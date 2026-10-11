from unittest.mock import MagicMock, patch

from core.utils.file_handler import FileHandler


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


@patch(
    "core.utils.file_handler.VideoFileClip", side_effect=OSError("no video stream")
)
def test_has_visuals_false_when_open_fails(mock_vfc):
    assert _handler().has_visuals(("dir", "audio", "mp3")) is False
