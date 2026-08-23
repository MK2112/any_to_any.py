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
    # Test workers spinbox has correct range, capped by CPU count like the CLI
    import os

    expected_max = max(1, min((os.cpu_count() or 2) - 1, 32))
    assert main_window.workers_spin.minimum() == 1
    assert main_window.workers_spin.maximum() == expected_max


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


def test_cancel_btn_initially_disabled(main_window):
    assert not main_window.cancel_btn.isEnabled()


def test_convert_btn_initially_enabled(main_window):
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


# ---- Resolution integration -------------------------------------------------


def test_format_combo_has_keep_original_entry(main_window):
    assert main_window.format_combo.itemData(0) == "original"
    # Default selection is a category header, forcing an explicit choice
    assert main_window.format_combo.currentData() is None


def test_resolution_combo_initially_hidden(main_window):
    # No target format chosen -> no ladder -> field hidden entirely
    assert not main_window.resolution_combo.isVisibleTo(main_window)
    assert not main_window.resolution_combo.isEnabled()


def test_split_field_initially_hidden(main_window):
    # Split only applies to PDF targets
    assert not main_window.split_edit.isVisibleTo(main_window)


def test_resolution_ladder_for_target(main_window):
    ladder = main_window._resolution_ladder_for_target("mp4")
    assert "1920x1080" in ladder
    assert "3840x2160" in ladder
    assert main_window._resolution_ladder_for_target("mp3") == []


def test_hls_protocol_ladder(main_window):
    ladder = main_window._resolution_ladder_for_target("hls")
    assert "842x480" in ladder
    assert "3840x2160" not in ladder


def test_selecting_movie_format_populates_resolution(main_window):
    idx = main_window.format_combo.findData("mp4")
    main_window.format_combo.setCurrentIndex(idx)
    combo = main_window.resolution_combo
    assert combo.isVisibleTo(main_window)
    data = [combo.itemData(i) for i in range(combo.count())]
    assert "" in data  # Keep-original option always present
    assert "1920x1080" in data


def test_audio_format_hides_resolution(main_window):
    idx = main_window.format_combo.findData("mp3")
    main_window.format_combo.setCurrentIndex(idx)
    assert not main_window.resolution_combo.isVisibleTo(main_window)
    assert main_window.resolution_combo.count() == 1


def test_resize_only_ladder_intersection(main_window, tmp_path):
    f1 = tmp_path / "a.mp4"  # allows up to 4k
    f2 = tmp_path / "b.flv"  # HD max
    f1.touch()
    f2.touch()
    main_window.add_files_batch([str(f1), str(f2)])
    idx = main_window.format_combo.findData("original")
    main_window.format_combo.setCurrentIndex(idx)
    ladder = main_window._selected_movie_ladder_intersection()
    assert "1920x1080" in ladder
    assert "2560x1440" not in ladder


def test_merge_concat_hides_resolution(main_window, tmp_path):
    f1 = tmp_path / "a.mp4"
    f1.touch()
    main_window.add_files_batch([str(f1)])
    idx = main_window.format_combo.findData("mp4")
    main_window.format_combo.setCurrentIndex(idx)
    assert main_window.resolution_combo.isVisibleTo(main_window)
    main_window.merge_check.setChecked(True)
    assert not main_window.resolution_combo.isVisibleTo(main_window)


def test_split_and_resolution_share_slot_exclusively(main_window):
    # PDF target: split shown, resolution hidden
    idx = main_window.format_combo.findData("pdf")
    main_window.format_combo.setCurrentIndex(idx)
    assert main_window.split_edit.isVisibleTo(main_window)
    assert not main_window.resolution_combo.isVisibleTo(main_window)

    # Movie target: exactly the reverse
    idx = main_window.format_combo.findData("mp4")
    main_window.format_combo.setCurrentIndex(idx)
    assert not main_window.split_edit.isVisibleTo(main_window)
    assert main_window.resolution_combo.isVisibleTo(main_window)


def test_split_hidden_clears_pattern_and_unlocks_merge(main_window):
    idx = main_window.format_combo.findData("pdf")
    main_window.format_combo.setCurrentIndex(idx)
    main_window.split_edit.setText("1-3,8-end")
    # A filled pattern locks merge/concat out
    assert not main_window.merge_check.isEnabled()
    assert not main_window.concat_check.isEnabled()

    # Leaving the PDF context hides the field and resets its state
    idx = main_window.format_combo.findData("mp4")
    main_window.format_combo.setCurrentIndex(idx)
    assert not main_window.split_edit.isVisibleTo(main_window)
    assert main_window.split_edit.text() == ""
    assert main_window.merge_check.isEnabled()
    assert main_window.concat_check.isEnabled()


def test_merge_checked_hides_split_field(main_window):
    idx = main_window.format_combo.findData("pdf")
    main_window.format_combo.setCurrentIndex(idx)
    assert main_window.split_edit.isVisibleTo(main_window)
    main_window.merge_check.setChecked(True)
    assert not main_window.split_edit.isVisibleTo(main_window)
    main_window.merge_check.setChecked(False)
    assert main_window.split_edit.isVisibleTo(main_window)


# ---- Split integration ------------------------------------------------------


def test_split_pattern_validation(main_window):
    for pattern in [
        "1-3",
        "10",
        "1-3,2-6,8-end",
        "1-5,rest",
        "end",
        "rest",
        "1 - 4",
        "1-3;5-7",  # Semicolon delimiter accepted like the backend
        "1-3,,5",  # Empty parts tolerated like the backend
    ]:
        assert main_window._is_valid_split_pattern(pattern), pattern
    for pattern in ["", "abc", "3-1", "1--2", "all"]:
        assert not main_window._is_valid_split_pattern(pattern), pattern


def test_start_conversion_blocked_without_format(main_window, tmp_path):
    test_file = tmp_path / "video.mp4"
    test_file.touch()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    main_window.add_files_batch([str(test_file)])
    main_window.output_dir_edit.setText(str(out_dir))
    with patch("gui.qt_app.QMessageBox") as mock_box:
        main_window.start_conversion()
        assert mock_box.warning.called
    assert main_window.current_thread is None


def test_resize_only_requires_resolution(main_window, tmp_path):
    test_file = tmp_path / "video.mkv"
    test_file.touch()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    main_window.add_files_batch([str(test_file)])
    main_window.output_dir_edit.setText(str(out_dir))
    idx = main_window.format_combo.findData("original")
    main_window.format_combo.setCurrentIndex(idx)
    with patch("gui.qt_app.QMessageBox") as mock_box:
        main_window.start_conversion()
        assert mock_box.warning.called
    assert main_window.current_thread is None


def test_merge_concat_mutual_exclusion(main_window, tmp_path):
    test_file = tmp_path / "video.mp4"
    test_file.touch()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    main_window.add_files_batch([str(test_file)])
    main_window.output_dir_edit.setText(str(out_dir))
    idx = main_window.format_combo.findData("mp4")
    main_window.format_combo.setCurrentIndex(idx)
    main_window.merge_check.setChecked(True)
    main_window.concat_check.setChecked(True)
    with patch("gui.qt_app.QMessageBox") as mock_box:
        main_window.start_conversion()
        assert mock_box.warning.called
    assert main_window.current_thread is None


# ---- Metadata options -------------------------------------------------------


def test_metadata_selector_options(main_window):
    options = [
        main_window.metadata_combo.itemText(i)
        for i in range(main_window.metadata_combo.count())
    ]
    assert options == ["Default", "Preserve", "Strip"]
    assert main_window.metadata_combo.currentText() == "Default"


# ---- Update check wiring ----------------------------------------------------


def _pump_events(qapp, seconds):
    from time import time, sleep

    deadline = time() + seconds
    while time() < deadline:
        qapp.processEvents()
        sleep(0.02)


def test_update_check_emits_newer_version(qapp):
    from gui import qt_app

    received = []
    bridge = qt_app.UpdateCheckBridge()
    bridge.update_available.connect(received.append)
    monkey = patch("gui.qt_app.check_for_update", lambda: "9.9.9")
    with monkey:
        qt_app.start_update_check(bridge)
    _pump_events(qapp, 3)
    assert received == ["9.9.9"]


def test_update_check_silent_when_up_to_date(qapp):
    from gui import qt_app

    received = []
    bridge = qt_app.UpdateCheckBridge()
    bridge.update_available.connect(received.append)
    with patch("gui.qt_app.check_for_update", lambda: None):
        qt_app.start_update_check(bridge)
    _pump_events(qapp, 1)
    assert received == []


# ---- Folder opener robustness -----------------------------------------------


class FakeProcess:
    # Mimics subprocess.Popen results: hang=True simulates an opener that
    # stays alive (file managers), rc simulates an immediate exit code.
    def __init__(self, rc=None, hang=False):
        self._rc = rc
        self._hang = hang

    def wait(self, timeout=None):
        import subprocess

        if self._hang:
            raise subprocess.TimeoutExpired("opener", timeout)
        return self._rc


def test_open_file_location_prefers_available_opener(main_window, monkeypatch):
    from gui import qt_app as qa

    calls = []
    monkeypatch.setattr(qa.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        qa.shutil, "which", lambda name: "/usr/bin/gio" if name == "gio" else None
    )

    def fake_popen(argv, **kwargs):
        calls.append(argv)
        return FakeProcess(hang=True)

    monkeypatch.setattr(qa.subprocess, "Popen", fake_popen)
    main_window._open_file_location("/tmp/some/file.mp4")
    # Files resolve to their containing folder
    assert calls == [["gio", "open", "/tmp/some"]]


def test_open_file_location_detaches_child_process(main_window, monkeypatch):
    from gui import qt_app as qa

    seen = {}
    monkeypatch.setattr(qa.platform, "system", lambda: "Linux")
    monkeypatch.setattr(qa.shutil, "which", lambda name: "/usr/bin/xdg-open")

    def fake_popen(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return FakeProcess(rc=0)

    monkeypatch.setattr(qa.subprocess, "Popen", fake_popen)
    main_window._open_file_location("/tmp/just_a_dir")
    assert seen["argv"][0] == "xdg-open"
    assert seen["kwargs"]["stdout"] == qa.subprocess.DEVNULL
    assert seen["kwargs"]["stderr"] == qa.subprocess.DEVNULL
    assert seen["kwargs"]["start_new_session"] is True


def test_open_file_location_sanitizes_child_environment(main_window, monkeypatch):
    from gui import qt_app as qa

    seen = {}
    monkeypatch.setattr(qa.platform, "system", lambda: "Linux")
    monkeypatch.setattr(qa.shutil, "which", lambda name: "/usr/bin/xdg-open")

    def fake_popen(argv, **kwargs):
        seen["kwargs"] = kwargs
        return FakeProcess(rc=0)

    monkeypatch.setattr(qa.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI12345")
    monkeypatch.setenv("LD_PRELOAD", "/tmp/_MEI12345/lib.so")
    monkeypatch.setenv("_MEIPASS2", "/tmp/_MEI12345")
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "/tmp/_MEI12345")
    monkeypatch.setenv("HOME", "/home/user")  # must survive untouched
    main_window._open_file_location("/tmp/just_a_dir")
    env = seen["kwargs"]["env"]
    assert "LD_LIBRARY_PATH" not in env
    assert "LD_PRELOAD" not in env
    assert "_MEIPASS2" not in env
    assert "_PYI_APPLICATION_HOME_DIR" not in env
    assert env["HOME"] == "/home/user"


def test_open_file_location_falls_through_on_opener_failure(main_window, monkeypatch):
    from gui import qt_app as qa

    attempts = []
    monkeypatch.setattr(qa.platform, "system", lambda: "Linux")
    monkeypatch.setattr(qa.shutil, "which", lambda name: "/usr/bin/" + name)

    def fake_popen(argv, **kwargs):
        attempts.append(argv[0])
        # xdg-open and gio both "fail" immediately with a non-zero exit
        return FakeProcess(rc=1 if argv[0] in ("xdg-open", "gio") else 0)

    monkeypatch.setattr(qa.subprocess, "Popen", fake_popen)
    main_window._open_file_location("/tmp/f.mp4")
    assert attempts[0] == "xdg-open"
    assert "gio" in attempts
    assert attempts[-1] not in ("xdg-open", "gio")


def test_open_file_location_shows_dialog_when_all_fail(main_window, monkeypatch):
    from gui import qt_app as qa

    warnings = []
    monkeypatch.setattr(qa.platform, "system", lambda: "Linux")
    monkeypatch.setattr(qa.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        qa.QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a))
    )
    main_window._open_file_location("/tmp/nowhere.mp4")
    assert len(warnings) == 1


def test_open_file_location_survives_spawner_errors(main_window, monkeypatch):
    from gui import qt_app as qa

    monkeypatch.setattr(qa.platform, "system", lambda: "Linux")
    monkeypatch.setattr(qa.shutil, "which", lambda name: "/usr/bin/" + name)

    attempts = []

    def flaky_popen(argv, **kwargs):
        attempts.append(argv[0])
        if argv[0] == "xdg-open":
            raise OSError("EBADF")
        return FakeProcess(rc=0)

    monkeypatch.setattr(qa.subprocess, "Popen", flaky_popen)
    main_window._open_file_location("/tmp/f.mp4")
    assert attempts[0] == "xdg-open"
    assert attempts[-1] != "xdg-open"  # fell through to a later candidate


def test_conversion_thread_new_options():
    from gui.qt_app import ConversionThread

    thread = ConversionThread(
        input_files=["/path/to/file.mp4"],
        output_format=None,
        output_dir="/output",
        resolution="1280x720",
        split="1-3",
        preserve_meta=True,
        strip_meta=False,
    )
    assert thread.resolution == "1280x720"
    assert thread.split == "1-3"
    assert thread.preserve_meta is True
    assert thread.strip_meta is False


def test_job_id_is_hex8():
    import re
    from gui.qt_app import ConversionThread

    thread = ConversionThread(["/file.mp4"], "mp3", "/out")
    assert re.fullmatch(r"[0-9a-f]{8}", thread.job_id)


# ---- Translation fallback ---------------------------------------------------


def test_tr_key_english_fallback():
    from gui.qt_app import tr_key

    assert tr_key("split_pages", "English") == "Split Pages (PDF)"
    # Untranslated locale falls back to English text, never the raw key
    assert tr_key("split_pages", "German") == "Split Pages (PDF)"
    assert tr_key("resolution_label", "German") != "resolution_label"


# ---- File list behaviour ----------------------------------------------------


def test_add_files_batch_filters_unsupported(main_window, tmp_path):
    good = tmp_path / "good.mp4"
    bad = tmp_path / "bad.xyz"
    good.touch()
    bad.touch()
    main_window.add_files_batch([str(good), str(bad)])
    assert str(good) in main_window._file_paths_set
    assert str(bad) not in main_window._file_paths_set
    assert main_window.file_list.count() == 1


def test_prune_missing_sources(main_window, tmp_path):
    f1 = tmp_path / "keep.mp4"
    f2 = tmp_path / "gone.mp4"
    f1.touch()
    f2.touch()
    main_window.add_files_batch([str(f1), str(f2)])
    f2.unlink()
    main_window._prune_missing_sources()
    assert main_window.file_list.count() == 1
    assert str(f1) in main_window._file_paths_set
    assert str(f2) not in main_window._file_paths_set


def test_language_switch_preserves_file_list(main_window, tmp_path):
    # Regression: rebuilding the UI (locale change) used to desync the
    # duplicate-check set from the list, silently dropping all files.
    from gui import qt_app

    test_file = tmp_path / "clip.mp4"
    test_file.touch()
    main_window.add_files_batch([str(test_file)])
    assert main_window.file_list.count() == 1

    class FakeDialog:
        def __init__(self, *args, **kwargs):
            self.selected_locale = "German"

        def exec(self):
            return True

    original = qt_app.SettingsDialog
    qt_app.SettingsDialog = FakeDialog
    try:
        main_window.open_settings_dialog()
    finally:
        qt_app.SettingsDialog = original

    assert main_window.file_list.count() == 1
    assert str(test_file) in main_window._file_paths_set
    assert main_window.locale == "German"


def test_save_settings_merges_existing_keys():
    from gui.qt_app import load_settings, save_settings

    original = load_settings()
    try:
        save_settings({"gui_test_marker": "abc"})
        save_settings({"last_dir": "/tmp/x"})
        loaded = load_settings()
        assert loaded.get("gui_test_marker") == "abc"
        assert loaded.get("last_dir") == "/tmp/x"
    finally:
        save_settings(original)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
