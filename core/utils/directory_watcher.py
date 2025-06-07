import time
from pathlib import Path
from typing import Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class DirectoryWatcher:
    # Watches for file system events in a directory and its subdirectories
    def __init__(self, watch_path: str, event_handler: Callable, recursive: bool = True):
        self.watch_path = Path(watch_path).resolve()
        self.event_handler = event_handler
        self.recursive = recursive
        self.observer: Optional[Observer] = None
        self._running = False

    def start(self) -> None:
        # Start watching the directory
        if self._running:
            return
            
        class Handler(FileSystemEventHandler):
            def _safe_callback(_, callback, *args):
                try:
                    callback(*args)
                except Exception as e:
                    # Log the error but don't let it crash the watcher
                    import logging
                    logging.error(f"Error in directory watcher callback: {e}", exc_info=True)
            
            def on_created(_, event):
                if not event.is_directory:
                    _._safe_callback(self.event_handler, 'created', event.src_path)
                    
            def on_modified(_, event):
                if not event.is_directory:
                    _._safe_callback(self.event_handler, 'modified', event.src_path)

        try:
            self.observer = Observer()
            self.observer.schedule(Handler(), str(self.watch_path), recursive=self.recursive)
            self.observer.start()
            self._running = True
        except Exception as e:
            if self.observer:
                self.observer.stop()
                self.observer = None
            raise RuntimeError(f"Failed to start directory watcher: {e}")

    def stop(self) -> None:
        # Stop watching the directory
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
        self._running = False

    def __enter__(self):
        # Context manager entry
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Context manager exit
        self.stop()

    def is_running(self) -> bool:
        # Check if the watcher is running
        return self._running and self.observer is not None and self.observer.is_alive()

    def watch(self, interval: float = 1.0) -> None:
        # Start watching and block until KeyboardInterrupt
        self.start()
        try:
            while self.is_running():
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
