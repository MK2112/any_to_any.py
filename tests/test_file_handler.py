import os

import pytest
from unittest.mock import MagicMock, patch

from core.utils.file_handler import (
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
