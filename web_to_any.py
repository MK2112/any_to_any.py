import os
import flask
from any_to_any import AnyToAny
from flask import Flask, render_template, request, send_file
from werkzeug.datastructures import  FileStorage
from flask_uploads import UploadSet, configure_uploads, ALL # pip install Flask-Reuploaded
import shutil
import tempfile
import requests
import jinja2

"""
This is a web server providing a web interface as extension to the CLI-based any-to-any.py
"""

app = Flask(__name__, template_folder=os.path.abspath('templates'))
host = '127.0.0.1'
port = 5000
any_to_any = AnyToAny()


files = UploadSet('files', ALL)
app.config['UPLOADED_FILES_DEST'] = 'uploads'
app.config['CONVERTED_FILES_DEST'] = 'converted'
configure_uploads(app, files)


@app.before_first_request
def before_first_request():
    # Make sure the upload and converted directories exist
    if not os.path.exists(app.config['UPLOADED_FILES_DEST']):
        os.makedirs(app.config['UPLOADED_FILES_DEST'])

    if not os.path.exists(app.config['CONVERTED_FILES_DEST']):
        os.makedirs(app.config['CONVERTED_FILES_DEST'])

    # This helps any_to_any to allocate cache memory early
    _ = any_to_any.supported_formats


def create_and_send_zip():
    # Create a temporary directory for the zip file
    temp_dir = tempfile.mkdtemp()
    zip_filename = os.path.join(temp_dir, 'converted_files.zip')
    # Zip all files in the 'converted' directory and save it in the temporary directory
    shutil.make_archive(zip_filename[:-4], 'zip', app.config['CONVERTED_FILES_DEST'])
    # Clear output dir
    for file in os.listdir(app.config['CONVERTED_FILES_DEST']):
        os.remove(os.path.join(app.config['CONVERTED_FILES_DEST'], file))
    # Return zip file
    return send_file(zip_filename, as_attachment=True)


def process_params():
    uploaded_files = request.files.getlist('files')
    uploaded_filenames = []

    format = request.form.get('conversionType')

    for file in uploaded_files:
        if file:
            filename = os.path.join(app.config['UPLOADED_FILES_DEST'], file.filename)
            file.save(filename)
            uploaded_filenames.append(file.filename)
    
    # file format to convert to
    return format


@app.route('/')
def index():
    return render_template('index.html', title='Any_To_Any.py', options=any_to_any.supported_formats)


@app.route('/convert', methods=['POST'])
def convert():
    format = process_params()
    any_to_any.convert(input=app.config['UPLOADED_FILES_DEST'],
                       format=format, 
                       output=app.config['CONVERTED_FILES_DEST'],  
                       framerate=None,
                       quality=None,
                       merge=None,
                       delete=True)

    # Send zip file
    return create_and_send_zip()


@app.route('/merge', methods=['POST'])
def merge():
    _ = process_params()

    any_to_any.convert(input=app.config['UPLOADED_FILES_DEST'],
                       format=None, 
                       output=app.config['CONVERTED_FILES_DEST'],  
                       framerate=None,
                       quality=None,
                       merge=True,
                       delete=True)

    # Send zip file
    return create_and_send_zip()


if __name__ == '__main__':
    app.run(debug=True, host=host, port=port)