import time
import threading
from tqdm import tqdm
from proglog import ProgressBarLogger

class ProgLogger(ProgressBarLogger):
    # Custom logger extracting progress info from moviepy video processing operations.
    # Optionally writes progress to a shared dict for web reporting
    def __init__(self, job_id=None, shared_progress_dict=None):
        super().__init__()
        self.start_time, self.last_print_time = None, None
        self.print_interval = 0.1  # Frequency of progress updates in seconds
        self.tqdm_bar = None
        self.job_id = job_id
        self.shared_progress_dict = shared_progress_dict
        if self.job_id and self.shared_progress_dict is not None:
            self.shared_progress_dict[self.job_id] = {
                'progress': 0,
                'total': 1,
                'status': 'starting',
                'error': None
            }

    def bars_callback(self, bar, attr, value, old_value=None):
        current_time = time.time()
        
        # Initialize if this is the first time we're seeing this bar
        if bar not in self.bars:
            return
            
        # Only process index updates for progress tracking
        if attr != 'index':
            return
            
        # Initialize progress tracking if this is the first update
        if self.start_time is None:
            self.start_time = current_time
            self.last_print_time = self.start_time
            total = self.bars[bar].get('total', 100)  # Default to 100 if total not available
            
            # Initialize tqdm progress bar
            self.tqdm_bar = tqdm(total=total, unit="chunks")
            
            # Initialize web progress info
            if self.job_id and self.shared_progress_dict is not None:
                with threading.Lock():
                    self.shared_progress_dict[self.job_id] = {
                        'progress': 0,
                        'total': total,
                        'status': 'processing',
                        'error': None,
                        'started_at': current_time,
                        'last_updated': current_time,
                        'current_bar': bar
                    }
        
        # Calculate progress percentage
        total = self.bars[bar].get('total', 100)
        if total > 0:
            progress_percent = int((value / total) * 100)
        else:
            progress_percent = 0
            
        # Update tqdm progress bar
        if value > (old_value or 0):
            if self.tqdm_bar:
                self.tqdm_bar.update(value - (old_value or 0))
            
            # Update web progress, but not too frequently to reduce overhead
            if current_time - self.last_print_time >= 0.1:  # Update at most 10 times per second
                self.last_print_time = current_time
                if self.job_id and self.shared_progress_dict is not None:
                    with threading.Lock():
                        if self.job_id in self.shared_progress_dict:
                            self.shared_progress_dict[self.job_id].update({
                                'progress': value,
                                'total': total,
                                'status': 'processing',
                                'last_updated': current_time,
                                'current_bar': bar,
                                'progress_percent': progress_percent
                            })
                            
                            # Force progress update by modifying the dictionary in-place
                            # This helps with thread safety and ensures the update is visible
                            self.shared_progress_dict[self.job_id] = dict(self.shared_progress_dict[self.job_id])
        
        # Handle bar completion
        if value >= total and self.tqdm_bar:
            self.tqdm_bar.close()
            if self.job_id and self.shared_progress_dict is not None:
                with threading.Lock():
                    if self.job_id in self.shared_progress_dict:
                        self.shared_progress_dict[self.job_id].update({
                            'progress': value,
                            'total': total,
                            'status': 'done',
                            'completed_at': current_time,
                            'last_updated': current_time,
                            'progress_percent': 100
                        })

    def set_error(self, error_msg):
        if self.job_id and self.shared_progress_dict is not None:
            self.shared_progress_dict[self.job_id].update({
                'status': 'error',
                'error': error_msg
            })
