import os
import sys
import pytest

from unittest.mock import patch
from types import SimpleNamespace
from contextlib import nullcontext

from PyQt6.QtTest import QTest
from PyQt6.QtGui import QDropEvent
from PyQt6.QtCore import QMimeData, QEvent, QPointF, Qt, QUrl

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def main_window(qapp):
    from gui.qt_app import MainWindow, save_settings

    save_settings({"active_view": 0, "locale": "English"})
    window = MainWindow()
    yield window
    window.edit_view.shutdown()
    window.close()
    save_settings({"active_view": 0})


def test_tabs_exist_convert_is_default(main_window):
    tab_widget = main_window.tab_widget
    assert tab_widget.count() == 2
    assert [tab_widget.tabText(i) for i in range(2)] == ["Convert", "Edit"]
    assert tab_widget.currentIndex() == 0
    assert main_window.tab_bar is tab_widget.tabBar()


def test_active_tab_is_persisted_across_restarts(qapp, main_window):
    from gui.qt_app import MainWindow, load_settings

    main_window.tab_widget.setCurrentIndex(1)
    assert load_settings().get("active_view") == 1

    other = MainWindow()
    try:
        assert other.tab_widget.currentIndex() == 1
        other.tab_widget.setCurrentIndex(0)
        third = MainWindow()
        try:
            assert third.tab_widget.currentIndex() == 0
        finally:
            third.edit_view.shutdown()
    finally:
        other.edit_view.shutdown()


def test_edit_active_detection(main_window):
    assert not main_window._edit_active()
    main_window.tab_widget.setCurrentIndex(1)
    assert main_window._edit_active()


def test_shortcuts_route_to_active_view(main_window):
    main_window.tab_widget.setCurrentIndex(1)
    ev = main_window.edit_view
    with (
        patch.object(ev, "add_files") as add,
        patch.object(ev, "add_folder") as folder,
        patch.object(ev, "delete_selected") as delete,
        patch.object(ev, "start_export") as export,
        patch.object(ev, "cancel_export") as cancel,
    ):
        main_window.add_files()
        main_window.add_folder()
        main_window.remove_selected()
        main_window.start_conversion()
        main_window.cancel_conversion()
    add.assert_called_once()
    folder.assert_called_once()
    delete.assert_called_once()
    export.assert_called_once()
    cancel.assert_called_once()


def test_edit_export_busy_blocks_convert_start(main_window):
    main_window.set_edit_export_busy(True)
    assert not main_window.convert_btn.isEnabled()
    with patch("gui.qt_app.QMessageBox") as box:
        main_window.start_conversion()
    assert not box.warning.called
    assert main_window.current_thread is None
    main_window.set_edit_export_busy(False)
    assert main_window.convert_btn.isEnabled()


def test_edit_view_has_core_widgets(main_window):
    ev = main_window.edit_view
    for name in (
        "media_pool",
        "timeline",
        "cut_btn",
        "delete_btn",
        "clear_btn",
        "mode_combo",
        "format_combo",
        "resolution_combo",
        "output_edit",
        "export_btn",
        "cancel_btn",
        "progress_bar",
        "tags_edit",
        "burn_subs_check",
        "metadata_combo",
        "marker_list",
    ):
        assert hasattr(ev, name), name
    assert [ev.mode_combo.itemData(i) for i in range(ev.mode_combo.count())] == [
        "stitch",
        "timeline",
        "trim",
        "split",
        "merge",
    ]


def _media(path, duration=10.0, kind="audio"):
    from gui.timeline import MediaFile

    return MediaFile(path=path, duration=duration, kind=kind)


def test_timeline_add_order_and_duration(main_window):
    timeline = main_window.edit_view.timeline
    a = _media("/a.wav", 6.0)
    b = _media("/b.mp4", 4.0, "movie")
    first = timeline.add_media(a, start=0, track=0)
    second = timeline.add_media(b, start=6.0, track=0)
    assert [c.clip_id for c in timeline.ordered_clips()] == [
        first.clip_id,
        second.clip_id,
    ]
    assert timeline.total_duration() == 10.0
    assert first.length == 6.0 and second.length == 4.0


def test_timeline_append_at_end_when_playhead_zero(main_window):
    timeline = main_window.edit_view.timeline
    timeline.add_media(_media("/a.wav", 5.0), start=0, track=0)
    appended = timeline.add_media(_media("/b.wav", 3.0), track=0)
    assert appended.start == 5.0


def test_timeline_split_at_playhead(main_window):
    timeline = main_window.edit_view.timeline
    clip = timeline.add_media(_media("/a.wav", 10.0), start=0, track=0)
    timeline.playhead = 4.0
    timeline.selected_ids = {clip.clip_id}
    assert timeline.split_selected_at_playhead() == 1
    left, right = timeline.ordered_clips()
    assert (left.in_point, left.out_point) == (0.0, 4.0)
    assert right.in_point == 4.0 and right.out == 10.0  # None out means "to end"
    assert left.end == right.start == 4.0


def test_timeline_split_outside_clip_is_noop(main_window):
    timeline = main_window.edit_view.timeline
    clip = timeline.add_media(_media("/a.wav", 10.0), start=0, track=0)
    timeline.playhead = 20.0
    timeline.selected_ids = {clip.clip_id}
    assert timeline.split_selected_at_playhead() == 0
    assert len(timeline.clips) == 1


def test_timeline_remove_selected_and_clear(main_window):
    timeline = main_window.edit_view.timeline
    timeline.add_media(_media("/a.wav", 5.0), start=0, track=0)
    timeline.add_media(_media("/b.wav", 5.0), start=5.0, track=1)
    first = timeline.clips[0]
    timeline.selected_ids = {first.clip_id}
    assert timeline.remove_selected() == 1
    assert len(timeline.clips) == 1
    timeline.clear()
    assert timeline.clips == [] and timeline.total_duration() == 0.0


def test_timeline_snap_affects_move(main_window):
    timeline = main_window.edit_view.timeline
    a = timeline.add_media(_media("/a.wav", 4.0), start=0, track=0)
    b = timeline.add_media(_media("/b.wav", 4.0), start=8.0, track=1)
    timeline.snapping = True
    assert timeline._snap_time(3.95, b.clip_id) == 4.0
    timeline.snapping = False
    assert timeline._snap_time(3.95, b.clip_id) == 3.95


def test_edit_view_pool_drop_places_clips(main_window):
    ev = main_window.edit_view
    path = "/tmp/opencode/tone.wav"
    if not os.path.isfile(path):
        pytest.skip("sample media not present")
    ev.add_paths([path])
    media = ev.media_pool.media()[0]
    ev._on_files_dropped([path], 3.0, 1)
    assert len(ev.timeline.clips) == 1
    clip = ev.timeline.clips[0]
    assert clip.start == 3.0 and clip.track == 1 and clip.media is media


def _base_job(mode, outdir="/tmp/out"):
    return {
        "mode": mode,
        "output_dir": outdir,
        "format": ["mp3"],
        "clips": [
            {"path": "/a.wav", "in": 1.0, "out": 3.0, "duration": 10.0},
            {"path": "/b.wav", "in": 0.0, "out": None, "duration": 5.0},
        ],
    }


def test_build_steps_stitch_uses_trim_then_concat(tmp_path):
    from gui.edit_export import build_steps

    steps, collected = build_steps(_base_job("stitch"), str(tmp_path))
    assert len(steps) == 2  # one trimmed segment + the concat pass
    assert steps[0].trim == "1-3"
    assert steps[0].inputs == ["/a.wav"]
    assert steps[0].collect_to == 0
    assert steps[1].concat is True
    assert steps[1].inputs == [("@collect", 0), "/b.wav"]
    assert steps[1].formats == ["mp3"]
    assert collected == 2


def test_build_steps_no_trim_needed_for_full_clip(tmp_path):
    from gui.edit_export import build_steps

    job = _base_job("stitch")
    job["clips"] = [{"path": "/a.wav", "in": 0, "out": 10.0, "duration": 10.0}]
    steps, _ = build_steps(job, str(tmp_path))
    assert len(steps) == 1
    assert steps[0].concat is True
    assert steps[0].inputs == ["/a.wav"]


def test_build_steps_split_merge_trim(tmp_path):
    from gui.edit_export import build_steps

    split_job = _base_job("split")
    split_job["source_path"] = "/a.wav"
    split_job["split_points"] = [2.0, 4.5]
    split_steps, _ = build_steps(split_job, str(tmp_path))
    assert split_steps[0].split_at == "2,4.5"
    assert split_steps[0].inputs == ["/a.wav"]

    merge_job = _base_job("merge")
    merge_job["inputs"] = ["/v.mp4", "/v.wav"]
    merge_steps, _ = build_steps(merge_job, str(tmp_path))
    assert merge_steps[0].merge is True
    assert merge_steps[0].inputs == ["/v.mp4", "/v.wav"]

    trim_steps, _ = build_steps(_base_job("trim"), str(tmp_path))
    assert trim_steps[0].trim == "1-3"
    assert not trim_steps[0].concat and not trim_steps[0].merge


def _run_export(qapp, job):
    from PyQt6.QtCore import Qt
    from gui.edit_export import EditExportThread

    runs = []
    events = []

    class FakeController:
        def __init__(self, job_id=None, shared_progress_dict=None, is_web=False):
            self.file_handler = SimpleNamespace(cancel_event=None)
            self.shared = shared_progress_dict
            self.job_id = job_id
            shared_progress_dict[job_id] = {
                "progress": 0,
                "total": 100,
                "status": "starting",
            }

        def run(self, **kwargs):
            runs.append(kwargs)
            name = f"fake_{len(runs)}.bin"
            with open(os.path.join(kwargs["output"], name), "wb") as handle:
                handle.write(b"x")
            self.shared[self.job_id].update(progress=100, status="done")

    thread = EditExportThread(job)
    for signal, name in (
        (thread.edit_finished, "finished"),
        (thread.error_occurred, "error"),
        (thread.edit_cancelled, "cancelled"),
    ):
        signal.connect(
            lambda *a, n=name: events.append((n, a)), Qt.ConnectionType.DirectConnection
        )

    with (
        patch("gui.edit_export.Controller", FakeController),
        patch("gui.edit_export.FFmpegProcessTracker", lambda *a, **k: nullcontext()),
    ):
        thread.start()
        assert thread.wait(15000)
    return runs, events


def test_export_thread_stitch_calls_concat_with_resolved_segments(qapp, tmp_path):
    runs, events = _run_export(qapp, _base_job("stitch", str(tmp_path)))
    assert len(runs) == 2
    assert runs[0]["trim"] == "1-3"
    assert runs[0]["input_path_args"] == ["/a.wav"]
    assert runs[1]["concat"] is True
    assert len(runs[1]["input_path_args"]) == 2
    assert all(isinstance(path, str) for path in runs[1]["input_path_args"])
    assert events[-1][0] == "finished" and events[-1][1][2] is True


def test_export_thread_passes_cli_only_features(qapp, tmp_path):
    job = _base_job("split", str(tmp_path))
    job["source_path"] = "/a.wav"
    job["split_points"] = [2.0, 4.0]
    job.update(
        burn_subs=True,
        preserve_meta=True,
        add_tag=["artist:John"],
        quality="high",
        framerate=30,
        resolution="1280x720",
    )
    runs, events = _run_export(qapp, job)
    assert runs[0]["split_at"] == "2,4"
    assert runs[0]["burn_subs"] is True
    assert runs[0]["preserve_meta"] is True
    assert runs[0]["add_tag"] == ["artist:John"]
    assert runs[0]["quality"] == "high"
    assert runs[0]["framerate"] == 30
    assert runs[0]["resolution"] == "1280x720"
    assert events[-1][0] == "finished"


def test_export_thread_cancellation(qapp, tmp_path):
    import time
    import threading
    from PyQt6.QtCore import Qt
    from gui.edit_export import EditExportThread
    from core.utils.file_handler import ConversionCancelled

    started = threading.Event()
    events = []

    class FakeController:
        def __init__(self, **kwargs):
            self.file_handler = SimpleNamespace(cancel_event=None)
            self.shared = kwargs["shared_progress_dict"]
            self.job_id = kwargs["job_id"]
            self.shared[self.job_id] = {"progress": 0, "total": 100}

        def run(self, **kwargs):
            started.set()
            event = self.file_handler.cancel_event
            while event is not None and not event.is_set():
                time.sleep(0.01)
            raise ConversionCancelled()

    thread = EditExportThread(_base_job("trim", str(tmp_path)))
    thread.edit_cancelled.connect(
        lambda *a: events.append("cancelled"), Qt.ConnectionType.DirectConnection
    )
    with (
        patch("gui.edit_export.Controller", FakeController),
        patch("gui.edit_export.FFmpegProcessTracker", lambda *a, **k: nullcontext()),
    ):
        thread.start()
        assert started.wait(5)
        thread.cancel()
        assert thread.wait(15000)
    assert "cancelled" in events


def test_parse_formats_supports_multi_format(main_window):
    ev = main_window.edit_view
    ev.format_combo.setEditText("mp3,wav")
    assert ev._parse_formats() == ["mp3", "wav"]
    ev.format_combo.setEditText("not_a_format")
    assert ev._parse_formats() is False
    ev.format_combo.setCurrentIndex(0)  # Keep original
    assert ev._parse_formats() is None


def test_locale_rebuild_preserves_timeline_and_tab(main_window):
    from gui import qt_app

    timeline = main_window.edit_view.timeline
    main_window.edit_view.add_paths(["/tmp/opencode/tone.wav"])
    if not timeline.clips and os.path.isfile("/tmp/opencode/tone.wav"):
        main_window.edit_view._on_files_dropped(["/tmp/opencode/tone.wav"], 0.0, 0)
    main_window.tab_widget.setCurrentIndex(1)

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

    assert main_window.tab_widget.currentIndex() == 1
    assert main_window.locale == "German"
    if os.path.isfile("/tmp/opencode/tone.wav"):
        assert len(main_window.edit_view.timeline.clips) == 1


def test_cut_without_selection_uses_clip_under_playhead(main_window):
    ev = main_window.edit_view
    timeline = ev.timeline
    clip = timeline.add_media(_media("/a.wav", 10.0), start=0, track=0)
    timeline.selected_ids.clear()
    timeline.set_playhead(4.0)
    assert timeline.clip_at_playhead() is clip

    ev.cut_at_playhead()
    assert len(timeline.clips) == 2
    assert "Cut 1 clip(s)" in ev.feedback_label.text()


def test_cut_outside_clips_gives_actionable_hint(main_window):
    ev = main_window.edit_view
    ev.timeline.add_media(_media("/a.wav", 5.0), start=0, track=0)
    ev.timeline.selected_ids.clear()
    ev.timeline.set_playhead(20.0)
    ev.cut_at_playhead()
    assert len(ev.timeline.clips) == 1
    assert "playhead" in ev.feedback_label.text().lower()


def test_clip_properties_reflect_and_edit_selection(main_window):
    ev = main_window.edit_view
    clip = ev.timeline.add_media(_media("/a.wav", 10.0), start=1.0, track=0)
    ev.timeline.selected_ids = {clip.clip_id}
    ev.timeline.selection_changed.emit()
    assert ev.clip_name_label.text() == "a.wav"
    assert ev.pos_spin.value() == 1.0
    assert ev.in_spin.value() == 0.0
    assert ev.out_spin.value() == 10.0
    assert ev.pos_spin.isEnabled()

    ev.pos_spin.setValue(3.5)
    ev.in_spin.setValue(2.0)
    ev.out_spin.setValue(6.0)
    assert (clip.start, clip.in_point, clip.out_point) == (3.5, 2.0, 6.0)
    assert clip.length == 4.0


def test_clip_properties_clean_when_nothing_selected(main_window):
    ev = main_window.edit_view
    ev.timeline.add_media(_media("/a.wav", 5.0), start=0, track=0)
    ev.timeline.selected_ids.clear()
    ev.timeline.selection_changed.emit()
    assert not ev.pos_spin.isEnabled()
    assert not ev.out_spin.isEnabled()
    assert "Select a clip" in ev.clip_name_label.text()


def test_marker_panel_only_in_split_mode(main_window):
    ev = main_window.edit_view
    assert ev.marker_panel.isHidden()
    ev.mode_combo.setCurrentIndex(ev.mode_combo.findData("split"))
    assert not ev.marker_panel.isHidden()
    ev.timeline.set_playhead(2.0)
    ev.add_marker()
    assert len(ev.timeline.markers) == 1
    ev.mode_combo.setCurrentIndex(ev.mode_combo.findData("stitch"))
    assert ev.marker_panel.isHidden()
    assert ev.timeline.markers == []


def test_marker_double_click_moves_playhead(main_window):
    ev = main_window.edit_view
    ev.mode_combo.setCurrentIndex(ev.mode_combo.findData("split"))
    ev.timeline.set_playhead(2.5)
    ev.add_marker()
    ev.timeline.set_playhead(0.0)
    ev.marker_list.itemDoubleClicked.emit(ev.marker_list.item(0))
    assert ev.timeline.playhead == 2.5


def test_pool_double_click_places_clip(main_window):
    ev = main_window.edit_view
    path = "/tmp/opencode/tone.wav"
    if not os.path.isfile(path):
        pytest.skip("sample media not present")
    ev.add_paths([path])
    media = ev.media_pool.item(0).data(Qt.ItemDataRole.UserRole)
    ev.media_pool.media_activated.emit(media)
    assert len(ev.timeline.clips) == 1
    assert ev.timeline.clips[0].media.path == path


def test_add_track_button(main_window):
    ev = main_window.edit_view
    before = len(ev.timeline.track_names)
    ev.add_track_btn.click()
    assert len(ev.timeline.track_names) == before + 1


def test_timeline_render_with_markers_and_clips(main_window):
    from PyQt6.QtGui import QPixmap

    ev = main_window.edit_view
    ev.timeline.add_media(_media("/a.wav", 8.0), start=0, track=0)
    ev.mode_combo.setCurrentIndex(ev.mode_combo.findData("split"))
    ev._markers = [2.0, 5.0]
    ev._refresh_markers()
    pixmap = QPixmap(600, 260)
    pixmap.fill()
    ev.timeline.resize(600, 260)
    ev.timeline.render(pixmap)
    assert not pixmap.isNull()


def test_drop_event_places_media_on_timeline(main_window):
    path = "/tmp/opencode/tone.wav"
    if not os.path.isfile(path):
        pytest.skip("sample media not present")
    timeline = main_window.edit_view.timeline
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    event = QDropEvent(
        QPointF(timeline._time_to_x(3.0), 30),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    timeline.dropEvent(event)
    assert len(timeline.clips) == 1
    assert timeline.clips[0].start == pytest.approx(3.0, abs=0.1)
    assert timeline.clips[0].track == 0


def test_mouse_drag_moves_and_trims_clip(main_window):
    timeline = main_window.edit_view.timeline
    timeline.snapping = False
    timeline.waveforms = False
    clip = timeline.add_media(_media("/a.wav", 10.0), start=1.0, track=0)
    rect = timeline._clip_rect(clip)
    center = rect.center()

    # Move the whole clip 60 px to the right.
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=center.toPoint())
    QTest.mouseMove(timeline, (center + QPointF(60, 0)).toPoint())
    QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton)
    assert clip.start == pytest.approx(1.0 + 60 / timeline.pps, abs=0.05)

    # Drag the right edge 40 px outwards to extend the out point
    # (start from a shorter clip so the source duration does not clamp it).
    clip.out_point = 5.0
    right = timeline._clip_rect(clip).right() - 2
    point = QPointF(right, rect.center().y())
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=point.toPoint())
    QTest.mouseMove(timeline, (point + QPointF(40, 0)).toPoint())
    QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton)
    assert clip.out_point == pytest.approx(5.0 + 40 / timeline.pps, abs=0.05)


def test_double_click_clip_focuses_properties(main_window, qapp):
    from PyQt6.QtGui import QMouseEvent

    main_window.show()
    main_window.tab_widget.setCurrentIndex(1)
    qapp.processEvents()
    ev = main_window.edit_view
    timeline = ev.timeline
    clip = timeline.add_media(_media("/a.wav", 8.0), start=1.0, track=0)
    seen = []
    timeline.clip_activated.connect(seen.append)

    rect = timeline._clip_rect(clip)
    event = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        rect.center(),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    timeline.mouseDoubleClickEvent(event)

    assert seen == [clip]
    assert timeline.selected_ids == {clip.clip_id}
    assert ev.clip_name_label.text() == "a.wav"
    assert ev.pos_spin.value() == 1.0
    assert ev.pos_spin.hasFocus()
    assert "a.wav" in ev.feedback_label.text()
    assert "a.wav" in ev.props_group.title()
    assert ev.props_group.styleSheet()  # visible highlight


def test_double_click_empty_timeline_moves_playhead(main_window):
    from PyQt6.QtGui import QMouseEvent

    ev = main_window.edit_view
    ev.timeline.add_media(_media("/a.wav", 8.0), start=0, track=0)
    seen = []
    ev.timeline.clip_activated.connect(seen.append)

    target_x = ev.timeline._time_to_x(5.0)
    event = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        QPointF(target_x, 300),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    ev.timeline.mouseDoubleClickEvent(event)
    assert seen == []
    assert ev.timeline.playhead == pytest.approx(5.0, abs=0.1)


def test_trimming_slices_waveform_instead_of_scaling(main_window):
    from gui.timeline import TimelineClip

    clip = TimelineClip(media=_media("/a.wav", 10.0))
    clip.peaks = [float(i) for i in range(100)]
    clip.peaks_duration = 10.0
    assert clip.visible_peaks() == clip.peaks

    clip.in_point, clip.out_point = 2.0, 6.0
    shown = clip.visible_peaks()
    assert shown == clip.peaks[20:60]
    assert shown[0] == 20.0 and shown[-1] == 59.0

    # A constant seconds-per-pixel scale: 4 s of audio keeps 40 buckets,
    # regardless of where the trim window sits.
    clip.in_point, clip.out_point = 5.0, 9.0
    assert len(clip.visible_peaks()) == 40


class _FakeClock:
    def __init__(self):
        self.ms = 0

    def start(self):
        self.ms = 0

    def elapsed(self):
        return self.ms


def _fake_multimedia():
    created = []

    class FakeQMediaPlayer:
        class PlaybackState:
            PlayingState = 1

        class MediaStatus:
            LoadedMedia = 2
            EndOfMedia = 3

        def __init__(self, parent=None):
            self.source = None
            self.position_ms = None
            self.played = False
            self.stopped = False
            self.mediaStatusChanged = SimpleNamespace(
                connect=lambda slot: None, disconnect=lambda slot: None
            )
            created.append(self)

        def setAudioOutput(self, output):
            pass

        def setSource(self, url):
            self.source = url.toLocalFile()

        def setPosition(self, ms):
            self.position_ms = ms

        def play(self):
            self.played = True

        def stop(self):
            self.stopped = True

    output = lambda parent=None: SimpleNamespace(setVolume=lambda value: None)
    return FakeQMediaPlayer, output, created


def test_playback_starts_voice_with_source_offset(main_window):
    FakeQMediaPlayer, output, created = _fake_multimedia()
    ev = main_window.edit_view
    ev.timeline.add_media(
        _media("/a.wav", 10.0), start=0, track=0, in_point=2.0, out_point=8.0
    )
    ev.timeline.set_playhead(4.0)  # source offset = 2 + (4 - 0) = 6 s
    with (
        patch("gui.edit_view.QMediaPlayer", FakeQMediaPlayer),
        patch("gui.edit_view.QAudioOutput", output),
    ):
        ev._start_playback()
    player = created[0]
    assert player.source == "/a.wav"
    assert player.position_ms == 6000
    assert player.played
    ev.stop_play()
    assert player.stopped


def test_playback_plays_adjacent_then_overlapping_clips(main_window):
    FakeQMediaPlayer, output, created = _fake_multimedia()
    ev = main_window.edit_view
    a = _media("/a.wav", 6.0)
    b = _media("/b.wav", 6.0)
    first = ev.timeline.add_media(a, start=0, track=0)
    second = ev.timeline.add_media(b, start=4.0, track=1)  # overlaps 4..6
    ev._clock = _FakeClock()
    with (
        patch("gui.edit_view.QMediaPlayer", FakeQMediaPlayer),
        patch("gui.edit_view.QAudioOutput", output),
    ):
        ev._start_playback()
        assert list(ev._voices) == [first.clip_id]

        ev._clock.ms = 5000  # t=5s: first still active, second also started
        ev._tick_scheduler()
        assert set(ev._voices) == {first.clip_id, second.clip_id}

        ev._clock.ms = 7000  # t=7s: first ended, second still playing
        ev._tick_scheduler()
        assert list(ev._voices) == [second.clip_id]
        ev.stop_play()
    assert len(created) == 2


def test_playback_schedules_appended_clip(main_window):
    FakeQMediaPlayer, output, created = _fake_multimedia()
    ev = main_window.edit_view
    first = ev.timeline.add_media(_media("/a.wav", 4.0), start=0, track=0)
    second = ev.timeline.add_media(_media("/b.wav", 4.0), start=4.0, track=0)
    ev._clock = _FakeClock()
    with (
        patch("gui.edit_view.QMediaPlayer", FakeQMediaPlayer),
        patch("gui.edit_view.QAudioOutput", output),
    ):
        ev._start_playback()
        assert list(ev._voices) == [first.clip_id]
        ev._clock.ms = 5000
        ev._tick_scheduler()
        assert list(ev._voices) == [second.clip_id]
        assert created[1].source == "/b.wav"
        ev.stop_play()


def test_playback_timer_keeps_running_without_multimedia(main_window):
    ev = main_window.edit_view
    ev.timeline.add_media(_media("/a.wav", 10.0), start=0, track=0)
    with patch("gui.edit_view._HAS_MULTIMEDIA", False):
        ev._start_playback()
    assert ev._play_timer.isActive()
    assert ev._voices == {}
    ev.stop_play()
    assert not ev._play_timer.isActive()


def test_overlap_auto_selects_timeline_mode(main_window):
    ev = main_window.edit_view
    assert ev.mode_combo.currentData() == "stitch"
    ev.timeline.add_media(_media("/a.wav", 5.0), start=0, track=0)
    assert ev.mode_combo.currentData() == "stitch"

    ev.timeline.add_media(_media("/b.wav", 5.0), start=2.0, track=1)
    assert ev.mode_combo.currentData() == "timeline"
    assert "Overlap detected" in ev.feedback_label.text()


def test_manual_render_mode_is_never_overwritten(main_window):
    ev = main_window.edit_view
    ev.timeline.add_media(_media("/a.wav", 5.0), start=0, track=0)
    ev.timeline.add_media(_media("/b.wav", 5.0), start=2.0, track=1)
    assert ev.mode_combo.currentData() == "timeline"

    # The user explicitly prefers Stitch for this overlap.
    ev.mode_combo.setCurrentIndex(ev.mode_combo.findData("stitch"))
    assert ev._mode_locked_by_user
    ev.timeline.add_media(_media("/c.wav", 3.0), start=8.0, track=2)
    ev.timeline.selected_ids.clear()
    ev.timeline.selection_changed.emit()
    assert ev.mode_combo.currentData() == "stitch"


def test_overlap_suggestion_returns_after_overlaps_removed(main_window):
    ev = main_window.edit_view
    first = ev.timeline.add_media(_media("/a.wav", 5.0), start=0, track=0)
    second = ev.timeline.add_media(_media("/b.wav", 5.0), start=2.0, track=1)
    assert ev.mode_combo.currentData() == "timeline"
    ev.mode_combo.setCurrentIndex(ev.mode_combo.findData("stitch"))

    ev.timeline.clips = [first]
    ev.timeline.selected_ids = {first.clip_id}
    ev.timeline.clips_changed.emit()
    assert not ev._mode_locked_by_user

    ev.timeline.add_media(second.media, start=2.0, track=1)
    assert ev.mode_combo.currentData() == "timeline"


def test_adjacent_clips_do_not_trigger_auto_mode(main_window):
    ev = main_window.edit_view
    ev.timeline.add_media(_media("/a.wav", 4.0), start=0, track=0)
    ev.timeline.add_media(_media("/b.wav", 4.0), start=4.0, track=0)
    assert ev.mode_combo.currentData() == "stitch"


def test_copy_paste_clips_preserves_trims_and_relative_positions(main_window, tmp_path):
    from PyQt6.QtWidgets import QApplication
    from gui.edit_view import CLIP_MIME

    QApplication.clipboard().clear()
    ev = main_window.edit_view
    first_path = tmp_path / "a.wav"
    second_path = tmp_path / "b.wav"
    first_path.touch()
    second_path.touch()
    first = ev.timeline.add_media(
        _media(str(first_path), 10.0), start=1.0, track=0, in_point=2.0, out_point=6.0
    )
    second = ev.timeline.add_media(_media(str(second_path), 8.0), start=5.0, track=1)
    ev.timeline.selected_ids = {first.clip_id, second.clip_id}
    ev.copy_clips()

    mime = QApplication.clipboard().mimeData()
    assert mime is not None and mime.hasFormat(CLIP_MIME)
    ev.timeline.set_playhead(20.0)
    ev.timeline.selected_ids.clear()
    ev.paste_clips()

    assert len(ev.timeline.clips) == 4
    pasted = [
        clip
        for clip in ev.timeline.clips
        if clip.clip_id not in {first.clip_id, second.clip_id}
    ]
    assert sorted((clip.start, clip.track) for clip in pasted) == [(20.0, 0), (24.0, 1)]
    copied_first = min(pasted, key=lambda clip: clip.start)
    assert (copied_first.in_point, copied_first.out_point) == (2.0, 6.0)
    assert ev.timeline.playhead == pytest.approx(32.0)
    assert ev.timeline.selected_ids == {clip.clip_id for clip in pasted}
    assert "Pasted 2 clip(s)" in ev.feedback_label.text()


def test_copy_without_selection_and_paste_without_clips(main_window):
    from PyQt6.QtWidgets import QApplication

    QApplication.clipboard().clear()
    ev = main_window.edit_view
    ev.copy_clips()
    assert "Select clips" in ev.feedback_label.text()
    ev.paste_clips()
    assert "No timeline clips" in ev.feedback_label.text()
    assert ev.timeline.clips == []


def test_locale_switch_retranslates_keep_original_entry(main_window):
    from gui import qt_app
    from utils.language_support import tr_key

    class FakeDialog:
        selected_locale = "German"

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return True

    original = qt_app.SettingsDialog
    qt_app.SettingsDialog = FakeDialog
    try:
        main_window.open_settings_dialog()
        assert main_window.edit_view.format_combo.currentText() == tr_key(
            "resolution_original", "German"
        )
        FakeDialog.selected_locale = "Korean"
        main_window.open_settings_dialog()
    finally:
        qt_app.SettingsDialog = original
    assert main_window.locale == "Korean"
    assert main_window.edit_view.format_combo.currentText() == tr_key(
        "resolution_original", "Korean"
    )


def test_preview_button_removed(main_window):
    assert not hasattr(main_window.edit_view, "preview_btn")


def test_timeline_mode_builds_compositing_job(main_window, tmp_path):
    ev = main_window.edit_view
    ev.timeline.add_media(_media("/a.wav", 5.0), start=0, track=0)
    ev.timeline.add_media(_media("/b.mp4", 5.0, "movie"), start=2.0, track=1)
    ev.output_edit.setText(str(tmp_path))
    ev.format_combo.setEditText("mp4,webm")
    ev.mode_combo.setCurrentIndex(ev.mode_combo.findData("timeline"))
    with (
        patch("gui.edit_view.EditExportThread") as thread_class,
        patch("gui.qt_app.QMessageBox"),
        patch("gui.edit_view.QMessageBox"),
    ):
        ev.start_export()
    job = thread_class.call_args[0][0]
    ev.export_thread = None  # mocked thread never finishes; don't block teardown
    assert job["mode"] == "timeline"
    assert job["has_video"] is True
    assert job["output_ext"] == "mp4"
    assert len(job["clips"]) == 2
    assert job["clips"][1]["start"] == 2.0
    assert job["clips"][1]["track"] == 1


def test_render_timeline_preserves_positions_and_trims(tmp_path):
    import threading

    from gui.edit_export import render_timeline

    composites = []

    class FakeAudio:
        def __init__(self, path):
            self.path = path
            self.duration = 100.0
            self.started = None
            self.trim = None

        def subclipped(self, start, end):
            self.trim = (start, end)
            return self

        def with_start(self, value):
            self.started = value
            return self

        def close(self):
            pass

    class FakeCompositeAudio:
        def __init__(self, segments):
            self.segments = segments
            composites.append(self)

        def write_audiofile(self, path, codec=None, logger=None):
            with open(path, "wb") as handle:
                handle.write(b"x")

        def close(self):
            pass

    job = {
        "clips": [
            {"path": "/a.wav", "in": 1.0, "out": 3.0, "duration": 5.0, "start": 0.0},
            {"path": "/b.wav", "in": 0.0, "out": None, "duration": 4.0, "start": 2.0},
        ],
        "output_ext": "mp3",
        "audio_codec": "libmp3lame",
    }
    output = tmp_path / "timeline.mp3"
    with (
        patch("moviepy.AudioFileClip", FakeAudio),
        patch("moviepy.CompositeAudioClip", FakeCompositeAudio),
    ):
        render_timeline(
            job, threading.Event(), str(output), lambda percent, message: None
        )
    assert output.exists()
    assert [segment.started for segment in composites[0].segments] == [0.0, 2.0]
    assert [segment.trim for segment in composites[0].segments] == [
        (1.0, 3.0),
        (0.0, 4.0),
    ]


def test_export_disables_and_restores_editing_controls(main_window, qapp, tmp_path):
    import time

    ev = main_window.edit_view
    runs = []

    class FakeController:
        def __init__(self, job_id=None, shared_progress_dict=None, is_web=False):
            self.file_handler = SimpleNamespace(cancel_event=None)
            self.shared = shared_progress_dict
            self.job_id = job_id
            shared_progress_dict[job_id] = {
                "progress": 0,
                "total": 100,
                "status": "starting",
            }

        def run(self, **kwargs):
            runs.append(kwargs)
            with open(os.path.join(kwargs["output"], "fake.bin"), "wb") as handle:
                handle.write(b"x")
            self.shared[self.job_id].update(progress=100, status="done")

    ev.timeline.add_media(_media("/a.wav", 3.0), start=0, track=0)
    ev.output_edit.setText(str(tmp_path))
    with (
        patch("gui.edit_export.Controller", FakeController),
        patch("gui.edit_export.FFmpegProcessTracker", lambda *a, **k: nullcontext()),
        patch("gui.qt_app.QMessageBox"),
        patch("gui.edit_view.QMessageBox"),
    ):
        ev.start_export()
        assert ev.is_busy()
        assert not ev.cut_btn.isEnabled()
        assert not ev.timeline.isEnabled()
        assert not ev.export_btn.isEnabled()
        thread = ev.export_thread
        assert thread.wait(15000)
        deadline = time.time() + 2
        while time.time() < deadline:
            qapp.processEvents()
            time.sleep(0.02)
    assert runs
    assert ev.cut_btn.isEnabled()
    assert ev.export_btn.isEnabled()
    assert ev.timeline.isEnabled()


def test_render_buttons_match_convert_view(main_window):
    from PyQt6.QtWidgets import QHBoxLayout
    from gui.qt_app import STYLE_CANCEL_BTN, STYLE_CONVERT_BTN

    ev = main_window.edit_view
    assert ev.export_btn.styleSheet() == STYLE_CONVERT_BTN
    assert ev.cancel_btn.styleSheet() == STYLE_CANCEL_BTN

    group = ev.export_btn.parentWidget()
    assert group is not None
    action_row = None
    for i in range(group.layout().count()):
        row = group.layout().itemAt(i).layout()
        if isinstance(row, QHBoxLayout) and any(
            row.itemAt(j).widget() is ev.export_btn for j in range(row.count())
        ):
            action_row = row
            break
    assert action_row is not None
    # A stretch first pushes Cancel / Render to the right, in that order.
    assert action_row.itemAt(0).spacerItem() is not None
    cancel_index = next(
        i
        for i in range(action_row.count())
        if action_row.itemAt(i).widget() is ev.cancel_btn
    )
    render_index = next(
        i
        for i in range(action_row.count())
        if action_row.itemAt(i).widget() is ev.export_btn
    )
    assert cancel_index < render_index


def test_progress_bar_only_visible_during_render(main_window, qapp, tmp_path):
    import time

    ev = main_window.edit_view
    assert ev.progress_bar.isHidden()
    assert ev.status_label.isHidden()

    class FakeController:
        def __init__(self, job_id=None, shared_progress_dict=None, is_web=False):
            self.file_handler = SimpleNamespace(cancel_event=None)
            self.shared = shared_progress_dict
            self.job_id = job_id
            shared_progress_dict[job_id] = {
                "progress": 0,
                "total": 100,
                "status": "starting",
            }

        def run(self, **kwargs):
            os.makedirs(kwargs["output"], exist_ok=True)
            with open(os.path.join(kwargs["output"], "fake.bin"), "wb") as handle:
                handle.write(b"x")
            self.shared[self.job_id].update(progress=100, status="done")

    ev.timeline.add_media(_media("/a.wav", 3.0), start=0, track=0)
    ev.output_edit.setText(str(tmp_path))
    with (
        patch("gui.edit_export.Controller", FakeController),
        patch("gui.edit_export.FFmpegProcessTracker", lambda *a, **k: nullcontext()),
        patch("gui.qt_app.QMessageBox"),
        patch("gui.edit_view.QMessageBox"),
    ):
        ev.start_export()
        assert not ev.progress_bar.isHidden()
        assert not ev.status_label.isHidden()
        assert ev.export_thread.wait(15000)
        deadline = time.time() + 3
        while time.time() < deadline:
            qapp.processEvents()
            time.sleep(0.02)
    assert ev.progress_bar.isHidden()
    assert ev.status_label.isHidden()
