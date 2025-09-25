import os
import sys
import pytest
from pathlib import Path
from utils.category import Category
from core.audio_converter import AudioConverter
from moviepy import AudioFileClip, VideoFileClip
from unittest.mock import Mock, MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAudioConverter:
    @pytest.fixture
    def mock_dependencies(self):
        # Create mock dependencies for AudioConverter
        file_handler = Mock()
        prog_logger = Mock()
        event_logger = Mock()
        return file_handler, prog_logger, event_logger

    @pytest.fixture
    def audio_converter(self, mock_dependencies):
        # Create AudioConverter instance with mocked dependencies
        file_handler, prog_logger, event_logger = mock_dependencies
        return AudioConverter(file_handler, prog_logger, event_logger, "English")

    @pytest.fixture
    def sample_file_paths(self):
        # Sample file paths structure for testing
        return {
            Category.AUDIO: [
                ("/path/to", "audio1", "mp3"),
                ("/path/to", "audio2", "wav"),
                ("/path/to", "audio3", "flac"),
            ],
            Category.MOVIE: [
                ("/path/to", "video1", "mp4"),
                ("/path/to", "video2", "avi"),
                ("/path/to", "audio_only", "mkv"),
            ],
        }

    def test_init_stores_references_correctly(self, mock_dependencies):
        # Test that AudioConverter stores references to passed objects
        file_handler, prog_logger, event_logger = mock_dependencies
        converter = AudioConverter(file_handler, prog_logger, event_logger, "French")

        assert converter.file_handler is file_handler
        assert converter.prog_logger is prog_logger
        assert converter.event_logger is event_logger
        assert converter.locale == "French"

    def test_init_default_locale(self, mock_dependencies):
        # Test that default locale is English
        file_handler, prog_logger, event_logger = mock_dependencies
        converter = AudioConverter(file_handler, prog_logger, event_logger)

        assert converter.locale == "English"

    @patch("core.audio_converter.AudioFileClip")
    def test_audio_conversion_skips_same_format(
        self, mock_audio_clip, audio_converter, mock_dependencies
    ):
        # Test that conversion is skipped when source and target format are the same
        file_handler, prog_logger, event_logger = mock_dependencies

        file_paths = {Category.AUDIO: [("/path", "audio", "mp3")], Category.MOVIE: []}

        audio_converter.to_audio(
            file_paths, "mp3", "mp3", False, "128k", "/input", "/output", "no"
        )

        # Should not create AudioFileClip for same format
        mock_audio_clip.assert_not_called()

    @patch("core.audio_converter.AudioFileClip")
    @patch("os.path.abspath")
    @patch("os.path.join")
    def test_audio_conversion_recursive_mode(
        self,
        mock_join,
        mock_abspath,
        mock_audio_clip,
        audio_converter,
        mock_dependencies,
    ):
        # Test recursive mode places output in source directory
        file_handler, prog_logger, event_logger = mock_dependencies

        mock_audio = Mock()
        mock_audio.fps = 44100
        mock_audio_clip.return_value = mock_audio
        mock_abspath.return_value = "/path/to/audio1.mp3"
        file_handler.join_back.return_value = "/path/to/audio1.wav"

        file_paths = {
            Category.AUDIO: [("/path/to", "audio1", "wav")],
            Category.MOVIE: [],
        }

        audio_converter.to_audio(
            file_paths, "mp3", "mp3", True, "128k", "/input", "/input", "no"
        )

        # Should use source directory for output in recursive mode
        mock_join.assert_called_with("/path/to", "audio1.mp3")

    @patch("core.audio_converter.AudioFileClip")
    @patch("utils.language_support.get_translation")
    @patch("os.path.exists")
    def test_audio_conversion_fps_fallback(
        self,
        mock_exists,
        mock_get_translation,
        mock_audio_clip,
        audio_converter,
        mock_dependencies,
    ):
        # Test fallback to 48000 fps when source rate is incompatible
        file_handler, prog_logger, event_logger = mock_dependencies

        mock_audio = Mock()
        mock_audio.fps = 44100
        mock_audio.duration = 30.0  # Add duration property
        mock_audio_clip.return_value = mock_audio
        file_handler.join_back.return_value = "/path/to/audio1.wav"
        mock_exists.return_value = True  # Make sure the file appears to exist

        # First call raises exception, second succeeds
        mock_audio.write_audiofile.side_effect = [Exception("Rate error"), None]
        mock_get_translation.side_effect = [
            "Error",
            "Source rate incompatible with mp3",
        ]

        file_paths = {
            Category.AUDIO: [("/path/to", "audio1", "wav")],
            Category.MOVIE: [],
        }

        audio_converter.to_audio(
            file_paths, "mp3", "mp3", False, "128k", "/input", "/output", "no"
        )

        # Should be called twice - once failing, once with fps=48000
        assert mock_audio.write_audiofile.call_count == 2
        second_call = mock_audio.write_audiofile.call_args_list[1]
        assert second_call[1]["fps"] == 48000
        event_logger.info.assert_called_once()

    @patch("core.audio_converter.VideoFileClip")
    @patch("os.path.abspath")
    @patch("os.path.join")
    @patch("os.path.exists")
    def test_video_to_audio_conversion_with_visuals(
        self,
        mock_exists,
        mock_join,
        mock_abspath,
        mock_video_clip,
        audio_converter,
        mock_dependencies,
    ):
        # Test video to audio conversion for files with visuals
        file_handler, prog_logger, event_logger = mock_dependencies

        mock_video = Mock()
        mock_audio = Mock()
        mock_audio.fps = 44100
        mock_audio.duration = 30.0  # Add duration property
        mock_video.audio = mock_audio
        mock_video.fps = 30
        mock_video.duration = 30.0  # Add duration property
        mock_video_clip.return_value = mock_video
        mock_abspath.return_value = "/output/video1.mp3"
        file_handler.has_visuals.return_value = True
        file_handler.join_back.return_value = "/path/to/video1.mp4"
        mock_exists.return_value = True  # Make sure the file appears to exist

        file_paths = {
            Category.AUDIO: [],
            Category.MOVIE: [("/path/to", "video1", "mp4")],
        }

        audio_converter.to_audio(
            file_paths, "mp3", "mp3", False, "128k", "/input", "/output", "no"
        )

        # Verify video file processing
        mock_video_clip.assert_called_with(
            "/path/to/video1.mp4", audio=True, fps_source="tbr"
        )
        mock_audio.write_audiofile.assert_called_with(
            "/output/video1.mp3", codec="mp3", bitrate="128k", logger=prog_logger
        )
        mock_audio.close.assert_called()
        mock_video.close.assert_called()

    @patch("core.audio_converter.VideoFileClip")
    @patch("utils.language_support.get_translation")
    @patch("os.path.exists")
    def test_video_to_audio_no_audio_track(
        self,
        mock_exists,
        mock_get_translation,
        mock_video_clip,
        audio_converter,
        mock_dependencies,
    ):
        # Test handling of video files with no audio track
        file_handler, prog_logger, event_logger = mock_dependencies

        mock_video = Mock()
        mock_video.fps = 30
        mock_video.duration = 30.0  # Add duration property
        mock_video.audio = None  # No audio track
        mock_video_clip.return_value = mock_video
        file_handler.has_visuals.return_value = True
        file_handler.join_back.return_value = "/path/to/video1.mp4"
        mock_get_translation.side_effect = ["No audio found", "Skipping"]
        mock_exists.return_value = True  # Make sure the file appears to exist

        file_paths = {
            Category.AUDIO: [],
            Category.MOVIE: [("/path/to", "video1", "mp4")],
        }

        audio_converter.to_audio(
            file_paths, "mp3", "mp3", False, "128k", "/input", "/output", "no"
        )

        # Should log warning and continue
        event_logger.info.assert_called_once()
        mock_video.close.assert_called()
        file_handler.post_process.assert_not_called()

    @patch("core.audio_converter.AudioFileClip")
    @patch("core.audio_converter.VideoFileClip")
    @patch("os.path.exists")
    def test_video_to_audio_audio_only_file(
        self,
        mock_exists,
        mock_video_clip,
        mock_audio_clip,
        audio_converter,
        mock_dependencies,
    ):
        # Test handling of audio-only video container files
        file_handler, prog_logger, event_logger = mock_dependencies

        mock_audio = Mock()
        mock_audio.fps = 44100
        mock_audio.duration = 30.0  # Add duration property
        mock_audio_clip.return_value = mock_audio
        file_handler.has_visuals.return_value = False
        file_handler.join_back.return_value = "/path/to/audio_only.mkv"
        mock_exists.return_value = True  # Make sure the file appears to exist

        file_paths = {
            Category.AUDIO: [],
            Category.MOVIE: [("/path/to", "audio_only", "mkv")],
        }

        audio_converter.to_audio(
            file_paths, "mp3", "mp3", False, "128k", "/input", "/output", "no"
        )

        # Should use AudioFileClip instead of VideoFileClip
        mock_video_clip.assert_not_called()
        mock_audio_clip.assert_called_with("/path/to/audio_only.mkv")
        mock_audio.write_audiofile.assert_called()
        mock_audio.close.assert_called()

    @patch("core.audio_converter.AudioFileClip")
    @patch("utils.language_support.get_translation")
    @patch("os.path.exists")
    def test_video_to_audio_extraction_failure(
        self,
        mock_exists,
        mock_get_translation,
        mock_audio_clip,
        audio_converter,
        mock_dependencies,
    ):
        # Test handling of audio extraction failure from video files
        file_handler, prog_logger, event_logger = mock_dependencies

        mock_audio_clip.side_effect = Exception("Extraction failed")
        file_handler.has_visuals.return_value = False
        file_handler.join_back.return_value = "/path/to/corrupted.mkv"
        mock_get_translation.side_effect = ["Audio extraction failed", "Skipping"]
        mock_exists.return_value = True  # Make sure the file appears to exist

        file_paths = {
            Category.AUDIO: [],
            Category.MOVIE: [("/path/to", "corrupted", "mkv")],
        }

        audio_converter.to_audio(
            file_paths, "mp3", "mp3", False, "128k", "/input", "/output", "no"
        )

        # Should log error and continue
        event_logger.info.assert_called_once()
        file_handler.post_process.assert_not_called()

    def test_empty_file_paths(self, audio_converter):
        # Test handling of empty file paths
        empty_paths = {Category.AUDIO: [], Category.MOVIE: []}

        # Should not raise any exceptions
        audio_converter.to_audio(
            empty_paths, "mp3", "mp3", False, "128k", "/input", "/output", "no"
        )

    @patch("core.audio_converter.AudioFileClip")
    @patch("core.audio_converter.VideoFileClip")
    @patch("os.path.exists")
    def test_multiple_files_processing(
        self,
        mock_exists,
        mock_video_clip,
        mock_audio_clip,
        audio_converter,
        mock_dependencies,
        sample_file_paths,
    ):
        # Test processing multiple audio and video files
        file_handler, prog_logger, event_logger = mock_dependencies

        # Setup mocks for audio files
        mock_audio = Mock()
        mock_audio.fps = 44100
        mock_audio.duration = 30.0  # Add duration property

        # Setup mocks for video files
        mock_video = Mock()
        mock_video.fps = 30
        mock_video.duration = 30.0  # Add duration property
        mock_video_audio = Mock()
        mock_video_audio.fps = 44100
        mock_video_audio.duration = 30.0  # Add duration property
        mock_video.audio = mock_video_audio
        mock_video_clip.return_value = mock_video

        file_handler.has_visuals.return_value = True
        file_handler.join_back.side_effect = [
            "/path/to/audio1.mp3",
            "/path/to/audio2.wav",
            "/path/to/audio3.flac",
            "/path/to/video1.mp4",
            "/path/to/video2.avi",
            "/path/to/audio_only.mkv",
        ]
        mock_exists.return_value = True  # Make sure the files appear to exist

        audio_converter.to_audio(
            sample_file_paths, "wav", "pcm", False, "1411k", "/input", "/output", "no"
        )

        # Should process audio files (skip first one as it's already mp3->wav conversion)
        assert mock_audio_clip.call_count >= 2
        assert mock_video_clip.call_count >= 3
        assert file_handler.post_process.call_count >= 5

    @pytest.mark.parametrize(
        "locale,expected_calls", [("English", 1), ("Spanish", 1), ("French", 1)]
    )
    def test_different_locales(self, locale, expected_calls, mock_dependencies):
        # Test AudioConverter works with different locales
        file_handler, prog_logger, event_logger = mock_dependencies
        converter = AudioConverter(file_handler, prog_logger, event_logger, locale)

        assert converter.locale == locale

    def test_parameter_passing_integrity(self, audio_converter, mock_dependencies):
        # Test that all parameters are passed correctly through the chain
        file_handler, prog_logger, event_logger = mock_dependencies

        # Test with specific parameter values
        test_params = {
            "format": "ogg",
            "codec": "vorbis",
            "recursive": True,
            "bitrate": "320k",
            "input": "/custom/input",
            "output": "/custom/output",
            "delete": "yes",
        }

        empty_paths = {Category.AUDIO: [], Category.MOVIE: []}

        # Should not raise exceptions with custom parameters
        audio_converter.to_audio(empty_paths, **test_params)


# --- Additional audio converter tests ---
def test_to_audio_single_file_triggers_post_process(monkeypatch, tmp_path):
    # Create local mock dependencies to avoid relying on test class fixtures
    file_handler = Mock()
    file_handler.join_back.return_value = str(tmp_path / "sample.wav")
    file_handler.post_process = Mock()
    prog_logger = Mock()
    event_logger = Mock()
    conv = AudioConverter(file_handler, prog_logger, event_logger)

    audio_item = ((str(tmp_path) + "/"), "sample", "wav")
    file_paths = {Category.AUDIO: [audio_item], Category.MOVIE: []}

    mock_clip = MagicMock()
    mock_clip.fps = 44100
    mock_clip.write_audiofile = MagicMock()
    monkeypatch.setattr("core.audio_converter.AudioFileClip", lambda path: mock_clip)

    conv.to_audio(
        file_paths,
        format="mp3",
        codec="libmp3lame",
        recursive=False,
        bitrate="192k",
        input=str(tmp_path),
        output=str(tmp_path),
        delete=False,
    )

    assert file_handler.post_process.call_count == 1


def test_to_audio_skips_if_same_format(monkeypatch, tmp_path):
    # local mocks
    file_handler = Mock()
    prog_logger = Mock()
    event_logger = Mock()
    conv = AudioConverter(file_handler, prog_logger, event_logger)

    audio_item = ((str(tmp_path) + "/"), "same", "mp3")
    file_paths = {Category.AUDIO: [audio_item], Category.MOVIE: []}

    called = {"count": 0}

    def fake_clip(path):
        called["count"] += 1
        return MagicMock()

    monkeypatch.setattr("core.audio_converter.AudioFileClip", fake_clip)

    conv.to_audio(
        file_paths,
        format="mp3",
        codec="libmp3lame",
        recursive=False,
        bitrate="128k",
        input=str(tmp_path),
        output=str(tmp_path),
        delete=False,
    )

    # Should not have opened a clip because format matched
    assert called["count"] == 0


# Integration-style tests
class TestAudioConverterIntegration:
    # Integration tests that test broader functionality

    @patch("core.audio_converter.AudioFileClip")
    @patch("core.audio_converter.VideoFileClip")
    @patch("utils.language_support.get_translation")
    @patch("os.path.exists")
    def test_mixed_success_and_failure_scenario(
        self, mock_exists, mock_get_translation, mock_video_clip, mock_audio_clip
    ):
        # Test scenario with mix of successful and failed conversions
        # Setup
        file_handler = Mock()
        prog_logger = Mock()
        event_logger = Mock()
        converter = AudioConverter(file_handler, prog_logger, event_logger)

        # Mock successful audio conversion
        mock_successful_audio = Mock()
        mock_successful_audio.fps = 44100
        mock_successful_audio.duration = 30.0  # Add duration property

        # Mock failing audio conversion
        mock_failing_audio = Mock()
        mock_failing_audio.fps = 44100
        mock_failing_audio.duration = 30.0  # Add duration property
        mock_failing_audio.write_audiofile.side_effect = Exception("Write failed")

        mock_audio_clip.side_effect = [mock_successful_audio, mock_failing_audio]

        # Mock video with no audio
        mock_video = Mock()
        mock_video.fps = 30
        mock_video.duration = 30.0  # Add duration property
        mock_video.audio = None
        mock_video_clip.return_value = mock_video

        file_handler.has_visuals.return_value = True
        file_handler.join_back.side_effect = [
            "/path/audio1.wav",
            "/path/audio2.mp3",
            "/path/video1.mp4",
        ]
        mock_get_translation.return_value = "Error message"
        mock_exists.return_value = True  # Make sure the files appear to exist

        file_paths = {
            Category.AUDIO: [("/path", "audio1", "wav"), ("/path", "audio2", "mp3")],
            Category.MOVIE: [("/path", "video1", "mp4")],
        }

        # Execute
        converter.to_audio(
            file_paths, "mp3", "mp3", False, "128k", "/input", "/output", "no"
        )

        # Verify mixed results
        assert mock_successful_audio.write_audiofile.called
        assert mock_successful_audio.close.called
        assert file_handler.post_process.call_count == 1  # Only successful conversion

        # Check that error was logged for both failed cases
        error_messages = [call[0][0] for call in event_logger.info.call_args_list]
        assert any("Error message" in str(msg) for msg in error_messages)
