function submitForm(endpoint) {
    // Selected conversion option and FormData object
    var conversion_type = document.getElementById('conversion-type').value;
    var form_data = new FormData(document.getElementById('conversion-form'));

    // Append selected conversion type
    form_data.append('conversionType', conversion_type);

    // Create XMLHttpRequest
    var xhr = new XMLHttpRequest();
    xhr.open('POST', endpoint, true);

    // Define the onload and onerror functions
    xhr.onload = function () {
        if (xhr.status === 200) {
            var blob = new Blob([xhr.response], { type: 'application/octet-stream' });
            var link = document.createElement('a');
            link.href = window.URL.createObjectURL(blob);
            var timestamp = new Date().toISOString().replace(/[-T:Z]/g, '');
            var file_name = 'any_to_any-' + timestamp + '.zip';
            link.download = file_name
            link.click(); // Download the file
        } else {
            alert('Error uploading files. Please try again.');
        }
    };

    xhr.onerror = function () {
        alert('File transmission failed. Please try again.');
    };

    // Send the FormData
    xhr.responseType = 'arraybuffer';
    xhr.send(form_data);

    // Reset file input and file-list ul
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
    handleFiles(files);
}

function handleFiles(files) {
    // Adding file names to the file-list ul
    var file_list = document.getElementById('file-list');
    file_list.innerHTML = '';

    for (var i = 0; i < files.length; i++) {
        var li = document.createElement('li');
        li.textContent = files[i].name;
        file_list.appendChild(li);
    }
}