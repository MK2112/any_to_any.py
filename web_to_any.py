import os
import shutil
import tempfile
import webbrowser
from any_to_any import AnyToAny
from flask import Flask, render_template, request, send_file, Response
from flask_uploads import UploadSet, configure_uploads, ALL

"""
Web server providing a web interface as extension to the CLI-based any_to_any.py
"""

app = Flask(__name__, template_folder=os.path.abspath("templates"))
host = "127.0.0.1"
port = 5000
any_to_any = AnyToAny()
any_to_any.web_flag = True
any_to_any.web_host = f'{"http" if host.lower() in ["127.0.0.1", "localhost"] else "https"}://{host}:{port}'

files = UploadSet("files", ALL)
app.config["UPLOADED_FILES_DEST"] = "./uploads"
app.config["CONVERTED_FILES_DEST"] = "./converted"
configure_uploads(app, files)

with app.app_context():
    # This is intended to help allocate memory early
    _ = any_to_any.supported_formats

def push_zip(cv_dir: str) -> Response:
    # Check if cv_dir is empty
    if len(os.listdir(cv_dir)) == 0:
        return Response("No files to convert", status=100)
    # Create a temporary dir for zip file
    temp_dir = tempfile.mkdtemp()
    zip_filename = os.path.join(temp_dir, "converted_files.zip")
    # Zip all files in the 'converted' directory and save it in the temporary directory
    shutil.make_archive(zip_filename[:-4], "zip", cv_dir)
    shutil.rmtree(cv_dir)  # Clean up 'converted' dir
    return send_file(zip_filename, as_attachment=True)  # Return zip file

def process_params() -> tuple:
    uploaded_files = request.files.getlist("files")
    format = request.form.get("conversionType")
    # Achieve some convert-session specificity; 4 Bytes = 8 chars (collision within 26^8 is unlikely)
    conv_key: str = os.urandom(4).hex()
    # These are necessary because uploaded files are 'dumped' in there; Names may collide because of this, so we separate them from beginning
    up_dir: str = f'{app.config["UPLOADED_FILES_DEST"]}_{conv_key}'  # separate upload directories for each conversion session
    cv_dir: str = f'{app.config["CONVERTED_FILES_DEST"]}_{conv_key}'  # separate converted directories for each conversion session

    if not os.path.exists(up_dir):
        os.makedirs(up_dir)
    if not os.path.exists(cv_dir):
        os.makedirs(cv_dir)

    for file in uploaded_files:
        if file:
            filename = os.path.join(up_dir, file.filename)
            file.save(filename)
    # File format to convert to
    return format, up_dir, cv_dir

@app.route("/")
def index():
    return render_template("index.html", title="Any_To_Any.py", options=any_to_any.supported_formats)


def send_to_backend(
    input_path_args: list,
    format: str,
    output: str,
    framerate: int,
    quality: str,
    merge: bool,
    concat: bool,
) -> None:
    # A bit hacky, centralized point to talk to any_to_any.py backend
    any_to_any.run(
        input_path_args=input_path_args,
        format=format,
        output=output,
        framerate=framerate,
        quality=quality,
        merge=merge,
        concat=concat,
        delete=True,
        across=False,
    )
    # Remove upload dir and contents therein
    if len(input_path_args[0]) > 0:
        shutil.rmtree(input_path_args[0])

@app.route("/convert", methods=["POST"])
def convert():
    format, up_dir, cv_dir = process_params()
    # Convert all files uploaded to the 'uploads' directory and save it in the 'converted' directory
    send_to_backend(
        input_path_args=[up_dir],
        format=format,
        output=cv_dir,
        framerate=None,
        quality=None,
        merge=None,
        concat=None,
    )
    return push_zip(cv_dir)


@app.route("/merge", methods=["POST"])
def merge():
    _, up_dir, cv_dir = process_params()
    # Merge all files in the 'uploads' directory and save it in the 'converted' directory
    send_to_backend(
        input_path_args=[up_dir],
        format=None,
        output=cv_dir,
        framerate=None,
        quality=None,
        merge=True,
        concat=None,
    )
    return push_zip(cv_dir)


@app.route("/concat", methods=["POST"])
def concat():
    _, up_dir, cv_dir = process_params()
    # Concatenation is always done with the same format, we just don't explicitly care here which format that is
    send_to_backend(
        input_path_args=[up_dir],
        format=None,
        output=cv_dir,
        framerate=None,
        quality=None,
        merge=None,
        concat=True,
    )
    return push_zip(cv_dir)


if __name__ == "__main__":
    webbrowser.open(any_to_any.web_host)
    app.run(debug=True, host=host, port=port)
