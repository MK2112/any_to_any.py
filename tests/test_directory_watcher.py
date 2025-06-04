"""Tests for the DirectoryWatcher class."""
import time
import pytest
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock

# Add parent directory to path to allow importing from core
import sys
sys.path.append(str(Path(__file__).parent.parent))

from core.utils.directory_watcher import DirectoryWatcher

class TestDirectoryWatcher:
    """Test suite for DirectoryWatcher class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create and clean up a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    def test_initialization(self, temp_dir):
        """Test DirectoryWatcher initialization."""
        callback = MagicMock()
        watcher = DirectoryWatcher(str(temp_dir), callback)
        
        assert watcher.watch_path == temp_dir
        assert watcher.recursive is True
        assert watcher.is_running() is False

    def test_start_stop(self, temp_dir):
        """Test starting and stopping the watcher."""
        callback = MagicMock()
        watcher = DirectoryWatcher(str(temp_dir), callback)
        
        # Start the watcher
        watcher.start()
        assert watcher.is_running() is True
        
        # Stop the watcher
        watcher.stop()
        assert watcher.is_running() is False

    def test_context_manager(self, temp_dir):
        """Test using DirectoryWatcher as a context manager."""
        callback = MagicMock()
        
        with DirectoryWatcher(str(temp_dir), callback) as watcher:
            assert watcher.is_running() is True
        
        # Should be stopped after context
        assert watcher.is_running() is False

    def test_file_creation_event(self, temp_dir):
        """Test that file creation triggers the callback."""
        callback = MagicMock()
        
        with DirectoryWatcher(str(temp_dir), callback) as _:
            # Create a test file
            test_file = temp_dir / "test.txt"
            test_file.touch()
            
            # Give the watcher time to detect the change
            time.sleep(0.5)
            
            # Check callback was called
            callback.assert_called_once()
            event_type, file_path = callback.call_args[0]
            assert event_type == 'created'
            assert str(file_path) == str(test_file)

    def test_file_modification_event(self, temp_dir):
        """Test that file modification triggers the callback."""
        # First create a file
        test_file = temp_dir / "test.txt"
        test_file.touch()
        
        # Wait for any initial events to pass
        time.sleep(0.5)
        
        callback = MagicMock()
        
        with DirectoryWatcher(str(temp_dir), callback) as _:
            # Modify the file
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("test content")
            
            # Give the watcher time to detect the change
            time.sleep(0.5)
            
            # Check callback was called with modification event
            callback.assert_called()
            event_type, file_path = callback.call_args[0]
            assert event_type == 'modified'
            assert str(file_path) == str(test_file)

    def test_non_recursive_watch(self, temp_dir):
        """Test that non-recursive watch only watches the top level."""
        # Create a subdirectory
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        
        callback = MagicMock()
        
        # Watch non-recursively
        with DirectoryWatcher(str(temp_dir), callback, recursive=False) as _:
            # Create a file in the subdirectory (should not trigger)
            test_file = subdir / "test.txt"
            test_file.touch()
            
            # Create a file in the watched directory (should trigger)
            top_file = temp_dir / "top.txt"
            top_file.touch()
            
            # Give the watcher time to detect changes
            time.sleep(0.5)
            
            # Only the top-level file should trigger the callback
            assert callback.call_count == 1
            event_type, file_path = callback.call_args[0]
            assert str(file_path) == str(top_file)

    def test_watch_method(self, temp_dir):
        """Test the blocking watch method."""
        callback = MagicMock()
        
        # Start the watcher in a separate thread
        def watch():
            with DirectoryWatcher(str(temp_dir), callback) as watcher:
                watcher.watch(interval=0.1)
        
        thread = threading.Thread(target=watch)
        thread.daemon = True
        thread.start()
        
        try:
            # Give the watcher time to start
            time.sleep(0.5)
            
            # Create a test file
            test_file = temp_dir / "test.txt"
            test_file.touch()
            
            # Give the watcher time to detect the change
            time.sleep(0.5)
            
            # Check callback was called
            callback.assert_called_once()
            
        finally:
            # Stop the watcher by interrupting the thread
            thread.join(timeout=1)
            if thread.is_alive():
                # If thread is still alive, it means join timed out
                thread.join(timeout=0.1)  # Give it a bit more time

    def test_error_handling(self, temp_dir):
        """Test that errors in the callback don't crash the watcher."""
        def error_callback(event_type, file_path):
            if "error" in str(file_path):
                raise ValueError("Test error")
        
        with DirectoryWatcher(str(temp_dir), error_callback) as watcher_obj:
            # This should not raise an exception
            test_file = temp_dir / "test.txt"
            test_file.touch()
            
            # This would raise if not handled
            error_file = temp_dir / "error.txt"
            error_file.touch()
            
            # Give the watcher time to process
            time.sleep(0.5)
            
            # Watcher should still be running
            assert watcher_obj.is_running() is True

    def test_multiple_events(self, temp_dir):
        """Test handling of multiple file events."""
        events = []
        
        def callback(event_type, file_path):
            events.append((event_type, str(file_path)))
        
        with DirectoryWatcher(str(temp_dir), callback) as watcher:
            # Create multiple files
            for i in range(3):
                test_file = temp_dir / f"test_{i}.txt"
                test_file.touch()
                time.sleep(0.1)  # Small delay between events
            
            # Give the watcher time to process
            time.sleep(0.5)
            
            # Should have 3 creation events
            assert len(events) == 3
            for i, (event_type, file_path) in enumerate(events):
                assert event_type == 'created'
                assert file_path == str(temp_dir / f"test_{i}.txt")