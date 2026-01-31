import os
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_utility_functions_import():
    from gui.qt_app import load_settings, save_settings, SETTINGS_FILE
    assert callable(load_settings)
    assert callable(save_settings)
    assert isinstance(SETTINGS_FILE, str)


def test_save_and_load_settings():
    from gui.qt_app import load_settings, save_settings  
    # Save test settings
    test_data = {"last_dir": "/tmp/test", "locale": "English"}
    save_settings(test_data)
    # Load and verify
    loaded = load_settings()
    assert loaded.get("last_dir") == "/tmp/test"
    assert loaded.get("locale") == "English"


def test_load_settings_handles_missing_file():
    from gui.qt_app import SETTINGS_FILE
    backup = None
    if os.path.exists(SETTINGS_FILE):
        backup = SETTINGS_FILE + ".backup"
        os.rename(SETTINGS_FILE, backup)
    
    try:
        with patch('gui.qt_app.SETTINGS_FILE', '/nonexistent/path/settings.json'):
            from gui import qt_app
            original = qt_app.SETTINGS_FILE
            qt_app.SETTINGS_FILE = '/nonexistent/path/settings.json'
            result = qt_app.load_settings()
            qt_app.SETTINGS_FILE = original
            assert result == {}
    finally:
        if backup:
            os.rename(backup, SETTINGS_FILE)

def test_conversion_thread_initialization():
    from gui.qt_app import ConversionThread
    
    thread = ConversionThread(
        input_files=["/path/to/file.mp4"],
        output_format="mp3",
        output_dir="/output",
        merge=True,
        concat=False,
        framerate=30,
        quality="high",
        recursive=True,
        delete=False,
        workers=4,
    )
    
    assert thread.input_files == ["/path/to/file.mp4"]
    assert thread.output_format == "mp3"
    assert thread.output_dir == "/output"
    assert thread.merge is True
    assert thread.concat is False
    assert thread.framerate == 30
    assert thread.quality == "high"
    assert thread.recursive is True
    assert thread.delete is False
    assert thread.workers == 4
    assert thread._cancelled is False


def test_conversion_thread_cancel():
    from gui.qt_app import ConversionThread
    
    thread = ConversionThread(
        input_files=["/path/to/file.mp4"],
        output_format="mp3",
        output_dir="/output",
    )
    
    assert thread._cancelled is False
    thread.cancel()
    assert thread._cancelled is True


def test_conversion_thread_job_id_unique():
    from gui.qt_app import ConversionThread
    thread1 = ConversionThread(["/file1.mp4"], "mp3", "/out")
    thread2 = ConversionThread(["/file2.mp4"], "mp3", "/out")
    assert thread1.job_id != thread2.job_id

@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture  
def main_window(qapp):
    from gui.qt_app import MainWindow
    window = MainWindow()
    yield window
    window.close()


def test_main_window_creation(main_window):
    assert main_window is not None
    assert "any_to_any.py" in main_window.windowTitle()


def test_main_window_minimum_size(main_window):
    min_size = main_window.minimumSize()
    assert min_size.width() >= 850
    assert min_size.height() >= 650


def test_main_window_has_file_set(main_window):
    assert hasattr(main_window, '_file_paths_set')
    assert isinstance(main_window._file_paths_set, set)


def test_format_combo_populated(main_window):
    assert main_window.format_combo.count() > 0


def test_framerate_spin_range(main_window):
    assert main_window.framerate_spin.minimum() == 0
    assert main_window.framerate_spin.maximum() == 120


def test_workers_spin_range(main_window):
    # Test workers spinbox has correct range
    assert main_window.workers_spin.minimum() == 1
    assert main_window.workers_spin.maximum() == 8


def test_quality_combo_options(main_window):
    # Test quality combo has correct options
    options = [main_window.quality_combo.itemText(i) for i in range(main_window.quality_combo.count())]
    assert "Default" in options
    assert "High" in options
    assert "Medium" in options
    assert "Low" in options


def test_add_file_to_list(main_window, tmp_path):
    test_file = tmp_path / "test.mp4"
    test_file.touch()
    
    initial_count = main_window.file_list.count()
    main_window.add_file_to_list(str(test_file))
    
    assert main_window.file_list.count() == initial_count + 1
    assert str(test_file) in main_window._file_paths_set


def test_add_file_duplicate_prevention(main_window, tmp_path):
    test_file = tmp_path / "test.mp4"
    test_file.touch()
    
    main_window.add_file_to_list(str(test_file))
    initial_count = main_window.file_list.count()
    main_window.add_file_to_list(str(test_file))

    assert main_window.file_list.count() == initial_count


def test_add_file_nonexistent_file(main_window):
    initial_count = main_window.file_list.count()
    main_window.add_file_to_list("/nonexistent/path/file.mp4")
    assert main_window.file_list.count() == initial_count


def test_clear_all_files(main_window, tmp_path):
    for i in range(3):
        f = tmp_path / f"test{i}.mp4"
        f.touch()
        main_window.add_file_to_list(str(f))
    
    assert main_window.file_list.count() == 3
    assert len(main_window._file_paths_set) == 3
    
    main_window.clear_all_files()
    
    assert main_window.file_list.count() == 0
    assert len(main_window._file_paths_set) == 0


def test_file_count_label_update(main_window, tmp_path):
    test_file = tmp_path / "test.mp4"
    test_file.touch()
    
    main_window.add_file_to_list(str(test_file))
    assert "1" in main_window.file_count_label.text()


def test_cancel_button_initially_disabled(main_window):
    assert not main_window.cancel_btn.isEnabled()


def test_convert_button_initially_enabled(main_window):
    assert main_window.convert_btn.isEnabled()


def test_set_ui_enabled_false(main_window):
    main_window.set_ui_enabled(False)
    
    assert not main_window.add_files_btn.isEnabled()
    assert not main_window.convert_btn.isEnabled()
    assert main_window.cancel_btn.isEnabled()


def test_set_ui_enabled_true(main_window):
    main_window.set_ui_enabled(False)
    main_window.set_ui_enabled(True)
    
    assert main_window.add_files_btn.isEnabled()
    assert main_window.convert_btn.isEnabled()
    assert not main_window.cancel_btn.isEnabled()


def test_file_list_performance_large_batch(main_window, tmp_path):
    import time
    
    files = []
    for i in range(100):
        f = tmp_path / f"file_{i:03d}.mp4"
        f.touch()
        files.append(str(f))
    
    start = time.time()
    for f in files:
        main_window.add_file_to_list(f)
    elapsed = time.time() - start
    
    assert main_window.file_list.count() == 100
    assert elapsed < 1.0, f"Adding 100 files took {elapsed:.2f}s, should be < 1s"


def test_settings_dialog_creation(qapp):
    from gui.qt_app import SettingsDialog
    dlg = SettingsDialog(None, "English", ["English", "German", "French"])
    assert dlg is not None
    assert dlg.selected_locale == "English"


def test_settings_dialog_locale_change(qapp):
    from gui.qt_app import SettingsDialog
    dlg = SettingsDialog(None, "English", ["English", "German", "French"])
    
    dlg.set_locale("German")
    assert dlg.selected_locale == "German"


def test_help_dialog_creation(qapp):
    from gui.qt_app import HelpDialog
    dlg = HelpDialog(None, "English")
    assert dlg is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
