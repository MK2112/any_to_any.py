import os
import shutil
import tempfile
import threading
import webbrowser
import utils.language_support as lang
from core.controller import Controller
from flask_uploads import UploadSet, configure_uploads, ALL
from flask import Flask, render_template, request, send_file, jsonify, abort, session

"""
Web server providing a web interface as extension to the CLI-based any_to_any.py
"""

app = Flask(__name__, template_folder=os.path.abspath("templates"))
app.secret_key = os.urandom(32)  # Distinguish session

host = "127.0.0.1"
port = 5000
controller = Controller()
controller.web_flag = True
controller.web_host = f"{'http' if host.lower() in ['127.0.0.1', 'localhost'] else 'https'}://{host}:{port}"

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


def push_zip(cv_dir: str):
    """Create a zip file from the contents of cv_dir and serve it for download."""
    # Create a temporary file for the zip
    temp_fd, temp_path = tempfile.mkstemp(suffix='.zip')
    os.close(temp_fd)
    
    try:
        # Create the zip file
        shutil.make_archive(temp_path[:-4], 'zip', cv_dir)
        
        # Remove the converted files directory
        shutil.rmtree(cv_dir, ignore_errors=True)
        
        # Send the file
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=f'any_to_any_-_{os.path.basename(cv_dir)}.zip',
            mimetype='application/zip'
        )
    except Exception:
        # Clean up temp file if it exists
        if os.path.exists(temp_path):
            os.unlink(temp_path)
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
    input_path_args: list,
    format: str,
    output: str,
    framerate: int,
    quality: str,
    merge: bool,
    concat: bool,
    job_id: str = None,
    shared_progress_dict: dict = None,
):
    """Process files in the background and update progress."""
    try:
        # Set initial progress
        if job_id and shared_progress_dict is not None:
            with progress_lock:
                shared_progress_dict[job_id] = {
                    'progress': 0,
                    'total': 100,
                    'status': 'processing',
                    'error': None
                }
        
        # Run the conversion
        controller.run(
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
        if job_id and shared_progress_dict is not None:
            with progress_lock:
                shared_progress_dict[job_id].update({
                    'progress': 100,
                    'status': 'done'
                })
                
    except Exception as e:
        # Update progress with error
        if job_id and shared_progress_dict is not None:
            with progress_lock:
                shared_progress_dict[job_id].update({
                    'status': 'error',
                    'error': str(e)
                })
        raise
        
    finally:
        # Clean up uploaded files
        if input_path_args and len(input_path_args) > 0 and os.path.exists(input_path_args[0]):
            shutil.rmtree(input_path_args[0], ignore_errors=True)


@app.route("/convert", methods=["POST"])
def convert():
    format, up_dir, cv_dir, job_id = process_params()
    # Start conversion in a thread for async progress
    thread = threading.Thread(
        target=send_to_backend,
        kwargs={
            "input_path_args": [up_dir],
            "format": format,
            "output": cv_dir,
            "framerate": None,
            "quality": None,
            "merge": None,
            "concat": None,
            "job_id": job_id,
            "shared_progress_dict": shared_progress_dict,
        },
    )
    thread.start()
    # Return job_id so frontend can poll progress
    return jsonify({"job_id": job_id}), 202


@app.route("/merge", methods=["POST"])
def merge():
    _, up_dir, cv_dir, job_id = process_params()
    thread = threading.Thread(
        target=send_to_backend,
        kwargs={
            "input_path_args": [up_dir],
            "format": None,
            "output": cv_dir,
            "framerate": None,
            "quality": None,
            "merge": True,
            "concat": None,
            "job_id": job_id,
            "shared_progress_dict": shared_progress_dict,
        },
    )
    thread.start()
    return jsonify({"job_id": job_id}), 202


@app.route("/concat", methods=["POST"])
def concat():
    _, up_dir, cv_dir, job_id = process_params()
    thread = threading.Thread(
        target=send_to_backend,
        kwargs={
            "input_path_args": [up_dir],
            "format": None,
            "output": cv_dir,
            "framerate": None,
            "quality": None,
            "merge": None,
            "concat": True,
            "job_id": job_id,
            "shared_progress_dict": shared_progress_dict,
        },
    )
    thread.start()
    return jsonify({"job_id": job_id}), 202


@app.route("/progress/<job_id>", methods=["GET"])
def get_progress(job_id):
    """Get the current progress of a conversion job."""
    with progress_lock:
        progress = shared_progress_dict.get(job_id, {
            'progress': 0,
            'total': 100,
            'status': 'processing',
            'error': None
        })
        return jsonify(progress)


@app.route("/download/<job_id>", methods=["GET"])
def download_zip(job_id):
    """Download the converted files as a zip archive."""
    cv_dir = f"{app.config['CONVERTED_FILES_DEST']}_{job_id}"
    
    # Check if directory exists and has files
    if not os.path.exists(cv_dir) or not os.path.isdir(cv_dir):
        abort(404, "Output directory not found")
        
    files = [f for f in os.listdir(cv_dir) if os.path.isfile(os.path.join(cv_dir, f))]
    if not files:
        abort(404, "No converted files found")
    
    return push_zip(cv_dir)


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
