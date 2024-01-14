function submitForm(endpoint) {
    // Selected conversion option and FormData object
    var conversion_type = document.getElementById('conversion-type').value;
    var form_data = new FormData(document.getElementById('conversion-form'));

    // Append selected conversion type
    form_data.append('conversionType', conversion_type);

    var xhr = new XMLHttpRequest();
    xhr.open('POST', endpoint, true);

    // Progress for file conversion (not upload)
    showLoader();

    // Take backend response .zip, rename the file, make it downloadable
    xhr.onload = function () {
        if (xhr.status === 200) {
            hideLoader();
            var blob = new Blob([xhr.response], { type: 'application/octet-stream' });
            var link = document.createElement('a');
            link.href = window.URL.createObjectURL(blob);
            var timestamp = new Date().toISOString().replace(/[-T:Z]/g, '');
            var file_name = 'any_to_any-' + timestamp + '.zip';
            link.download = file_name
            link.click(); // Offer .zip for download
        } else {
            hideLoader();
            alert('Error Uploading Files. Please Try Again.');
        }
    };

    xhr.onerror = function () {
        hideLoader();
        alert('Communication To Backend Failed. Please Try Again.');
    };

    // Provide form contents to backend
    xhr.responseType = 'arraybuffer';
    xhr.send(form_data);

    // Reset file input list
    document.getElementById('files').value = null;
    var file_list = document.getElementById('file-list');
    file_list.innerHTML = '';
}


function triggerUploadDialogue(event) {
    if (event.target.tagName !== 'INPUT') {
        document.getElementById('files').click();
    }
}

function allowDrop(event) {
    event.preventDefault();
}

function drop(event) {
    event.preventDefault();
    var files = event.dataTransfer.files;
    handleFiles(files, false);
}

function handleFiles(files, fromInput) {
    if (!fromInput) {
        // handleFiles not called from within input element, we have to add files to it then
        var input = document.getElementById('files');
        input.files = files;
    }

    // Adding file names to the file-list ul
    var fileList = document.getElementById('file-list');
    fileList.innerHTML = '';

    for (var i = 0; i < files.length; i++) {
        var li = document.createElement('li');
        li.textContent = files[i].name;
        fileList.appendChild(li);
    }
}

function showLoader() {
    document.getElementById('loader').style.display = 'block';
}

function hideLoader() {
    document.getElementById('loader').style.display = 'none';
}