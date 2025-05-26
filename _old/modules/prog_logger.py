import time
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
        if bar == 'chunk' and attr == 'index':
            if self.start_time is None:
                self.start_time = time.time()
                self.last_print_time = self.start_time
                total = self.bars[bar]['total']
                self.tqdm_bar = tqdm(total=total, desc="Processing", unit="chunks")
                # Initialize web progress info
                if self.job_id and self.shared_progress_dict is not None:
                    self.shared_progress_dict[self.job_id].update({
                        'progress': 0,
                        'total': total,
                        'status': 'processing',
                        'error': None
                    })

            # Update our replacing tqdm bar
            if value > (old_value or 0):
                self.tqdm_bar.update(value - (old_value or 0))
                # Update web progress
                if self.job_id and self.shared_progress_dict is not None:
                    self.shared_progress_dict[self.job_id].update({
                        'progress': value,
                        'total': self.bars[bar]['total'],
                        'status': 'processing',
                        'error': None
                    })

            # Handle bar completion
            if value == self.bars[bar]['total']:
                self.tqdm_bar.close()
                if self.job_id and self.shared_progress_dict is not None:
                    self.shared_progress_dict[self.job_id].update({
                        'progress': value,
                        'total': self.bars[bar]['total'],
                        'status': 'done',
                        'error': None
                    })

    def set_error(self, error_msg):
        if self.job_id and self.shared_progress_dict is not None:
            self.shared_progress_dict[self.job_id].update({
                'status': 'error',
                'error': error_msg
            })
