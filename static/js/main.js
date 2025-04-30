// Accumulate all selected/dropped files in this array
let uploadedFiles = [];

function submitForm(endpoint) {
    const conversionType = document.getElementById('conversion-type').value;
    
    if (uploadedFiles.length === 0) {
        alert('No files selected!');
        return;
    }

    // Build FormData from our global array
    // Basis for formulating POST request
    const form_data = new FormData();
    // Append each file to the FormData object
    uploadedFiles.forEach(file => form_data.append('files', file));
    // Append the conversion type to the FormData object
    form_data.append('conversionType', conversionType);

    const xhr = new XMLHttpRequest();
    // Hand off the FormData to the server
    xhr.open('POST', endpoint, true);
    // loader animation for the user during processing
    showLoader();

    xhr.onload = function () {
        hideLoader();
        // If successful, the server should return a zip file
        // We hand that off to the browser to download
        if (xhr.status === 200) {
            const blob = new Blob([xhr.response], { type: 'application/octet-stream' });
            const link = document.createElement('a');
            link.href = window.URL.createObjectURL(blob);
            const timestamp = new Date().toISOString().replace(/[-T:Z]/g, '');
            link.download = `any_to_any-${timestamp}.zip`;
            link.click();
        } else {
            alert('Error Uploading Files.');
        }
    };

    xhr.onerror = function () {
        hideLoader();
        alert('Conversion Failed. Provided File May Be Corrupted/Incomplete or Upload Failed.');
    };

    xhr.responseType = 'arraybuffer';
    xhr.send(form_data);

    // Reset state
    uploadedFiles = [];
    document.getElementById('file-list').innerHTML = '';
}

function triggerUploadDialogue(event) {
    // Trigger the file input click when the drop area is clicked
    // This allows the user to select files from their file system
    // with a button click additionally to drag and drop
    if (event.target.tagName !== 'INPUT') {
        document.getElementById('files').click();
    }
}

function allowDrop(event) {
    // Allow dropping files into the drop area
    event.preventDefault();
}

function drop(event) {
    // Prevent file from being opened
    event.preventDefault();
    handleFiles(event.dataTransfer.files, false);
}

function handleFiles(files, fromInput) {
    // If files come from the <input>, replace entire array; on drop, append
    if (fromInput) {
        uploadedFiles = Array.from(files);
    } else {
        // Append new files, avoid exact duplicates by name+size
        Array.from(files).forEach(f => {
            if (!uploadedFiles.some(existing => existing.name === f.name && existing.size === f.size)) {
                uploadedFiles.push(f);
            }
        });
    }

    // Update visible file list
    const fileList = document.getElementById('file-list');
    fileList.innerHTML = '';
    // Show the names of the files selected in the drop area
    uploadedFiles.forEach(f => {
        const li = document.createElement('li');
        li.textContent = f.name;
        fileList.appendChild(li);
    });
}

// Show the loader animation
function showLoader() {
    document.getElementById('loader').style.display = 'block';
}

// Hide the loader animation
function hideLoader() {
    document.getElementById('loader').style.display = 'none';
}

// Wiring up the <input> change to our handler
document.getElementById('files').addEventListener('change', function() {
    handleFiles(this.files, true);
});
