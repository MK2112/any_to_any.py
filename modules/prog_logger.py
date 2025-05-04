import time
from tqdm import tqdm
from proglog import ProgressBarLogger

class ProgLogger(ProgressBarLogger):
    """ Custom logger extracting progress info from moviepy video processing operations"""
    def __init__(self):
        super().__init__()
        self.start_time, self.last_print_time = None, None
        self.print_interval = 0.1  # Frequency of progress updates
        self.tqdm_bar = None

    def bars_callback(self, bar, attr, value, old_value=None):
        if bar == 'chunk' and attr == 'index':
            if self.start_time is None:
                self.start_time = time.time()
                self.last_print_time = self.start_time
                total = self.bars[bar]['total']
                self.tqdm_bar = tqdm(total=total, desc="Processing", unit="chunks")

            # Update our replacing tqdm bar
            # Kind of nonsensical at this point, but we now got the progress info
            if value > (old_value or 0):
                self.tqdm_bar.update(value - (old_value or 0))

            # Handle bar completion
            if value == self.bars[bar]['total']:
                self.tqdm_bar.close()
                #print(f"Processing complete! Time elapsed: {time.time() - self.start_time:.2f}s")
