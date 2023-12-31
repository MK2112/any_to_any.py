import os
from any_to_any import AnyToAny
from flask import Flask, render_template, request, send_file
from flask_uploads import UploadSet, configure_uploads, ALL # pip install Flask-Reuploaded
import shutil
import tempfile

"""
Web server providing a web interface as extension to the CLI-based any-to-any.py
"""

# Flask configuration
app = Flask(__name__, template_folder=os.path.abspath('templates'))
host = '127.0.0.1'
port = 5000
any_to_any = AnyToAny()

# Flask-Uploads configuration
files = UploadSet('files', ALL)
app.config['UPLOADED_FILES_DEST'] = 'uploads'
app.config['CONVERTED_FILES_DEST'] = 'converted'
configure_uploads(app, files)


with app.app_context():
    # Make sure the upload and converted file dirs exist
    if not os.path.exists(app.config['UPLOADED_FILES_DEST']):
        os.makedirs(app.config['UPLOADED_FILES_DEST'])
    if not os.path.exists(app.config['CONVERTED_FILES_DEST']):
        os.makedirs(app.config['CONVERTED_FILES_DEST'])
    # This helps any_to_any to allocate memory early on
    _ = any_to_any.supported_formats


def create_and_send_zip():
    # Temporary directory for the zip file
    temp_dir = tempfile.mkdtemp()
    zip_filename = os.path.join(temp_dir, 'converted_files.zip')
    # Zip all files in the 'converted' directory and save it in the temporary directory
    shutil.make_archive(zip_filename[:-4], 'zip', app.config['CONVERTED_FILES_DEST'])
    for file in os.listdir(app.config['CONVERTED_FILES_DEST']):
        os.remove(os.path.join(app.config['CONVERTED_FILES_DEST'], file))
    return send_file(zip_filename, as_attachment=True) # Return zip file


def process_params():
    uploaded_files = request.files.getlist('files')
    format = request.form.get('conversionType')
    for file in uploaded_files:
        if file:
            filename = os.path.join(app.config['UPLOADED_FILES_DEST'], file.filename)
            file.save(filename)
    return format # File format to convert to


@app.route('/')
def index():
    return render_template('index.html', title='Any_To_Any.py', options=any_to_any.supported_formats)


@app.route('/convert', methods=['POST'])
def convert():
    format = process_params()
    any_to_any.run(input=app.config['UPLOADED_FILES_DEST'],
                       format=format, 
                       output=app.config['CONVERTED_FILES_DEST'],  
                       framerate=None,
                       quality=None,
                       merge=None,
                       concat=None,
                       delete=True)
    return create_and_send_zip()


@app.route('/merge', methods=['POST'])
def merge():
    _ = process_params() # Ignore format, we're merging anyway
    any_to_any.run(input=app.config['UPLOADED_FILES_DEST'],
                       format=None, 
                       output=app.config['CONVERTED_FILES_DEST'],  
                       framerate=None,
                       quality=None,
                       merge=True,
                       concat=False,
                       delete=True)
    return create_and_send_zip()


@app.route('/concat', methods=['POST'])
def concat():
    _ = process_params() # Ignore format again, backend will figure out details
    any_to_any.run(input=app.config['UPLOADED_FILES_DEST'],
                       format=None, 
                       output=app.config['CONVERTED_FILES_DEST'],  
                       framerate=None,
                       quality=None,
                       merge=False,
                       concat=True,
                       delete=True)
    return create_and_send_zip()


if __name__ == '__main__':
    app.run(debug=True, host=host, port=port)