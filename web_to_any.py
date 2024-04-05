import os
from any_to_any import AnyToAny
from flask import Flask, render_template, request, send_file
from flask_uploads import UploadSet, configure_uploads, ALL # special `pip install flask-reuploaded` needed
import shutil
import tempfile
import webbrowser

"""
Web server providing a web interface as extension to the CLI-based any-to-any.py
"""

app = Flask(__name__, template_folder=os.path.abspath('templates'))
host = '127.0.0.1'
port = 5000
any_to_any = AnyToAny()

files = UploadSet('files', ALL)
app.config['UPLOADED_FILES_DEST'] = './uploads'
app.config['CONVERTED_FILES_DEST'] = './converted'
configure_uploads(app, files)


with app.app_context():
    # This is intended to help allocate memory early
    _ = any_to_any.supported_formats


def create_send_zip(cv_dir: str):
    # Create a temporary dir for zip file
    temp_dir = tempfile.mkdtemp()
    zip_filename = os.path.join(temp_dir, 'converted_files.zip')
    # Zip all files in the 'converted' directory and save it in the temporary directory
    shutil.make_archive(zip_filename[:-4], 'zip', cv_dir)
    shutil.rmtree(cv_dir) # Clean up 'converted' dir
    return send_file(zip_filename, as_attachment=True) # Return zip file


def process_params():
    uploaded_files = request.files.getlist('files')
    format = request.form.get('conversionType')
    conv_key: str = os.urandom(4).hex() # Achieve some convert-session specificity; 4 Bytes = 8 chars (collision within 26^8 is unlikely)
    # These are necessary because uploaded files are 'dumped' in there; Names may collide because of this, so we separate them from beginning
    up_dir: str = f'{app.config['UPLOADED_FILES_DEST']}_{conv_key}' # separate upload directories for each conversion session
    cv_dir: str = f'{app.config['CONVERTED_FILES_DEST']}_{conv_key}'# separate converted directories for each conversion session

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


@app.route('/')
def index():
    return render_template('index.html', title='Any_To_Any.py', options=any_to_any.supported_formats)


def send_off(inputs: list, format: str, output: str, framerate: int, quality: str, merge: bool, concat: bool) -> None:
    # A bit hacky, but now centralized point to talk to any-to-any.py backend
    any_to_any.run(inputs=inputs,
                   format=format, 
                   output=output,  
                   framerate=framerate,
                   quality=quality,
                   merge=merge,
                   concat=concat,
                   delete=True)
    # Remove the upload dir and contents therein
    shutil.rmtree(inputs)


@app.route('/convert', methods=['POST'])
def convert():
    format, up_dir, cv_dir = process_params()
    # Convert all files uploaded to the 'uploads' directory and save it in the 'converted' directory
    send_off(inputs=[up_dir], format=format, output=cv_dir, framerate=None, quality=None, merge=None, concat=None)
    return create_send_zip(cv_dir)


@app.route('/merge', methods=['POST'])
def merge():
    _, up_dir, cv_dir = process_params()
    # Merge all files in the 'uploads' directory and save it in the 'converted' directory
    send_off(inputs=[up_dir], format=None, output=cv_dir, framerate=None, quality=None, merge=True, concat=None)
    return create_send_zip(cv_dir)


@app.route('/concat', methods=['POST'])
def concat():
    _, up_dir, cv_dir = process_params()
    # Concatenation is always done with the same format, we just don't explicitly care here which format that is
    send_off(inputs=[up_dir], format=None, output=cv_dir, framerate=None, quality=None, merge=None, concat=True)
    return create_send_zip(cv_dir)


if __name__ == '__main__':
    webbrowser.open(f'http://{host}:{port}/')
    app.run(debug=True, host=host, port=port)