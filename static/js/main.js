// Accumulate all selected/dropped files in this array
let uploadedFiles = [];

function submitForm(endpoint) {
    const conversionType = document.getElementById('conversion-type').value;
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressStatus = document.getElementById('progress-status');
    const errorMessage = document.getElementById('error-message');
    const jobIdInput = document.getElementById('job-id');

    if (uploadedFiles.length === 0) {
        alert('No files selected!');
        return;
    }

    // Reset UI for new conversion
    progressContainer.style.display = 'none';
    progressBar.style.width = '0';
    progressStatus.textContent = '';
    errorMessage.style.display = 'none';
    errorMessage.textContent = '';
    jobIdInput.value = '';

    // Build FormData from our global array
    const form_data = new FormData();
    uploadedFiles.forEach(file => form_data.append('files', file));
    form_data.append('conversionType', conversionType);

    // Will leave that, shows activity before actual conversion
    showLoader();

    // Fetch from API for JSON parsing
    fetch(endpoint, {
        method: 'POST',
        body: form_data
    })
    .then(response => {
        hideLoader();
        if (response.status === 202) {
            return response.json();
        } else {
            throw new Error('Failed to start conversion.');
        }
    })
    .then(data => {
        if (!data.job_id) throw new Error('No job_id returned.');
        jobIdInput.value = data.job_id;
        pollProgress(data.job_id, endpoint);
    })
    .catch(err => {
        errorMessage.style.display = 'block';
        errorMessage.textContent = err.message;
    });

    // Reset state
    uploadedFiles = [];
    document.getElementById('file-list').innerHTML = '';
}

function pollProgress(jobId, endpoint) {
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressStatus = document.getElementById('progress-status');
    const errorMessage = document.getElementById('error-message');

    progressContainer.style.display = 'block';
    progressBar.style.width = '0';
    progressStatus.textContent = 'Starting...';
    errorMessage.style.display = 'none';
    errorMessage.textContent = '';

    let lastProgress = 0;
    let pollInterval = setInterval(() => {
        fetch(`/progress/${jobId}`)
            .then(resp => {
                if (!resp.ok) throw new Error('Progress not found.');
                return resp.json();
            })
            .then(data => {
                if (data.status === 'error') {
                    clearInterval(pollInterval);
                    progressContainer.style.display = 'none';
                    errorMessage.style.display = 'block';
                    errorMessage.textContent = data.error || 'An error occurred.';
                    return;
                }
                // Update progress bar
                let percent = 0;
                if (data.total && data.total > 0) {
                    percent = Math.round((data.progress / data.total) * 100);
                }
                progressBar.style.width = percent + '%';
                progressStatus.textContent = data.status === 'done' ? 'Finishing up...' : `Processing: ${percent}%`;
                lastProgress = percent;

                if (data.status === 'done') {
                    clearInterval(pollInterval);
                    progressStatus.textContent = 'Preparing download...';
                    setTimeout(() => {
                        fetch(`/download/${jobId}`)
                            .then(resp => {
                                if (!resp.ok) throw new Error('Download failed.');
                                return resp.blob();
                            })
                            .then(blob => {
                                const link = document.createElement('a');
                                link.href = window.URL.createObjectURL(blob);
                                const timestamp = new Date().toISOString().replace(/[-T:Z]/g, '');
                                link.download = `any_to_any-${timestamp}.zip`;
                                link.click();
                                progressContainer.style.display = 'none';
                                progressBar.style.width = '0';
                                progressStatus.textContent = '';
                            })
                            .catch(err => {
                                errorMessage.style.display = 'block';
                                errorMessage.textContent = err.message;
                                progressContainer.style.display = 'none';
                            });
                    }, 500);
                }
            })
            .catch(err => {
                clearInterval(pollInterval);
                errorMessage.style.display = 'block';
                errorMessage.textContent = err.message;
                progressContainer.style.display = 'none';
            });
    }, 500);
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
