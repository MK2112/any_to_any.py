// Language detection and forwarding
let resolutionData = null;

document.addEventListener('DOMContentLoaded', function() {
    // Only send if not already set in session (could check via a cookie or a hidden field)
    if (!window.sessionStorage.getItem('languageSet')) {
        var lang = navigator.language || navigator.userLanguage || 'en_US';
        var csrfInput = document.querySelector('input[name="csrf_token"]');
        fetch('/language', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                language: lang.replace('-', '_'),
                csrf_token: csrfInput ? csrfInput.value : ''
            })
        }).then(function(response) {
            if (response.ok) {
                window.sessionStorage.setItem('languageSet', '1');
                // Reload the page to apply new language if needed
                window.location.reload();
            }
        });
    }

    // Resolution controls (the JSON block lives below in the body)
    const dataEl = document.getElementById('resolution-data');
    if (dataEl) {
        resolutionData = JSON.parse(dataEl.textContent);
        updateResolutionOptions();
        document.getElementById('conversion-type').addEventListener('change', updateResolutionOptions);
    }
});

// Populate the resolution dropdown with the given allowed values
function buildResolutionOptions(allowed) {
    const select = document.getElementById('conversion-resolution');
    const previous = select.value;
    select.innerHTML = '';
    const keep = document.createElement('option');
    keep.value = '';
    keep.textContent = resolutionData.strings.resolution_original;
    select.appendChild(keep);
    allowed.forEach(res => {
        const opt = document.createElement('option');
        opt.value = res;
        opt.textContent = res;
        select.appendChild(opt);
    });
    // Keep the current choice only if it is still valid, otherwise reset
    select.disabled = allowed.length === 0;
    if (allowed.includes(previous)) {
        select.value = previous;
    }
}

// Valid movie extensions among the uploaded files
function uploadedMovieExtensions() {
    const exts = new Set();
    uploadedFiles.forEach(file => {
        const dot = file.name.lastIndexOf('.');
        if (dot >= 0) {
            const ext = file.name.slice(dot + 1).toLowerCase();
            if (resolutionData.movies[ext]) exts.add(ext);
        }
    });
    return exts;
}

// The resolution row is only shown when it can actually be applied
function setResolutionRowVisible(visible) {
    const select = document.getElementById('conversion-resolution');
    const label = document.getElementById('conversion-resolution-label');
    if (!visible) select.value = '';
    select.hidden = !visible;
    label.hidden = !visible;
}

// Refill the resolution dropdown for the currently selected target format
function updateResolutionOptions() {
    if (!resolutionData) return;
    const format = document.getElementById('conversion-type').value;
    if (format === 'original') {
        // Resize-only: restrict to what the uploaded movies themselves allow
        const exts = uploadedMovieExtensions();
        const union = new Set();
        exts.forEach(ext => resolutionData.movies[ext].forEach(r => union.add(r)));
        if (union.size === 0) {
            setResolutionRowVisible(false);
            return;
        }
        const allowed = resolutionData.ladder.filter(r => union.has(r));
        buildResolutionOptions(allowed);
        setResolutionRowVisible(true);
    } else {
        const allowed = resolutionData.formats[format] || [];
        buildResolutionOptions(allowed);
        setResolutionRowVisible(allowed.length > 0);
    }
}

// Accumulate all selected/dropped files in this array
let uploadedFiles = [];

function submitForm(endpoint) {
    const conversionType = document.getElementById('conversion-type').value;
    const progressContainer = document.getElementById('progress-container');
    const errorMessage = document.getElementById('error-message');
    const csrfInput = document.querySelector('input[name="csrf_token"]');

    if (uploadedFiles.length === 0) {
        errorMessage.style.display = 'block';
        errorMessage.textContent = 'Please select at least one file';
        return;
    }

    // Resize-only (keep the source format) requires a chosen resolution
    if (conversionType === 'original' && resolutionData) {
        const resolutionSelect = document.getElementById('conversion-resolution');
        if (resolutionSelect.value === '') {
            errorMessage.style.display = 'block';
            errorMessage.textContent = resolutionSelect.hidden
                ? resolutionData.strings.movies_required
                : resolutionData.strings.resolution_required;
            return;
        }
    }

    // Reset UI
    progressContainer.style.display = 'none';
    errorMessage.style.display = 'none';
    errorMessage.textContent = '';

    // Prepare form data
    const formData = new FormData();
    if (csrfInput) formData.append('csrf_token', csrfInput.value);
    uploadedFiles.forEach(file => formData.append('files', file));
    formData.append('conversionType', conversionType);
    // Merge/concat do not resize; only conversions apply a resolution
    if (endpoint === '/convert') {
        formData.append('resolution', document.getElementById('conversion-resolution').value);
    }

    // Show loading state
    showLoader();

    // Start conversion
    fetch(endpoint, {
        method: 'POST',
        body: formData
    })
    .then(response => {
        hideLoader();
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (!data.job_id) {
            throw new Error('No job ID received from server');
        }
        if (data.csrf_token && csrfInput) {
            csrfInput.value = data.csrf_token;
        }
        pollProgress(data.job_id);
    })
    .catch(error => {
        hideLoader();
        errorMessage.style.display = 'block';
        errorMessage.textContent = `Error: ${error.message}`;
        console.error('Conversion error:', error);
    })
    .finally(() => {
        uploadedFiles = [];
        document.getElementById('file-list').innerHTML = '';
    });
}

function pollProgress(jobId) {
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressStatus = document.getElementById('progress-status');
    const errorMessage = document.getElementById('error-message');

    // Show progress UI
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    progressStatus.textContent = '';
    errorMessage.style.display = 'none';
    errorMessage.textContent = '';

    // Start polling for progress
    const pollInterval = setInterval(() => {
        fetch(`/progress/${jobId}`)
            .then(response => {
                if (!response.ok) throw new Error('Failed to get progress');
                return response.json();
            })
            .then(data => {
                // Handle error state
                if (data.status === 'error') {
                    throw new Error(data.error || 'Conversion failed');
                }

                // Update progress using progress_percent if available, otherwise calculate from progress/total
                let percent = 0;
                if (data.progress_percent !== undefined) {
                    percent = Math.min(100, Math.max(0, data.progress_percent));
                } else if (data.total > 0) {
                    percent = Math.min(100, Math.max(0, Math.round((data.progress / data.total) * 100)));
                }
                
                // Smooth animation for progress bar
                const currentWidth = parseFloat(progressBar.style.width) || 0;
                if (Math.abs(percent - currentWidth) > 1) {
                    progressBar.style.transition = 'width 0.3s ease-in-out';
                    progressBar.style.width = `${percent}%`;
                } else if (progressBar.style.transition) {
                    // Remove transition for small updates to prevent stuttering
                    progressBar.style.transition = 'none';
                    progressBar.style.width = `${percent}%`;
                } else {
                    progressBar.style.width = `${percent}%`;
                }
                
                // Update status text with more detailed information
                let statusText = `${percent}%`;
                if (data.status === 'processing' && data.current_bar) {
                    statusText += ` (${data.current_bar})`;
                }
                progressStatus.textContent = statusText; 
                if (percent > 0 && percent < 100) {
                    progressBar.classList.add('active');
                } else {
                    progressBar.classList.remove('active');
                }

                // Handle completion
                if (data.status === 'done') {
                    clearInterval(pollInterval);
                    progressStatus.textContent = '';
                    window.location.href = `/download/${jobId}`;
                    
                    // Reset UI and file inputs after a short delay
                    setTimeout(() => {
                        progressContainer.style.display = 'none';
                        progressBar.style.width = '0%';
                        progressStatus.textContent = '';
                        // Clear selected files array and visible file list
                        uploadedFiles = [];
                        const fileListEl = document.getElementById('file-list');
                        if (fileListEl) fileListEl.innerHTML = '';
                        // Reset file input element so same files can be reselected
                        const fileInput = document.getElementById('files');
                        if (fileInput) fileInput.value = '';
                        // Clear any stored job id
                        const jobIdInput = document.getElementById('job-id');
                        if (jobIdInput) jobIdInput.value = '';
                    }, 2000);
                }
            })
            .catch(error => {
                clearInterval(pollInterval);
                errorMessage.style.display = 'block';
                errorMessage.textContent = error.message || 'An error occurred during conversion';
                progressContainer.style.display = 'none';
                // On error also reset file selection so user can try again
                uploadedFiles = [];
                const fileListEl = document.getElementById('file-list');
                if (fileListEl) fileListEl.innerHTML = '';
                const fileInput = document.getElementById('files');
                if (fileInput) fileInput.value = '';
                const jobIdInput = document.getElementById('job-id');
                if (jobIdInput) jobIdInput.value = '';
            });
    }, 500); // Poll every 500ms
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

    // Resize-only options depend on which movie formats were uploaded
    updateResolutionOptions();
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
