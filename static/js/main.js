// Language detection and forwarding
document.addEventListener('DOMContentLoaded', function() {
    // Only send if not already set in session (could check via a cookie or a hidden field)
    if (!window.sessionStorage.getItem('languageSet')) {
        var lang = navigator.language || navigator.userLanguage;
        fetch('/language', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({language: lang.replace('-', '_')})
        }).then(function(response) {
            if (response.ok) {
                window.sessionStorage.setItem('languageSet', '1');
                // Reload the page to apply new language if needed
                window.location.reload();
            }
        });
    }
});

// Accumulate all selected/dropped files in this array
let uploadedFiles = [];

function submitForm(endpoint) {
    const conversionType = document.getElementById('conversion-type').value;
    const progressContainer = document.getElementById('progress-container');
    const errorMessage = document.getElementById('error-message');

    if (uploadedFiles.length === 0) {
        errorMessage.style.display = 'block';
        errorMessage.textContent = 'Please select at least one file';
        return;
    }

    // Reset UI
    progressContainer.style.display = 'none';
    errorMessage.style.display = 'none';
    errorMessage.textContent = '';

    // Prepare form data
    const formData = new FormData();
    uploadedFiles.forEach(file => formData.append('files', file));
    formData.append('conversionType', conversionType);

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
        // Start polling for progress
        pollProgress(data.job_id);
    })
    .catch(error => {
        hideLoader();
        errorMessage.style.display = 'block';
        errorMessage.textContent = `Error: ${error.message}`;
        console.error('Conversion error:', error);
    })
    .finally(() => {
        // Reset file list
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
    progressStatus.textContent = 'Starting conversion...';
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
                let statusText = `Processing: ${percent}%`;
                if (data.status === 'processing' && data.current_bar) {
                    statusText += ` (${data.current_bar})`;
                }
                progressStatus.textContent = statusText; 
                
                // Add a visual indicator when progress is stuck
                if (percent > 0 && percent < 100) {
                    progressBar.classList.add('active');
                } else {
                    progressBar.classList.remove('active');
                }

                // Handle completion
                if (data.status === 'done') {
                    clearInterval(pollInterval);
                    progressStatus.textContent = 'Starting Download...';
                    
                    // Trigger download
                    window.location.href = `/download/${jobId}`;
                    
                    // Reset UI after a short delay
                    setTimeout(() => {
                        progressContainer.style.display = 'none';
                        progressBar.style.width = '0%';
                        progressStatus.textContent = '';
                    }, 2000);
                }
            })
            .catch(error => {
                clearInterval(pollInterval);
                errorMessage.style.display = 'block';
                errorMessage.textContent = error.message || 'An error occurred during conversion';
                progressContainer.style.display = 'none';
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
