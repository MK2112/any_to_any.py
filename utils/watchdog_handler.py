from watchdog.events import FileSystemEventHandler

class WatchDogFileHandler(FileSystemEventHandler):
    def __init__(self, inner):
        self.inner = inner

    def on_created(self, event):
        if event.is_directory:
            return
        file_path = event.src_path
        # log with the inner’s logger, and trigger its run()
        self.inner.event_logger.info(f"[+] New file detected in dropzone: {file_path}")
        self.inner.run([file_path],
                    format=self.inner.format,
                    output=self.inner.output,
                    framerate=self.inner.framerate,
                    quality=self.inner.quality,
                    merge=self.inner.merging,
                    concat=self.inner.concatenating,
                    delete=self.inner.delete,
                    across=self.inner.across,
                    recursive=self.inner.recursive,
                    dropzone=False)