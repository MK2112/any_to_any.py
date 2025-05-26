import pytest
import warnings
from any_to_any import Category
from tests.test_fixtures import any_to_any_instance

def test_to_audio_invalid_format(any_to_any_instance, tmp_path):
    invalid_file = tmp_path / "invalid_file.mp3"
    invalid_file.touch()
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Exception ignored in: <function FFMPEG_AudioReader.__del__.*AttributeError: 'FFMPEG_AudioReader' object has no attribute 'proc'",
            category=Warning,
        )
        with pytest.raises((OSError, KeyError)):
            any_to_any_instance.to_audio(file_paths={Category.AUDIO: [((str(tmp_path) + "/"), 'invalid_file', 'mp3')]}, format='invalid_format', codec='libmp3lame')

def test_to_gif_handles_invalid_file(any_to_any_instance, tmp_path):
    fake_file = tmp_path / "fake.mp3"
    # This is funny, I like this pattern, need to suppress any rambling from ffmpeg though
    fake_file.write_bytes(b"\x00" * 128)
    with pytest.raises(Exception):
        any_to_any_instance.to_gif({'audio': [(str(tmp_path) + "/", 'fake', 'mp3')]}, 'gif')

def test_to_bmp_with_image(any_to_any_instance, tmp_path):
    fake_file = tmp_path / "fake.jpg"
    fake_file.write_bytes(b"\x00" * 128)
    with pytest.raises(Exception):
        any_to_any_instance.to_bmp({'image': [(str(tmp_path) + "/", 'fake', 'jpg')]}, 'bmp')

def test_to_webp_with_image(any_to_any_instance, tmp_path):
    fake_file = tmp_path / "fake.png"
    fake_file.write_bytes(b"\x00" * 128)
    with pytest.raises(Exception):
        any_to_any_instance.to_webp({'image': [(str(tmp_path) + "/", 'fake', 'png')]}, 'webp')

def test_to_frames_with_pdf(any_to_any_instance, tmp_path):
    fake_file = tmp_path / "fake.pdf"
    fake_file.write_bytes(b"%PDF-1.4\n%Fake PDF\n")
    with pytest.raises(Exception):
        any_to_any_instance.to_frames({'document': [(str(tmp_path) + "/", 'fake', 'pdf')]}, 'png')

def test_to_audio_unsupported_format(any_to_any_instance, tmp_path):
    fake_file = tmp_path / "test.wav"
    fake_file.write_bytes(b"\x00" * 128)
    with pytest.raises(Exception):
        any_to_any_instance.to_audio({'audio': [(str(tmp_path) + "/", 'test', 'wav')]}, 'xyz', 'libmp3lame')

def test_to_movie_invalid_codec(any_to_any_instance, tmp_path):
    fake_file = tmp_path / "test.mp4"
    fake_file.write_bytes(b"\x00" * 128)
    with pytest.raises(Exception):
        any_to_any_instance.to_movie({'movie': [(str(tmp_path) + "/", 'test', 'mp4')]}, 'mp4', 'invalid_codec')

def test_to_subtitles_invalid_format(any_to_any_instance, tmp_path):
    fake_file = tmp_path / "test.srt"
    fake_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    with pytest.raises(Exception):
        any_to_any_instance.to_subtitles({'document': [(str(tmp_path) + "/", 'test', 'srt')]}, 'xyz')
