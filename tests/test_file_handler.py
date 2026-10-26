import os
import sys
import time
import shutil
import threading
import subprocess

import pytest
from unittest.mock import MagicMock, patch

from core.utils.file_handler import (
    FFmpegProcessTracker,
    FileHandler,
    effective_fps,
    resolve_worker_count,
    sort_frame_filenames,
    worker_count_for,
)
from tests.test_fixtures import controller_instance


def _handler():
    return FileHandler(event_logger=MagicMock(), locale="English")


@patch("core.utils.file_handler.VideoFileClip")
def test_has_visuals_true_when_frame_readable(mock_vfc):
    clip = MagicMock()
    clip.iter_frames.return_value = iter([MagicMock()])
    mock_vfc.return_value = clip

    assert _handler().has_visuals(("dir", "video", "mp4")) is True
    clip.close.assert_called_once()


@patch("core.utils.file_handler.VideoFileClip")
def test_has_visuals_false_when_no_decodable_frame(mock_vfc):
    # Regression: iter_frames() is lazy, so merely creating the generator
    # never raises. The old check therefore returned True without decoding
    # anything, misrouting audio-only/unreadable files into the video path.
    clip = MagicMock()
    clip.iter_frames.return_value = iter([])
    mock_vfc.return_value = clip

    assert _handler().has_visuals(("dir", "audio", "mp4")) is False
    clip.close.assert_called_once()


@patch("core.utils.file_handler.VideoFileClip", side_effect=OSError("no video stream"))
def test_has_visuals_false_when_open_fails(mock_vfc):
    assert _handler().has_visuals(("dir", "audio", "mp3")) is False


@patch("core.utils.file_handler.VideoFileClip")
def test_has_visuals_reuses_passed_clip_without_closing_it(mock_vfc):
    clip = MagicMock()
    clip.iter_frames.return_value = iter([MagicMock()])

    assert _handler().has_visuals(("dir", "video", "mp4"), clip=clip) is True
    mock_vfc.assert_not_called()
    clip.close.assert_not_called()


@patch("core.utils.file_handler.VideoFileClip")
def test_has_visuals_false_for_passed_clip_without_frames(mock_vfc):
    clip = MagicMock()
    clip.iter_frames.return_value = iter([])

    assert _handler().has_visuals(("dir", "audio", "mp4"), clip=clip) is False
    mock_vfc.assert_not_called()
    clip.close.assert_not_called()


def test_sort_frame_filenames_numeric_order():
    frames = [f"clip-{i}.png" for i in (1, 2, 10, 9, 11, 3, 20)]
    assert sort_frame_filenames(frames) == [
        "clip-1.png",
        "clip-2.png",
        "clip-3.png",
        "clip-9.png",
        "clip-10.png",
        "clip-11.png",
        "clip-20.png",
    ]


def test_sort_frame_filenames_zero_padded_and_mixed():
    frames = ["doc-007.jpeg", "doc-010.jpeg", "doc-002.jpeg", "notes.txt"]
    assert sort_frame_filenames(frames) == [
        "doc-002.jpeg",
        "doc-007.jpeg",
        "doc-010.jpeg",
        "notes.txt",
    ]


def test_sort_frame_filenames_non_numeric_sorts_last_by_name():
    assert sort_frame_filenames(["b.png", "a.png", "clip-1.png"]) == [
        "clip-1.png",
        "a.png",
        "b.png",
    ]


def test_resolve_worker_count_garbage_env_falls_back(monkeypatch):
    monkeypatch.setenv("Any2Any_MAX_WORKERS", "bogus")
    assert resolve_worker_count() == 1


def test_resolve_worker_count_cpu_none_does_not_crash(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: None)
    monkeypatch.setenv("Any2Any_MAX_WORKERS", "4")
    assert resolve_worker_count() == 4


def test_resolve_worker_count_single_cpu_yields_one(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 1)
    monkeypatch.setenv("Any2Any_MAX_WORKERS", "8")
    assert resolve_worker_count() == 1


def test_resolve_worker_count_caps_at_cpu_minus_one(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 4)
    monkeypatch.setenv("Any2Any_MAX_WORKERS", "8")
    assert resolve_worker_count() == 3


def test_worker_count_for_prefers_instance_snapshot(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    monkeypatch.setenv("Any2Any_MAX_WORKERS", "7")
    handler = _handler()
    handler.max_workers = 2
    assert worker_count_for(handler) == 2


def test_worker_count_for_ignores_non_int_snapshot(monkeypatch):
    monkeypatch.delenv("Any2Any_MAX_WORKERS", raising=False)
    assert worker_count_for(MagicMock()) == 1


def test_controller_run_snapshots_workers_without_env(
    controller_instance, tmp_path, monkeypatch
):
    monkeypatch.delenv("Any2Any_MAX_WORKERS", raising=False)
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(SystemExit):
        controller_instance.run(
            [str(empty_dir)],
            format="mp3",
            output=str(tmp_path),
            framerate=None,
            quality=None,
            split=None,
            merge=False,
            concat=False,
            delete=False,
            across=False,
            recursive=False,
            dropzone=False,
            language=None,
            workers=2,
        )
    assert controller_instance.file_handler.max_workers == 2
    assert "Any2Any_MAX_WORKERS" not in os.environ


def test_effective_fps_requested_wins():
    assert effective_fps(None, 30) == 30
    assert effective_fps(24, 30) == 30


def test_effective_fps_falls_back_to_clip_then_default():
    assert effective_fps(29.97, None) == 29.97
    assert effective_fps(None, None) == 24
    assert effective_fps(0, None) == 24


def test_effective_fps_custom_default_for_audio():
    # Audio sample rates use their own default, not 24 fps video
    assert effective_fps(None, None, default=48000) == 48000


def test_post_process_stops_before_deleting_when_cancelled(tmp_path):
    # Once cancelled, no further source may be removed
    import threading
    from core.utils.file_handler import ConversionCancelled

    handler = _handler()
    handler.cancel_event = threading.Event()
    handler.cancel_event.set()
    src = tmp_path / "in.mp3"
    src.write_bytes(b"source")
    out = tmp_path / "out.mp3"
    out.write_bytes(b"converted")

    with pytest.raises(ConversionCancelled):
        handler.post_process(
            (str(tmp_path) + os.sep, "in", "mp3"), str(out), delete=True
        )

    assert src.exists()
    assert out.exists()


def test_post_process_unchanged_without_cancel_event(tmp_path):
    handler = _handler()
    src = tmp_path / "in.mp3"
    src.write_bytes(b"source")
    out = tmp_path / "out.mp3"
    out.write_bytes(b"converted")

    handler.post_process((str(tmp_path) + os.sep, "in", "mp3"), str(out), delete=True)

    assert not src.exists()
    assert out.exists()


def test_post_process_releases_claim_for_missing_output(tmp_path):
    from core.utils.file_handler import _CLAIMED

    handler = _handler()
    target = str(tmp_path / "ghost.mp3")

    assert handler._resolve_output_file_conflict(target) == target
    assert target in _CLAIMED

    handler.post_process((str(tmp_path) + os.sep, "src", "wav"), target, delete=False)

    assert target not in _CLAIMED


def test_release_job_claims_frees_reserved_names(tmp_path):
    from core.utils.file_handler import _CLAIMED

    handler = _handler()
    target = str(tmp_path / "later.mp3")
    handler._resolve_output_file_conflict(target)
    assert target in _CLAIMED

    handler.release_job_claims()

    assert handler._job_claims == set()
    assert target not in _CLAIMED
    # The name is claimable again without being pushed to later_1.mp3
    assert handler._resolve_output_file_conflict(target) == target
    handler.release_job_claims()


def test_check_cancelled_is_noop_while_event_unset():
    import threading

    handler = _handler()
    handler.cancel_event = threading.Event()
    handler.check_cancelled()  # set() never called: must not raise


def test_process_file_paths_stops_before_dispatch_when_cancelled(
    controller_instance,
):
    import threading

    from core.utils.file_handler import ConversionCancelled
    from utils.category import Category

    file_handler = controller_instance.file_handler
    file_handler.cancel_event = threading.Event()
    file_handler.cancel_event.set()

    with pytest.raises(ConversionCancelled):
        controller_instance.process_file_paths({category: [] for category in Category})


def _fake_ffmpeg(tmp_path):
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    path = tmp_path / name
    try:
        os.symlink(sys.executable, path)
    except OSError:
        shutil.copy2(sys.executable, path)
    return str(path)


def test_ffmpeg_process_tracker_terminates_on_cancel(tmp_path):
    event = threading.Event()
    original_popen = subprocess.Popen
    process = None
    with FFmpegProcessTracker(event):
        assert subprocess.Popen is not original_popen
        process = subprocess.Popen(
            [_fake_ffmpeg(tmp_path), "-c", "import time; time.sleep(30)"]
        )
        try:
            event.set()
            deadline = time.time() + 5
            while process.poll() is None and time.time() < deadline:
                time.sleep(0.05)
            assert process.poll() is not None
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    assert subprocess.Popen is original_popen


def test_ffmpeg_process_tracker_ignores_other_commands():
    event = threading.Event()
    process = None
    with FFmpegProcessTracker(event):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"]
        )
        try:
            event.set()
            time.sleep(0.3)
            assert process.poll() is None
        finally:
            process.kill()
            process.wait()
