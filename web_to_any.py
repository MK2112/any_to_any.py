import os
import re
import time
import shutil
import logging
import secrets
import tempfile
import threading
import webbrowser

import utils.language_support as lang

from functools import wraps
from utils.version import VERSION
from utils.category import Category
from core.controller import Controller
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from flask_uploads import UploadSet, configure_uploads, ALL
from core.utils.resolution import available_resolutions, normalize_resolution
from flask import Flask, render_template, request, send_file, jsonify, abort, session, g

# Web server providing a web interface
# Extension to the CLI-based any_to_any.py
app = Flask(__name__, template_folder=os.path.abspath("templates"))
app.secret_key = os.urandom(32)

app.config.update(
    MAX_CONTENT_LENGTH=5 * 1024**3, # 5 GiB max request size
    MAX_UPLOAD_FILE_SIZE=5 * 1024**3,
    MAX_UPLOAD_FILES=20,
    WEB_MAX_WORKERS=2,
    WEB_MAX_QUEUED_JOBS=8,
    JOB_RETENTION_SECONDS=15 * 60,
    JOB_CLEANUP_INTERVAL=60,
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

_csrf_tokens = {}
_csrf_max_entries = 10000
_csrf_ttl_seconds = 24 * 3600
_csrf_lock = threading.Lock()

_job_owners, _job_records = {}, {}
_job_lock = threading.Lock()
_JOB_ID_BYTES, _JOB_ID_RE = 16, re.compile(r"^[a-f0-9]{32}$")
_job_executor = ThreadPoolExecutor(
    max_workers=app.config["WEB_MAX_WORKERS"], thread_name_prefix="conversion"
)
_job_slots = threading.BoundedSemaphore(
    app.config["WEB_MAX_WORKERS"] + app.config["WEB_MAX_QUEUED_JOBS"]
)


def _job_owner_id() -> str:
    # Unique owner id per session so user can
    # authenticate for access to its jobs
    owner_id = session.get("job_owner_id")
    if owner_id is None:
        owner_id = secrets.token_urlsafe(32)
        session["job_owner_id"] = owner_id
    return owner_id


def _create_job_storage() -> tuple[str, str, str]:
    # Reserve both directories with exclusive creation before accepting files
    for _ in range(10):
        job_id = secrets.token_hex(_JOB_ID_BYTES)
        up_dir = f"{app.config['UPLOADED_FILES_DEST']}_{job_id}"
        cv_dir = f"{app.config['CONVERTED_FILES_DEST']}_{job_id}"
        created_upload_dir = False
        try:
            os.makedirs(up_dir, exist_ok=False)
            created_upload_dir = True
            os.makedirs(cv_dir, exist_ok=False)
        except FileExistsError:
            if created_upload_dir:
                shutil.rmtree(up_dir, ignore_errors=True)
            continue
        except Exception:
            if created_upload_dir:
                shutil.rmtree(up_dir, ignore_errors=True)
            raise

        with _job_lock:
            owner_id = _job_owner_id()
            _job_owners[job_id] = owner_id
            _job_records[job_id] = {
                "owner_id": owner_id,
                "upload_dir": up_dir,
                "converted_dir": cv_dir,
                "created_at": time.time(),
                "status": "queued",
                "cleanup_lock": threading.Lock(),
            }
        return job_id, up_dir, cv_dir

    raise RuntimeError("Could not allocate unique job storage")


def _job_is_authorized(job_id: str) -> bool:
    if not _JOB_ID_RE.fullmatch(job_id):
        return False
    owner_id = session.get("job_owner_id")
    if not owner_id:
        return False
    with _job_lock:
        job_owner = _job_owners.get(job_id)
    return job_owner is not None and secrets.compare_digest(job_owner, owner_id)


def _get_job_record(job_id: str):
    with _job_lock:
        return _job_records.get(job_id)


def _set_job_status(
    job_id: str, status: str, completed_at: float = None
) -> None:
    with _job_lock:
        rec = _job_records.get(job_id)
        if rec is not None:
            rec["status"] = status
            rec["updated_at"] = time.time()
            if completed_at is not None:
                rec["completed_at"] = completed_at


def _remove_job_record(job_id: str, record: dict = None) -> None:
    with _job_lock:
        current = _job_records.get(job_id)
        if record is not None and current is not record:
            return
        _job_records.pop(job_id, None)
        _job_owners.pop(job_id, None)
    with progress_lock:
        shared_progress_dict.pop(job_id, None)
        _last_progress_cache.pop(job_id, None)


def _cleanup_job_storage(job_id: str, record: dict = None) -> None:
    record = record or _get_job_record(job_id)
    if record is None:
        return
    with record["cleanup_lock"]:
        shutil.rmtree(record["upload_dir"], ignore_errors=True)
        shutil.rmtree(record["converted_dir"], ignore_errors=True)
        _remove_job_record(job_id, record)


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


@app.before_request
def reserve_conversion_slot():
    # Reserve capacity before request.form/request.files causes Flask to parse
    # and spool a multipart upload to disk.
    if request.method == "POST" and request.path in {"/convert", "/merge", "/concat"}:
        if not _job_slots.acquire(blocking=False):
            abort(429, "Conversion queue is full")
        g.conversion_slot_acquired = True


@app.teardown_request
def release_untransferred_conversion_slot(exception=None):
    if getattr(g, "conversion_slot_acquired", False):
        _job_slots.release()
        g.conversion_slot_acquired = False


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


def _cleanup_expired_jobs() -> None:
    now = time.time()
    retentn = app.config["JOB_RETENTION_SECONDS"]
    with _job_lock:
        records = list(_job_records.items())

    # Dir scan also removes abandoned storage left by process restart
    for job_id, record in records:
        completed_at = record.get("completed_at", record.get("updated_at", 0))
        if (
            record.get("status") in {"done", "error"}
            and now - completed_at >= retentn
        ):
            _cleanup_job_storage(job_id, record)

    prefixes = (
        os.path.abspath(app.config["UPLOADED_FILES_DEST"]),
        os.path.abspath(app.config["CONVERTED_FILES_DEST"]),
    )
    known_paths = {
        os.path.abspath(path)
        for _, record in records
        for path in (record["upload_dir"], record["converted_dir"])
    }

    for base_path in prefixes:
        parent = os.path.dirname(base_path)
        prefix = os.path.basename(base_path) + "_"
        try:
            candidates = os.scandir(parent)
        except OSError:
            continue
        with candidates:
            for entry in candidates:
                if not entry.name.startswith(prefix):
                    continue
                job_id = entry.name[len(prefix) :]
                if not _JOB_ID_RE.fullmatch(job_id):
                    continue
                path = os.path.abspath(entry.path)
                if path in known_paths:
                    continue
                try:
                    if now - entry.stat().st_mtime >= retentn:
                        shutil.rmtree(path, ignore_errors=True)
                except OSError:
                    continue


def _job_cleanup_loop() -> None:
    while True:
        try:
            _cleanup_expired_jobs()
        except Exception:
            app.logger.exception("Job cleanup failed")
        time.sleep(app.config["JOB_CLEANUP_INTERVAL"])


files = UploadSet("files", ALL)
app.config["UPLOADED_FILES_DEST"] = "./uploads"
app.config["CONVERTED_FILES_DEST"] = "./converted"
configure_uploads(app, files)

threading.Thread(
    target=_job_cleanup_loop, name="job-cleanup", daemon=True
).start()

with app.app_context():
    # Helps allocate memory early
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
            shutil.rmtree(source_path, ignore_errors=True)
            # Set the download name based on the directory name
            download_name = f"any_to_any_-_{dir_name}.zip"
        else:
            # If source is a file, zip just that file
            file_name = os.path.basename(source_path)
            # Create a temp dir to hold file
            temp_dir = tempfile.mkdtemp()
            temp_file_path = os.path.join(temp_dir, file_name)

            try:
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

        # Clean up temp file after sending
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
    max_files = app.config["MAX_UPLOAD_FILES"]
    if not uploaded_files or len(uploaded_files) > max_files:
        abort(400, f"No files or too many files (maximum {max_files})")

    file_max_size = app.config["MAX_UPLOAD_FILE_SIZE"]
    for uploaded_file in uploaded_files:
        if not uploaded_file or not uploaded_file.filename:
            continue
        try:
            current_position = uploaded_file.stream.tell()
            uploaded_file.stream.seek(0, os.SEEK_END)
            file_size = uploaded_file.stream.tell()
            uploaded_file.stream.seek(current_position)
        except (AttributeError, OSError):
            file_size = uploaded_file.content_length or 0
        if file_size > file_max_size:
            abort(413, "Uploaded file exceeds the per-file size limit")

    # A resize-only job (no format change) is meaningless without a resolution
    if fmt is None and resolution is None:
        abort(400, "A resolution is required for resize-only mode")
    if resolution is not None:
        resolution = normalize_resolution(
            controller._RES_ALIASES, controller._RES_ALL, resolution
        )
        if resolution is None:
            abort(400, "Invalid resolution")
    conv_key, up_dir, cv_dir = _create_job_storage()
    try:
        saved_files = 0
        for uploaded_file in uploaded_files:
            if uploaded_file and uploaded_file.filename:
                safe_name = re.sub(r"[^\w\.\-]", "_", uploaded_file.filename)
                uploaded_file.save(os.path.join(up_dir, safe_name))
                saved_files += 1
        if saved_files == 0:
            abort(400, "No files or empty filenames")
    except Exception:
        _cleanup_job_storage(conv_key)
        raise
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

        _set_job_status(job_id, "processing")
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
                completed_at = time.time()
                shared_dict[job_id].update(
                    {
                        "progress": total_files * 100,
                        "total": total_files * 100,
                        "completed_files": total_files,
                        "progress_percent": 100,
                        "status": "done",
                        "completed_at": completed_at,
                        "last_updated": completed_at,
                    }
                )
            _set_job_status(job_id, "done", completed_at)

    except Exception as e:
        error_msg = str(e)
        completed_at = time.time()
        if job_id and shared_dict is not None:
            with progress_lock:
                if job_id in shared_dict:
                    shared_dict[job_id].update(
                        {
                            "status": "error",
                            "error": error_msg,
                            "completed_at": completed_at,
                            "last_updated": completed_at,
                        }
                    )
        _set_job_status(job_id, "error", completed_at)
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

        job_id = None
        slot_transferred = False
        try:
            fmt, up_dir, cv_dir, job_id, resolution = process_params()
            job_controller = create_controller(
                job_id=job_id, shared_progress_dict=shared_progress_dict
            )
            # Merge/concat never apply a resolution; only conversions do
            if merge or concat:
                resolution = None

            future = _job_executor.submit(
                send_to_backend,
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
            )
            future.add_done_callback(lambda _: _job_slots.release())
            slot_transferred = True
            g.conversion_slot_acquired = False
        except Exception:
            if not slot_transferred:
                _job_slots.release()
                g.conversion_slot_acquired = False
            if job_id is not None:
                _cleanup_job_storage(job_id)
            raise
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
    if not _JOB_ID_RE.fullmatch(job_id):
        return jsonify({"error": "Invalid job ID"}), 400
    if not _job_is_authorized(job_id):
        abort(404, "Job not found")

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
    if not _JOB_ID_RE.fullmatch(job_id):
        abort(400)
    if not _job_is_authorized(job_id):
        abort(404, "Job not found")

    record = _get_job_record(job_id)
    if record is None or record.get("status") not in {"done", "error"}:
        abort(409, "Conversion is not complete")

    base_path = record["converted_dir"]
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
    try:
        response = push_zip(base_path)
    except Exception as e:
        app.logger.error(f"Error processing output: {str(e)}")
        abort(500, f"Error processing file: {str(e)}")

    _cleanup_job_storage(job_id)
    return response


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
