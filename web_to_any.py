import os
import re
import time
import shutil
import logging
import tempfile
import threading
import webbrowser
import secrets
import utils.language_support as lang

from functools import wraps
from utils.version import VERSION
from core.controller import Controller
from core.utils.resolution import available_resolutions, normalize_resolution
from utils.category import Category
from datetime import datetime, timedelta
from flask_uploads import UploadSet, configure_uploads, ALL
from flask import Flask, render_template, request, send_file, jsonify, abort, session

# Web server providing a web interface
# Extension to the CLI-based any_to_any.py
app = Flask(__name__, template_folder=os.path.abspath("templates"))
app.secret_key = os.urandom(32)

# 16 GiB effective upload limit, adjust as needed
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024**3
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

_csrf_tokens = {}
_csrf_max_entries = 10000
_csrf_ttl_seconds = 24 * 3600
_csrf_lock = threading.Lock()


def get_csrf_token():
    session_id = session.sid if hasattr(session, "sid") else request.remote_addr
    now = time.time()
    with _csrf_lock:
        entry = _csrf_tokens.get(session_id)
        if entry and now - entry["created_at"] < _csrf_ttl_seconds:
            return entry["token"]
        # Remove expired entries, cap size to bound memory (i.e. drop oldest)
        if len(_csrf_tokens) >= _csrf_max_entries:
            for sid in sorted(
                _csrf_tokens, key=lambda s: _csrf_tokens[s]["created_at"]
            )[: len(_csrf_tokens) // 10]:
                _csrf_tokens.pop(sid, None)
        token = secrets.token_hex(32)
        _csrf_tokens[session_id] = {"token": token, "created_at": now}
        return token


def validate_csrf_token(token):
    session_id = session.sid if hasattr(session, "sid") else request.remote_addr
    now = time.time()
    with _csrf_lock:
        entry = _csrf_tokens.get(session_id)
        if (
            entry
            and now - entry["created_at"] < _csrf_ttl_seconds
            and secrets.compare_digest(entry["token"], token)
        ):
            return True
    return False


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": get_csrf_token()}


# Security headers
@app.after_request
def headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    return response


# Disable Flask's default access logging
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)
app.logger.setLevel(logging.ERROR)

host = "127.0.0.1"
port = 5000

_is_loopback = host.lower() in ("127.0.0.1", "localhost", "::1")
app.config["SESSION_COOKIE_SECURE"] = not _is_loopback

# Rate limiting
_rate_limit = {}
_max_ips = 10000
_rate_lock = threading.Lock()


def _rate_check(max_req: int = 30, window: int = 3600):
    # Rate limit as max_req per window seconds per IP.
    # max_req reqs ALLOWED per window and request max_req+1 gets 429
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ip = request.remote_addr
            now = datetime.now()
            cutoff = now - timedelta(seconds=window)
            with _rate_lock:
                _rate_limit[ip] = [t for t in _rate_limit.get(ip, []) if t > cutoff]
                if len(_rate_limit[ip]) >= max_req:
                    abort(429)
                _rate_limit[ip].append(now)
                if len(_rate_limit) > _max_ips:
                    for k in sorted(_rate_limit, key=lambda k: len(_rate_limit[k]))[
                        : len(_rate_limit) // 10
                    ]:
                        _rate_limit.pop(k, None)
            return f(*args, **kwargs)

        return wrapper

    return decorator


# Initialize a default controller for the app
controller = None


# This function creates a new controller instance with the given job_id
def create_controller(
    job_id: str = None, shared_progress_dict: dict = None
) -> Controller:
    controller = Controller(
        job_id=job_id, shared_progress_dict=shared_progress_dict, is_web=True
    )
    controller.web_flag = True
    controller.web_host = f"{'http' if host.lower() in ['127.0.0.1', 'localhost'] else 'https'}://{host}:{port}"
    return controller


# Create default controller for the app
controller = create_controller()

# Shared progress dictionary for job tracking
shared_progress_dict = {}
progress_lock = threading.Lock()
_last_progress_cache = {}

files = UploadSet("files", ALL)
app.config["UPLOADED_FILES_DEST"] = "./uploads"
app.config["CONVERTED_FILES_DEST"] = "./converted"
configure_uploads(app, files)

with app.app_context():
    # Intended to help allocate memory early
    _ = controller.supported_formats


def push_zip(source_path: str):
    # Create .zip file from source path, serve it for download.
    # Source can be either a directory or a single file, doesn't matter.
    # Create a temporary file for the zip
    temp_fd, temp_path = tempfile.mkstemp(suffix=".zip")
    os.close(temp_fd)

    try:
        if os.path.isdir(source_path):
            # If source is a directory, zip its contents
            base_dir = os.path.dirname(source_path)
            dir_name = os.path.basename(source_path)

            # Create the zip file with the directory's contents
            shutil.make_archive(temp_path[:-4], "zip", base_dir, dir_name)

            # Clean up the original directory
            shutil.rmtree(source_path, ignore_errors=True)

            # Set the download name based on the directory name
            download_name = f"any_to_any_-_{dir_name}.zip"
        else:
            # If source is a file, zip just that file
            file_name = os.path.basename(source_path)

            # Create a temporary directory to hold the file
            temp_dir = tempfile.mkdtemp()
            temp_file_path = os.path.join(temp_dir, file_name)

            try:
                # Move the file to the temp directory
                shutil.move(source_path, temp_file_path)

                # Create the zip file with the single file
                shutil.make_archive(temp_path[:-4], "zip", temp_dir)

                # Set the download name based on the file name
                download_name = f"any_to_any_-_{file_name}.zip"
            finally:
                # Clean up the temporary directory
                shutil.rmtree(temp_dir, ignore_errors=True)

        # Send the file
        response = send_file(
            temp_path,
            as_attachment=True,
            download_name=download_name,
            mimetype="application/zip",
        )

        # Clean up the temp file after sending
        try:
            response.call_on_close(
                lambda: os.unlink(temp_path) if os.path.exists(temp_path) else None
            )
        except Exception as e:
            app.logger.error(
                f"Error setting up cleanup for temp file {temp_path}: {str(e)}"
            )

        return response
    except Exception as e:
        # Clean up temp file if it exists
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        app.logger.error(f"Error in push_zip: {str(e)}")
        raise


def process_params() -> tuple:
    uploaded_files = request.files.getlist("files")
    fmt = request.form.get("conversionType")
    resolution = request.form.get("resolution") or None

    # 'original' means "keep the source format", used for resize-only jobs
    if fmt == "original":
        fmt = None
    elif not fmt or fmt not in controller.supported_formats:
        abort(400, "Invalid format")
    if not uploaded_files or len(uploaded_files) > 50:
        abort(400, "No files or too many files")
    # A resize-only job (no format change) is meaningless without a resolution
    if fmt is None and resolution is None:
        abort(400, "A resolution is required for resize-only mode")
    if resolution is not None:
        resolution = normalize_resolution(
            controller._RES_ALIASES, controller._RES_ALL, resolution
        )
        if resolution is None:
            abort(400, "Invalid resolution")

    conv_key = os.urandom(4).hex()
    up_dir = f"{app.config['UPLOADED_FILES_DEST']}_{conv_key}"
    cv_dir = f"{app.config['CONVERTED_FILES_DEST']}_{conv_key}"
    os.makedirs(up_dir, exist_ok=True)
    os.makedirs(cv_dir, exist_ok=True)

    for file in uploaded_files:
        if file and file.filename:
            safe_name = re.sub(r"[^\w\.\-]", "_", file.filename)
            file.save(os.path.join(up_dir, safe_name))
    return fmt, up_dir, cv_dir, conv_key, resolution


@app.route("/")
def index():
    # Retrieve language from session (from browser), default to 'en_US'
    lang_code = session.get("language", "en_US")
    translations = lang.get_all_translations(lang.LANGUAGE_CODES[lang_code])
    # Graceful fallback: any untranslated key resolves to its English text
    translations = {
        **lang.get_all_translations("English"),
        **translations,
    }
    grouped_options = []
    for category, mapping in controller._supported_formats.items():
        cat_name = str(category).split(".")[-1].replace("_", " ").title()
        grouped_options.append(
            {
                "label": cat_name,
                "formats": sorted(mapping.keys(), key=str.lower),
            }
        )
    # Only movie formats, codecs and protocols accept resizing. Expose the per
    # format allowed resolutions so the UI can constrain the choices up front.
    resized_formats = {}
    movie_resolutions = {}
    for fmt in controller._fmt_movie_keys:
        resolved = available_resolutions(
            controller._supported_formats[Category.MOVIE], fmt
        )
        movie_resolutions[fmt] = resolved
        resized_formats[fmt] = resolved
    for fmt in controller._fmt_codec_keys:
        resized_formats[fmt] = available_resolutions(
            controller._supported_formats[Category.MOVIE_CODECS], fmt
        )
    for fmt in controller._fmt_protocol_keys:
        resized_formats[fmt] = available_resolutions(
            controller._supported_formats[Category.PROTOCOLS], fmt
        )
    return render_template(
        "index.html",
        title=f"any_to_any.py {VERSION}",
        options=grouped_options,
        translations=translations,
        lang_code=lang_code,
        supported_languages=lang.LANGUAGE_CODES,
        resolution_data={
            "ladder": list(controller._STD_RES),
            "formats": resized_formats,
            "movies": movie_resolutions,
            "strings": {
                "resolution_original": translations["resolution_original"],
                "resolution_required": translations["resolution_required"],
                "movies_required": translations["resize_only_movies_required"],
            },
        },
    )


def send_to_backend(
    controller_instance: Controller,
    input_path_args: list,
    format: str,
    output: str,
    framerate: int,
    quality: str,
    split_pattern: str,
    merge: bool,
    concat: bool,
    resolution: str = None,
):
    job_id = getattr(controller_instance.prog_logger, "job_id", None)
    shared_dict = getattr(controller_instance.prog_logger, "shared_progress_dict", None)

    input_dir = input_path_args[0] if input_path_args else None
    total_files = 0
    if input_dir and os.path.isdir(input_dir):
        total_files = len(
            [
                f
                for f in os.listdir(input_dir)
                if os.path.isfile(os.path.join(input_dir, f))
            ]
        )

    try:
        if job_id and shared_dict is not None:
            with progress_lock:
                shared_dict[job_id] = {
                    "progress": 0,
                    "total": total_files * 100,
                    "total_files": total_files,
                    "completed_files": 0,
                    "status": "processing",
                    "error": None,
                    "started_at": time.time(),
                    "last_updated": time.time(),
                }

        controller_instance.run(
            input_path_args=input_path_args,
            format=format,
            output=output,
            framerate=framerate,
            quality=quality,
            split=split_pattern,
            merge=merge,
            concat=concat,
            delete=True,
            across=False,
            recursive=False,
            dropzone=False,
            language="en_US",
            workers=1,
            preserve_meta=True,
            add_tag=False,
            strip_meta=False,
            resolution=resolution,
        )

        if job_id and shared_dict is not None:
            with progress_lock:
                shared_dict[job_id].update(
                    {
                        "progress": total_files * 100,
                        "total": total_files * 100,
                        "completed_files": total_files,
                        "progress_percent": 100,
                        "status": "done",
                        "completed_at": time.time(),
                        "last_updated": time.time(),
                    }
                )

    except Exception as e:
        error_msg = str(e)
        if job_id and shared_dict is not None:
            with progress_lock:
                if job_id in shared_dict:
                    shared_dict[job_id].update(
                        {
                            "status": "error",
                            "error": error_msg,
                            "completed_at": time.time(),
                            "last_updated": time.time(),
                        }
                    )
        raise

    finally:
        if (
            input_path_args
            and len(input_path_args) > 0
            and os.path.exists(input_path_args[0])
        ):
            shutil.rmtree(input_path_args[0], ignore_errors=True)


def create_conversion_endpoint(merge: bool = False, concat: bool = False):
    @_rate_check(max_req=30, window=3600)
    def endpoint():
        csrf_token = request.form.get("csrf_token") or request.headers.get(
            "X-CSRF-Token"
        )
        # Validating the CSRF token for all POST requests
        if not csrf_token or not validate_csrf_token(csrf_token):
            abort(403, "Invalid CSRF token")

        fmt, up_dir, cv_dir, job_id, resolution = process_params()
        # New controller instance for this job
        job_controller = create_controller(
            job_id=job_id, shared_progress_dict=shared_progress_dict
        )
        # Merge/concat never apply a resolution; only conversions do
        if merge or concat:
            resolution = None
        # Start conversion in background thread
        thread = threading.Thread(
            target=send_to_backend,
            args=(
                job_controller,
                [up_dir],
                fmt,
                cv_dir,
                0,
                "high",
                None,
                merge,
                concat,
                resolution,
            ),
        )
        thread.start()
        # Return job_id so frontend can poll progress
        return jsonify({"job_id": job_id}), 202

    return endpoint


app.add_url_rule(
    "/convert",
    "convert",
    create_conversion_endpoint(merge=False, concat=False),
    methods=["POST"],
)
app.add_url_rule(
    "/merge",
    "merge",
    create_conversion_endpoint(merge=True, concat=False),
    methods=["POST"],
)
app.add_url_rule(
    "/concat",
    "concat",
    create_conversion_endpoint(merge=False, concat=True),
    methods=["POST"],
)


@app.route("/progress/<job_id>", methods=["GET"])
def get_progress(job_id: str):
    if not re.match(r"^[a-f0-9]{8}$", job_id):
        return jsonify({"error": "Invalid job ID"}), 400

    with progress_lock:
        prog = shared_progress_dict.get(
            job_id,
            {
                "progress": 0,
                "total": 100,
                "status": "waiting",
                "error": None,
                "progress_percent": 0,
            },
        )

        total_n_files = prog.get("total_files", 1)
        current_prog = prog.get("progress", 0)
        last_prog = _last_progress_cache.get(job_id, 0)

        if current_prog < last_prog and last_prog > 0:
            completed_files = prog.get("completed_files", 0) + 1
            prog["completed_files"] = completed_files
        else:
            completed_files = prog.get("completed_files", 0)

        _last_progress_cache[job_id] = current_prog

        if total_n_files > 1 and completed_files > 0:
            cumulative_prog = completed_files * 100 + current_prog
            progress_percent = int((cumulative_prog / (total_n_files * 100)) * 100)
        elif prog.get("progress_percent") is not None:
            progress_percent = prog.get("progress_percent")
            cumulative_prog = current_prog
        else:
            progress_percent = (
                int((current_prog / prog.get("total", 100)) * 100)
                if prog.get("total", 0) > 0
                else 0
            )
            cumulative_prog = current_prog

        current_time = time.time()
        for jid in list(shared_progress_dict.keys()):
            job = shared_progress_dict[jid]
            if (
                job.get("status") in ["done", "error"]
                and (current_time - job.get("completed_at", 0)) > 300
            ):
                del shared_progress_dict[jid]
                _last_progress_cache.pop(jid, None)

        return jsonify(
            {
                "progress": cumulative_prog if total_n_files > 1 else current_prog,
                "total": total_n_files * 100,
                "status": prog.get("status", "waiting"),
                "error": prog.get("error"),
                "progress_percent": progress_percent,
                "total_files": total_n_files,
                "completed_files": completed_files,
            }
        )


@app.route("/download/<job_id>", methods=["GET"])
def download_zip(job_id: str):
    if not re.match(r"^[a-f0-9]{8}$", job_id):
        abort(400)

    base_path = f"{app.config['CONVERTED_FILES_DEST']}_{job_id}"
    if not os.path.exists(base_path):
        abort(404, "Output not found")

    # If it's a directory, check if it has any content
    if os.path.isdir(base_path):
        has_content = False
        for _, dirs, files in os.walk(base_path):
            if files or dirs:
                has_content = True
                break

        if not has_content:
            abort(404, "No converted files found in output directory")

    # If it's a single file
    if os.path.isfile(base_path):
        try:
            # Zip single file
            return push_zip(base_path)
        except Exception as e:
            app.logger.error(f"Error processing single file: {str(e)}")
            abort(500, f"Error processing file: {str(e)}")
    return push_zip(base_path)


@app.route("/language", methods=["POST"])
def set_language():
    # Web interface language is set via the browser, *not* via sys language
    # This POST helps retrieve client's language info
    data = request.get_json(silent=True) or {}
    lang_code = data.get("language")
    if not lang_code:
        return {"success": False}, 400
    if "_" not in lang_code:
        for code, _ in lang.LANGUAGE_CODES.items():
            if lang_code in code:
                lang_code = code
                break
    if lang_code and lang_code in lang.LANGUAGE_CODES:
        session["language"] = lang_code
        language = lang.LANGUAGE_CODES[lang_code]
        return {"success": True, "lang_code": lang_code, "language": language}
    return {"success": False}, 400


if __name__ == "__main__":
    webbrowser.open(controller.web_host)
    app.run(debug=False, host=host, port=port)
