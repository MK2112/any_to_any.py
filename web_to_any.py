import os
import shutil
import tempfile
import threading
import time
import webbrowser
import utils.language_support as lang
from core.controller import Controller
from flask_uploads import UploadSet, configure_uploads, ALL
from flask import Flask, render_template, request, send_file, jsonify, abort, session
import logging

# Web server providing a web interface as extension to the CLI-based any_to_any.py
app = Flask(__name__, template_folder=os.path.abspath("templates"))
app.secret_key = os.urandom(32)  # Distinguish session

# Disable Flask's default access logging
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

# Optional: Keep our own logs at ERROR level to still see important errors
app.logger.setLevel(logging.ERROR)

host = "127.0.0.1"
port = 5000

# Initialize a default controller for the app
controller = None


# This function creates a new controller instance with the given job_id
def create_controller(job_id=None, shared_progress_dict=None):
    controller = Controller(job_id=job_id, shared_progress_dict=shared_progress_dict)
    controller.web_flag = True
    controller.web_host = f"{'http' if host.lower() in ['127.0.0.1', 'localhost'] else 'https'}://{host}:{port}"
    return controller


# Create default controller for the app
controller = create_controller()

# Shared progress dictionary for job tracking
shared_progress_dict = {}
progress_lock = threading.Lock()

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
    format = request.form.get("conversionType")
    # Achieve some convert-session specificity; 4 Bytes = 8 chars (collision within 26^8 is unlikely)
    conv_key: str = os.urandom(4).hex()
    # These are necessary because uploaded files are 'dumped' in there; Names may collide because of this, so we separate them from beginning
    up_dir: str = f"{app.config['UPLOADED_FILES_DEST']}_{conv_key}"  # separate upload directories for each conversion session
    cv_dir: str = f"{app.config['CONVERTED_FILES_DEST']}_{conv_key}"  # separate converted directories for each conversion session
    # Create directories for uploaded and converted files
    os.makedirs(up_dir, exist_ok=True)
    os.makedirs(cv_dir, exist_ok=True)
    # Save uploaded files to the upload directory
    for file in uploaded_files:
        if file:
            filename = os.path.join(up_dir, file.filename)
            file.save(filename)
    # File format to convert to
    return format, up_dir, cv_dir, conv_key


@app.route("/")
def index():
    # Retrieve language from session (from browser), default to 'en_US'
    lang_code = session.get("language", "en_US")
    translations = lang.get_all_translations(lang.LANGUAGE_CODES[lang_code])
    return render_template(
        "index.html",
        title="Any_To_Any.py",
        options=controller.supported_formats,
        translations=translations,
        lang_code=lang_code,
        supported_languages=lang.LANGUAGE_CODES,
    )


def send_to_backend(
    controller_instance,
    input_path_args: list,
    format: str,
    output: str,
    framerate: int,
    quality: str,
    merge: bool,
    concat: bool,
):
    # Process files in the background and update progress
    job_id = getattr(controller_instance.prog_logger, "job_id", None)
    shared_dict = getattr(controller_instance.prog_logger, "shared_progress_dict", None)

    try:
        # Set initial progress
        if job_id and shared_dict is not None:
            with progress_lock:
                shared_dict[job_id] = {
                    "progress": 0,
                    "total": 100,
                    "status": "processing",
                    "error": None,
                    "started_at": time.time(),
                    "last_updated": time.time(),
                }

        # Run the conversion
        controller_instance.run(
            input_path_args=input_path_args,
            format=format,
            output=output,
            framerate=framerate,
            quality=quality,
            merge=merge,
            concat=concat,
            delete=True,
            across=False,
            recursive=False,
            dropzone=False,
            language="en_US",
        )

        # Mark as done
        if job_id and shared_dict is not None:
            with progress_lock:
                shared_dict[job_id].update(
                    {
                        "progress": 100,
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
        # Re-raise the exception to be handled by the caller
        raise

    finally:
        # Clean up uploaded files
        if (
            input_path_args
            and len(input_path_args) > 0
            and os.path.exists(input_path_args[0])
        ):
            shutil.rmtree(input_path_args[0], ignore_errors=True)


@app.route("/convert", methods=["POST"])
def convert():
    format, up_dir, cv_dir, job_id = process_params()
    # Create a new controller instance for this job
    job_controller = create_controller(
        job_id=job_id, shared_progress_dict=shared_progress_dict
    )

    # Start conversion in background thread
    thread = threading.Thread(
        target=send_to_backend,
        args=(
            job_controller,
            [up_dir],
            format,
            cv_dir,
            0,
            "high",
            False,
            False,
        ),
    )
    thread.start()
    # Return job_id so frontend can poll progress
    return jsonify({"job_id": job_id}), 202


@app.route("/merge", methods=["POST"])
def merge():
    format, up_dir, cv_dir, job_id = process_params()
    # Create a new controller instance for this job
    job_controller = create_controller(
        job_id=job_id, shared_progress_dict=shared_progress_dict
    )

    # Start conversion in background thread
    thread = threading.Thread(
        target=send_to_backend,
        args=(
            job_controller,
            [up_dir],
            format,
            cv_dir,
            0,
            "high",
            True,
            False,
        ),
    )
    thread.start()
    # Return job_id so frontend can poll progress
    return jsonify({"job_id": job_id}), 202


@app.route("/concat", methods=["POST"])
def concat():
    format, up_dir, cv_dir, job_id = process_params()
    # Create a new controller instance for this job
    job_controller = create_controller(
        job_id=job_id, shared_progress_dict=shared_progress_dict
    )

    # Start conversion in background thread
    thread = threading.Thread(
        target=send_to_backend,
        args=(
            job_controller,
            [up_dir],
            format,
            cv_dir,
            0,
            "high",
            False,
            True,
        ),
    )
    thread.start()
    # Return job_id so frontend can poll progress
    return jsonify({"job_id": job_id}), 202


@app.route("/progress/<job_id>", methods=["GET"])
def get_progress(job_id):
    # Get the current progress of a conversion job
    with progress_lock:
        # Get the current progress, or default values if job not found
        progress = shared_progress_dict.get(
            job_id,
            {
                "progress": 0,
                "total": 100,
                "status": "waiting",  # Indicate job hasn't started yet
                "error": None,
                "progress_percent": 0,
            },
        )

        # Ensure we have a progress percentage
        if "progress_percent" not in progress:
            if progress.get("total", 0) > 0:
                progress["progress_percent"] = int(
                    (progress.get("progress", 0) / progress["total"]) * 100
                )
            else:
                progress["progress_percent"] = 0

        # Clean up completed or errored jobs that are older than 5 minutes
        current_time = time.time()
        for jid in list(shared_progress_dict.keys()):
            job = shared_progress_dict[jid]
            if (
                job.get("status") in ["done", "error"]
                and (current_time - job.get("completed_at", 0)) > 300
            ):
                del shared_progress_dict[jid]

        # Create a new dict to avoid thread-safety issues
        response = {
            "progress": progress.get("progress", 0),
            "total": progress.get("total", 100),
            "status": progress.get("status", "waiting"),
            "error": progress.get("error"),
            "progress_percent": progress.get("progress_percent", 0),
        }

        return jsonify(response)


@app.route("/download/<job_id>", methods=["GET"])
def download_zip(job_id):
    # Download the converted files as a .zip archive
    # Handles both single files and directories of files
    base_path = f"{app.config['CONVERTED_FILES_DEST']}_{job_id}"

    # Check if the path exists
    if not os.path.exists(base_path):
        abort(404, "Output not found")

    # If it's a directory, check if it has any content
    if os.path.isdir(base_path):
        # Check for any files or directories
        has_content = False
        for root, dirs, files in os.walk(base_path):
            if files or dirs:
                has_content = True
                break

        if not has_content:
            abort(404, "No converted files found in output directory")

    # If it's a single file, handle it directly
    if os.path.isfile(base_path):
        try:
            # For single files, we'll zip just that file
            return push_zip(base_path)
        except Exception as e:
            app.logger.error(f"Error processing single file: {str(e)}")
            abort(500, f"Error processing file: {str(e)}")

    # For directories, use the directory as the source
    return push_zip(base_path)


@app.route("/language", methods=["POST"])
def set_language():
    # Web interface language is set via the browser, *not* via sys language
    # This POST helps retrieve client's language info
    data = request.get_json()
    lang_code = data.get("language")
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
