import pytest
import warnings
from utils.category import Category
from tests.test_fixtures import controller_instance


def test_to_audio_invalid_format(controller_instance, tmp_path):
    invalid_file = tmp_path / "invalid_file.mp3"
    invalid_file.touch()
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Exception ignored in: <function FFMPEG_AudioReader.__del__.*AttributeError: 'FFMPEG_AudioReader' object has no attribute 'proc'",
            category=Warning,
        )
        with pytest.raises((OSError, KeyError)):
            controller_instance.audio_converter.to_audio(
                file_paths={
                    Category.AUDIO: [((str(tmp_path) + "/"), "invalid_file", "mp3")]
                },
                format="invalid_format",
                codec="libmp3lame",
                recursive=False,
                bitrate="192k",
                input=str(tmp_path),
                output=str(tmp_path),
                delete="no",
            )


def test_to_gif_handles_invalid_file(controller_instance, tmp_path):
    fake_file = tmp_path / "fake.mp3"
    fake_file.write_bytes(b"\x00" * 128)
    with pytest.raises(Exception):
        controller_instance.to_gif(
            {Category.AUDIO: [(str(tmp_path) + "/", "fake", "mp3")]}, "gif"
        )


def test_to_bmp_with_image(controller_instance, tmp_path):
    fake_file = tmp_path / "fake.jpg"
    fake_file.write_bytes(b"\x00" * 128)
    with pytest.raises(Exception):
        controller_instance.to_bmp(
            {Category.IMAGE: [(str(tmp_path) + "/", "fake", "jpg")]}, "bmp"
        )


def test_to_webp_with_image(controller_instance, tmp_path):
    fake_file = tmp_path / "fake.png"
    fake_file.write_bytes(b"\x00" * 128)
    with pytest.raises(Exception):
        controller_instance.to_webp(
            {Category.IMAGE: [(str(tmp_path) + "/", "fake", "png")]}, "webp"
        )


def test_to_frames_with_pdf(controller_instance, tmp_path):
    fake_file = tmp_path / "fake.pdf"
    fake_file.write_bytes(b"%PDF-1.4\n%Fake PDF\n")
    with pytest.raises(Exception):
        controller_instance.to_frames(
            {Category.DOCUMENT: [(str(tmp_path) + "/", "fake", "pdf")]}, "png"
        )


def test_to_audio_unsupported_format(controller_instance, tmp_path):
    fake_file = tmp_path / "test.wav"
    fake_file.write_bytes(b"\x00" * 128)
    with pytest.raises(Exception):
        controller_instance.audio_converter.to_audio(
            file_paths={Category.AUDIO: [(str(tmp_path) + "/", "test", "wav")]},
            format="xyz",
            codec="libmp3lame",
            recursive=False,
            bitrate="192k",
            input=str(tmp_path),
            output=str(tmp_path),
            delete="no",
        )


def test_to_movie_invalid_codec(controller_instance, tmp_path):
    fake_file = tmp_path / "test.mp4"
    fake_file.write_bytes(b"\x00" * 128)
    with pytest.raises(Exception):
        controller_instance.to_movie(
            {Category.MOVIE: [(str(tmp_path) + "/", "test", "mp4")]},
            "mp4",
            "invalid_codec",
        )


def test_to_subtitles_invalid_format(controller_instance, tmp_path):
    fake_file = tmp_path / "test.srt"
    fake_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    with pytest.raises(Exception):
        controller_instance.to_subtitles(
            {Category.DOCUMENT: [(str(tmp_path) + "/", "test", "srt")]}, "xyz"
        )
