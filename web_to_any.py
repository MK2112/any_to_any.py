import os
import re
import sys
import time
import shutil
import logging
import secrets
import zipfile
import tempfile
import threading
import subprocess

import utils.language_support as lang

from functools import wraps
from utils.version import VERSION
from utils.category import Category
from core.controller import Controller
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from flask_uploads import UploadSet, configure_uploads, ALL
from core.utils.resolution import available_resolutions, normalize_resolution
from core.utils.file_handler import ConversionCancelled, FFmpegProcessTracker
from flask import Flask, render_template, request, send_file, jsonify, abort, session, g

# Web server providing a web interface
# Extension to the CLI-based any_to_any.py
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"))
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)

app.config.update(
    MAX_CONTENT_LENGTH=5 * 1024**3,  # 5 GiB max request size
    MAX_UPLOAD_FILE_SIZE=5 * 1024**3,
    MAX_UPLOAD_FILES=20,
    WEB_MAX_WORKERS=2,
    WEB_MAX_QUEUED_JOBS=8,
    JOB_RETENTION_SECONDS=15 * 60,
    JOB_CLEANUP_INTERVAL=60,
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

_CSRF_SESSION_KEY = "csrf_token"
_CSRF_ISSUED_AT_KEY = "csrf_token_issued_at"
_csrf_ttl_seconds = 24 * 3600  # idle age after which a token is re-issued

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
                "cancel_event": threading.Event(),
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


def _set_job_status(job_id: str, status: str, completed_at: float = None) -> None:
    with _job_lock:
        rec = _job_records.get(job_id)
        if rec is not None:
            rec["status"] = status
            rec["updated_at"] = time.time()
            if completed_at is not None:
                rec["completed_at"] = completed_at


def _forget_progress(job_id: str) -> None:
    with progress_lock:
        shared_progress_dict.pop(job_id, None)
        _last_progress_cache.pop(job_id, None)


def _remove_job_record(job_id: str, record: dict = None) -> None:
    with _job_lock:
        current = _job_records.get(job_id)
        if record is not None and current is not record:
            return
        _job_records.pop(job_id, None)
        _job_owners.pop(job_id, None)
    _forget_progress(job_id)


def _cleanup_job_storage(job_id: str, record: dict = None) -> None:
    record = record or _get_job_record(job_id)
    if record is None:
        return
    with record["cleanup_lock"]:
        shutil.rmtree(record["upload_dir"], ignore_errors=True)
        shutil.rmtree(record["converted_dir"], ignore_errors=True)
        _remove_job_record(job_id, record)


def _require_csrf(data: dict = None) -> None:
    # Validate CSRF token from a POST request
    csrf_token = data.get("csrf_token") if isinstance(data, dict) else None
    if not csrf_token:
        csrf_token = request.form.get("csrf_token") or request.headers.get(
            "X-CSRF-Token"
        )
    if not isinstance(csrf_token, str) or not validate_csrf_token(csrf_token):
        abort(403, "Invalid CSRF token")


def get_csrf_token():
    token = session.get(_CSRF_SESSION_KEY)
    issued_at = session.get(_CSRF_ISSUED_AT_KEY)
    if isinstance(token, str) and token and isinstance(issued_at, (int, float)):
        if time.time() - issued_at < _csrf_ttl_seconds:
            return token
    return rotate_csrf_token()


def validate_csrf_token(token):
    expected = session.get(_CSRF_SESSION_KEY)
    issued_at = session.get(_CSRF_ISSUED_AT_KEY)
    if not isinstance(expected, str) or not expected:
        return False
    if not isinstance(token, str):
        return False
    if not isinstance(issued_at, (int, float)):
        return False
    if time.time() - issued_at >= _csrf_ttl_seconds:
        return False
    return secrets.compare_digest(expected, token)


def rotate_csrf_token():
    # Tokens stay valid for their whole lifetime so parallel tabs and in-flight
    # requests keep working; only expiry issues a new token
    token = secrets.token_hex(32)
    session[_CSRF_SESSION_KEY] = token
    session[_CSRF_ISSUED_AT_KEY] = time.time()
    return token


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
_loopback_hosts = ("127.0.0.1", "localhost", "::1")
host = os.environ.get("Any2Any_HOST", "127.0.0.1")

try:
    port = int(os.environ.get("Any2Any_PORT", "5000"))
except (TypeError, ValueError):
    port = 5000


@app.before_request
def _apply_session_cookie_security():
    app.config["SESSION_COOKIE_SECURE"] = request.is_secure


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
    controller.web_host = _browser_url()
    return controller


def _browser_url() -> str:
    if host.lower() in ("0.0.0.0", "::"):
        return f"http://127.0.0.1:{port}"
    scheme = "http" if host.lower() in _loopback_hosts else "https"
    return f"{scheme}://{host}:{port}"


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
        if record.get("status") in {"done", "error", "cancelled"} and now - completed_at >= retentn:
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
app.config["UPLOADED_FILES_DEST"] = os.path.join(_BASE_DIR, "uploads")
app.config["CONVERTED_FILES_DEST"] = os.path.join(_BASE_DIR, "converted")
configure_uploads(app, files)

threading.Thread(target=_job_cleanup_loop, name="job-cleanup", daemon=True).start()

with app.app_context():
    # Helps allocate memory early
    _ = controller.supported_formats


def _zip_without_metadata(
    source_path: str, zip_path: str, include_metadata: bool = False
) -> None:
    dir_name = os.path.basename(source_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, dirs, files in os.walk(source_path):
            if not include_metadata:
                dirs[:] = [d for d in dirs if d != ".metadata"]
            for file_name in files:
                file_path = os.path.join(root, file_name)
                archive_name = os.path.join(
                    dir_name, os.path.relpath(file_path, source_path)
                )
                archive.write(file_path, archive_name)


def push_zip(source_path: str, include_metadata: bool = False):
    # Create .zip file from source path, serve it for download
    temp_fd, temp_path = tempfile.mkstemp(suffix=".zip")
    os.close(temp_fd)

    try:
        if os.path.isdir(source_path):
            # If source is a directory, zip its contents
            dir_name = os.path.basename(source_path)
            # Create the zip file with the directory's contents
            _zip_without_metadata(source_path, temp_path, include_metadata)
            # Set the download name based on the directory name
            download_name = f"any_to_any_-_{dir_name}.zip"
        else:
            # If source is a file, zip just that file
            file_name = os.path.basename(source_path)
            with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(source_path, file_name)
            download_name = f"any_to_any_-_{file_name}.zip"

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


def _has_output_files(output_dir: str) -> bool:
    if not os.path.isdir(output_dir):
        return False
    for _, _, files in os.walk(output_dir):
        if files:
            return True
    return False


def _preserve_unconverted_inputs(input_dir: str, output_dir: str) -> int:
    # Keep skipped or unread inputs downloadable instead of discarding them
    if (
        not input_dir
        or not output_dir
        or os.path.abspath(input_dir) == os.path.abspath(output_dir)
        or not os.path.isdir(input_dir)
        or not os.path.isdir(output_dir)
    ):
        return 0
    preserved = 0
    with os.scandir(input_dir) as entries:
        for entry in entries:
            if not entry.is_file():
                continue
            destination = os.path.join(output_dir, entry.name)
            base, ext = os.path.splitext(entry.name)
            suffix = 1
            while os.path.exists(destination):
                destination = os.path.join(output_dir, f"{base}_{suffix}{ext}")
                suffix += 1
            try:
                shutil.move(entry.path, destination)
                preserved += 1
            except OSError:
                app.logger.exception(
                    f"Could not preserve unconverted input {entry.path}"
                )
    return preserved


def process_params() -> tuple:
    uploaded_files = request.files.getlist("files")
    fmt = request.form.get("conversionType")
    resolution = request.form.get("resolution") or None
    metadata_mode = request.form.get("metadataMode", "none")

    # 'original' means "keep the source format", used for resize-only jobs
    if fmt == "original":
        fmt = None
    elif not fmt or fmt not in controller.supported_formats:
        abort(400, "Invalid format")
    max_files = app.config["MAX_UPLOAD_FILES"]
    if not uploaded_files or len(uploaded_files) > max_files:
        abort(400, f"No files or too many files (maximum {max_files})")

    file_max_size = app.config["MAX_UPLOAD_FILE_SIZE"]
    safe_names = set()
    for uploaded_file in uploaded_files:
        if not uploaded_file or not uploaded_file.filename:
            continue
        safe_name = re.sub(r"[^\w\.\-]", "_", uploaded_file.filename)
        # Reject rather than rename: merge pairs inputs by filename.
        collision_key = safe_name.rstrip(". ").casefold()
        if collision_key in safe_names:
            abort(400, "Upload filenames collide after sanitization")
        safe_names.add(collision_key)
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
    if metadata_mode not in {"none", "preserve", "strip"}:
        abort(400, "Invalid metadata mode")
    conv_key, up_dir, cv_dir = _create_job_storage()
    with _job_lock:
        _job_records[conv_key]["metadata_mode"] = metadata_mode
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
    return fmt, up_dir, cv_dir, conv_key, resolution, metadata_mode


@app.route("/")
def index():
    # Retrieve language from session (from browser), default to 'en_US'
    lang_code = session.get("language", "en_US")
    if lang_code not in lang.LANGUAGE_CODES:
        lang_code = "en_US"
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
    movie_resolutions = {
        fmt: available_resolutions(controller._supported_formats[Category.MOVIE], fmt)
        for fmt in controller._fmt_movie_keys
    }
    resized_formats = {
        **movie_resolutions,
        **{
            fmt: available_resolutions(
                controller._supported_formats[Category.MOVIE_CODECS], fmt
            )
            for fmt in controller._fmt_codec_keys
        },
        **{
            fmt: available_resolutions(
                controller._supported_formats[Category.PROTOCOLS], fmt
            )
            for fmt in controller._fmt_protocol_keys
        },
    }
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


def _conversion_error_message(exc: BaseException) -> str:
    # When end_with_msg() was called, report the job as failed so clients stop polling
    if isinstance(exc, SystemExit):
        if isinstance(exc.code, str) and exc.code.strip():
            return exc.code.strip()
        return (
            "Conversion failed: the file(s) could not be processed. "
            "Check the server log for details."
        )
    return str(exc) or type(exc).__name__


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
    metadata_mode: str = "none",
):
    job_id = getattr(controller_instance.prog_logger, "job_id", None)
    shared_dict = getattr(controller_instance.prog_logger, "shared_progress_dict", None)

    record = _get_job_record(job_id) if job_id else None
    cancel_event = record["cancel_event"] if record else None
    if cancel_event is not None:
        controller_instance.file_handler.cancel_event = cancel_event
    input_dir = input_path_args[0] if input_path_args else None
    total_files = 0
    if input_dir and os.path.isdir(input_dir):
        with os.scandir(input_dir) as it:
            total_files = sum(1 for entry in it if entry.is_file())

    error = None
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

        with _job_lock:
            if record and not cancel_event.is_set():
                record["status"] = "processing"
        if cancel_event is not None and cancel_event.is_set():
            raise ConversionCancelled("Conversion cancelled")
        with FFmpegProcessTracker(cancel_event, current_thread_only=True):
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
                preserve_meta=metadata_mode == "preserve",
                add_tag=False,
                strip_meta=metadata_mode == "strip",
                resolution=resolution,
            )
    except (Exception, SystemExit) as e:
        error = e
    finally:
        # Decide completion atomically with cancellation and publish only after cleanup.
        with _job_lock:
            cancelled = cancel_event is not None and cancel_event.is_set()
            had_output = _has_output_files(output)
            preserved = 0
            if not cancelled and input_path_args and os.path.exists(input_path_args[0]):
                preserved = _preserve_unconverted_inputs(input_path_args[0], output)
                if not _has_output_files(input_path_args[0]):
                    shutil.rmtree(input_path_args[0], ignore_errors=True)
            if (
                not cancelled
                and total_files > 0
                and not had_output
                and not preserved
                and not error
            ):
                error = RuntimeError("No output files were produced")
            status = "cancelled" if cancelled else ("error" if error else "done")
            completed_at = time.time()
            if record:
                record.update(status=status, completed_at=completed_at, updated_at=completed_at)
            if job_id and shared_dict is not None:
                with progress_lock:
                    progress = shared_dict.get(job_id)
                    if progress is not None:
                        progress.update(status=status, error=_conversion_error_message(error) if error and not cancelled else None,
                                        completed_at=completed_at, last_updated=completed_at)
                        if status == "done":
                            progress.update(progress=total_files * 100, total=total_files * 100,
                                            completed_files=total_files, progress_percent=100)
    if error and not cancelled:
        raise error


def create_conversion_endpoint(merge: bool = False, concat: bool = False):
    @_rate_check(max_req=30, window=3600)
    def endpoint():
        # Validate the CSRF token for all POST requests
        _require_csrf()

        job_id = None
        slot_transferred = False
        try:
            fmt, up_dir, cv_dir, job_id, resolution, metadata_mode = process_params()
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
                None,
                "high",
                None,
                merge,
                concat,
                resolution,
                metadata_mode,
            )
            with _job_lock:
                _job_records[job_id]["future"] = future

            def job_finished(done_future):
                if done_future.cancelled():
                    completed_at = time.time()
                    _set_job_status(job_id, "cancelled", completed_at)
                _job_slots.release()

            future.add_done_callback(job_finished)
            slot_transferred = True
            g.conversion_slot_acquired = False
        except Exception:
            if not slot_transferred:
                _job_slots.release()
                g.conversion_slot_acquired = False
            if job_id is not None:
                _cleanup_job_storage(job_id)
            raise
        return (
            jsonify({"job_id": job_id, "csrf_token": get_csrf_token()}),
            202,
        )

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


@app.route("/cancel/<job_id>", methods=["POST"])
def cancel_job(job_id: str):
    _require_csrf()
    if not _JOB_ID_RE.fullmatch(job_id):
        abort(400, "Invalid job ID")
    if not _job_is_authorized(job_id):
        abort(404, "Job not found")
    with _job_lock:
        record = _job_records.get(job_id)
        if record is None:
            abort(404, "Job not found")
        if record["status"] == "cancelled":
            return jsonify({"status": "cancelled"})
        if record["status"] in {"done", "error"}:
            abort(409, "Conversion is already complete")
        record["cancel_event"].set()
        record["status"] = "cancelling"
        future = record.get("future")
    if future is not None:
        future.cancel()  # A queued job can release its slot immediately.
    with _job_lock:
        status = record["status"]
    return jsonify({"status": status}), 202 if status == "cancelling" else 200


@app.route("/progress/<job_id>", methods=["GET"])
def get_progress(job_id: str):
    if not _JOB_ID_RE.fullmatch(job_id):
        return jsonify({"error": "Invalid job ID"}), 400
    if not _job_is_authorized(job_id):
        abort(404, "Job not found")

    with _job_lock:
        record = _job_records.get(job_id)
        if record is None:
            abort(404, "Job not found")
        job_status = record["status"]
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

        # ProgLogger can announce done before Controller.run has returned.
        # The job record is authoritative for the worker lifecycle.
        prog = dict(prog)
        prog["status"] = "waiting" if job_status == "queued" else job_status
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
        expired_job_ids = [
            jid
            for jid, job in shared_progress_dict.items()
            if job.get("status") in ["done", "error"]
            and (current_time - job.get("completed_at", 0)) > 300
        ]

        response = jsonify(
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

    for jid in expired_job_ids:
        _forget_progress(jid)
    return response


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
        response = push_zip(
            base_path,
            include_metadata=(
                record.get("metadata_mode") == "preserve"
                or os.path.isdir(os.path.join(base_path, ".metadata"))
            ),
        )
    except Exception as e:
        app.logger.error(f"Error processing output: {str(e)}")
        abort(500, f"Error processing file: {str(e)}")

    # The job remains available for re-download until its retention period expires
    return response


@app.route("/language", methods=["POST"])
def set_language():
    # Web interface language is set via the browser, *not* via sys language
    # This POST helps retrieve client's language info
    data = request.get_json(silent=True) or {}
    _require_csrf(data)
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
        return {
            "success": True,
            "lang_code": lang_code,
            "language": language,
            "csrf_token": get_csrf_token(),
        }
    return {"success": False}, 400


def _open_browser_quietly(url: str) -> None:
    # Launch default browser (I don't care about their output)
    subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, webbrowser; webbrowser.open(sys.argv[1])",
            url,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


if __name__ == "__main__":
    _open_browser_quietly(controller.web_host)
    app.run(debug=False, host=host, port=port)
