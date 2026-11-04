import shutil
import subprocess
import wave
from unittest import mock

import pytest

from core.converter.audio_converter import AudioConverter
from core.converter.movie_converter import MovieConverter
from tests.test_fixtures import controller_instance, setup_file_handler_mock
from utils.category import Category


def _write_wav(path, seconds=4, rate=8000):
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(b"\x00\x00" * int(rate * seconds))


def _wav_duration(path):
    with wave.open(str(path), "rb") as source:
        return source.getnframes() / source.getframerate()


def _media_duration(path):
    return float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            text=True,
        ).strip()
    )


def _make_test_video(path, seconds=3):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=red:s=32x32:d={seconds}:r=10",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def _run(controller, input_path, output_path, formats, **kwargs):
    controller.run(
        [str(input_path)],
        format=formats,
        output=str(output_path),
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
        workers=1,
        **kwargs,
    )


def test_audio_trim_uses_subclipped_and_preserves_format():
    file_handler = mock.Mock()
    setup_file_handler_mock(file_handler)
    file_handler.join_back.return_value = "/input/sample.wav"
    file_handler.post_process = mock.Mock()
    converter = AudioConverter(file_handler, mock.Mock(), mock.Mock(), "English")
    clip = mock.MagicMock()
    clip.duration = 10
    clip.fps = 44100
    segment = mock.MagicMock()
    segment.fps = 44100
    clip.subclipped.return_value = segment

    with mock.patch(
        "core.converter.audio_converter.AudioFileClip", return_value=clip
    ):
        converter.to_audio(
            file_paths={Category.AUDIO: [("/input", "sample", "wav")], Category.MOVIE: []},
            format="wav",
            codec="pcm_s16le",
            recursive=False,
            bitrate="192k",
            input="/input",
            output="/output",
            delete=False,
            trim=(2, 5),
        )

    clip.subclipped.assert_called_once_with(2, 5)
    segment.write_audiofile.assert_called_once()
    assert segment.write_audiofile.call_args.args[0].endswith("sample.wav")
    file_handler.post_process.assert_called_once()


def test_audio_split_at_creates_numbered_parts():
    file_handler = mock.Mock()
    setup_file_handler_mock(file_handler)
    file_handler.join_back.return_value = "/input/sample.wav"
    file_handler.post_process = mock.Mock()
    converter = AudioConverter(file_handler, mock.Mock(), mock.Mock(), "English")
    clip = mock.MagicMock()
    clip.duration = 10
    clip.fps = 44100
    segments = [mock.MagicMock(), mock.MagicMock(), mock.MagicMock()]
    for segment in segments:
        segment.fps = 44100
    clip.subclipped.side_effect = segments

    with mock.patch(
        "core.converter.audio_converter.AudioFileClip", return_value=clip
    ):
        converter.to_audio(
            file_paths={Category.AUDIO: [("/input", "sample", "wav")], Category.MOVIE: []},
            format="mp3",
            codec="libmp3lame",
            recursive=False,
            bitrate="192k",
            input="/input",
            output="/output",
            delete=False,
            split_at=[3, 6],
        )

    assert clip.subclipped.call_args_list == [mock.call(0.0, 3.0), mock.call(3.0, 6.0), mock.call(6.0, 10.0)]
    written = [segment.write_audiofile.call_args.args[0] for segment in segments]
    assert [part.rsplit("/", 1)[-1] for part in written] == [
        "sample_part_1.mp3",
        "sample_part_2.mp3",
        "sample_part_3.mp3",
    ]
    assert file_handler.post_process.call_count == 3


def test_movie_trim_uses_subclipped_and_preserves_format():
    file_handler = mock.MagicMock()
    setup_file_handler_mock(file_handler)
    file_handler.join_back.return_value = "/input/clip.mp4"
    file_handler.has_visuals.return_value = True
    converter = MovieConverter(file_handler, mock.MagicMock(), mock.MagicMock())
    clip = mock.MagicMock()
    clip.duration = 10
    clip.fps = 24
    clip.audio = mock.MagicMock()
    segment = mock.MagicMock()
    segment.fps = 24
    segment.audio = mock.MagicMock()
    clip.subclipped.return_value = segment

    with mock.patch("core.converter.movie_converter.VideoFileClip", return_value=clip):
        converter.to_movie(
            input="/input",
            output="/output",
            recursive=False,
            file_paths={
                Category.IMAGE: [],
                Category.MOVIE: [("/input", "clip", "mp4")],
                Category.DOCUMENT: [],
            },
            format="mp4",
            framerate=None,
            codec="libx264",
            delete=False,
            trim=(2, 5),
        )

    clip.subclipped.assert_called_once_with(2, 5)
    segment.write_videofile.assert_called_once()
    assert segment.write_videofile.call_args.args[0].endswith("clip.mp4")
    file_handler.post_process.assert_called_once()


def test_controller_trims_audio_without_explicit_format(
    controller_instance, tmp_path
):
    source = tmp_path / "tone.wav"
    output = tmp_path / "out"
    _write_wav(source)
    output.mkdir()

    _run(controller_instance, source, output, [], trim="1-3")

    result = output / "tone.wav"
    assert result.is_file()
    assert _wav_duration(result) == pytest.approx(2, abs=0.05)


def test_controller_splits_audio_at_points(controller_instance, tmp_path):
    source = tmp_path / "tone.wav"
    output = tmp_path / "out"
    _write_wav(source)
    output.mkdir()

    _run(controller_instance, source, output, ["wav"], split_at="1,2")

    parts = [output / f"tone_part_{index}.wav" for index in range(1, 4)]
    assert all(part.is_file() for part in parts)
    assert [_wav_duration(part) for part in parts] == pytest.approx(
        [1, 1, 2], abs=0.05
    )


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_controller_splits_movie_without_explicit_format(
    controller_instance, tmp_path
):
    source = tmp_path / "clip.mp4"
    output = tmp_path / "out"
    _make_test_video(source, seconds=3)
    output.mkdir()

    _run(controller_instance, source, output, [], split_at="1,2")

    parts = [output / f"clip_part_{index}.mp4" for index in range(1, 4)]
    assert all(part.is_file() for part in parts)
    assert all(0.5 <= _media_duration(part) <= 1.5 for part in parts)


def test_controller_rejects_invalid_trim(controller_instance, tmp_path):
    source = tmp_path / "tone.wav"
    _write_wav(source)

    with pytest.raises(ValueError):
        _run(controller_instance, source, tmp_path / "out", [], trim="10-5")
