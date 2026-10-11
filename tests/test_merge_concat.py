import os

import pytest
import utils.language_support as lang
from unittest import mock
from utils.category import Category
from tests.test_fixtures import (
    controller_instance,
    test_input_folder,
    test_output_folder,
)


def test_merging_method(controller_instance, test_input_folder, test_output_folder):
    movie_path = test_input_folder / "movie_name.mp4"
    audio_path = test_input_folder / "movie_name.mp3"
    movie_path.touch()
    audio_path.touch()
    with pytest.raises(OSError):
        controller_instance.merge(
            {
                Category.MOVIE: [((str(movie_path.parent) + "/"), "movie_name", "mp4")],
                Category.AUDIO: [((str(audio_path.parent) + "/"), "movie_name", "mp3")],
            }
        )


def test_concatenating_method(
    controller_instance, test_input_folder, test_output_folder
):
    movie1_path = test_input_folder / "movie1.mp4"
    movie2_path = test_input_folder / "movie2.mp4"
    movie1_path.touch()
    movie2_path.touch()
    with pytest.raises(OSError):
        controller_instance.concat(
            {
                Category.AUDIO: [],
                Category.MOVIE: [
                    ((str(movie1_path.parent) + "/"), "movie1", "mp4"),
                    ((str(movie2_path.parent) + "/"), "movie2", "mp4"),
                ],
            },
            format="mp4",
        )


def test_concat_default_format(
    controller_instance, test_input_folder, test_output_folder
):
    """concat() should accept format=None (default) without crashing."""
    movie1 = test_input_folder / "m1.mp4"
    movie2 = test_input_folder / "m2.mp4"
    movie1.touch()
    movie2.touch()
    controller_instance.output = str(test_output_folder)
    with pytest.raises(OSError):
        controller_instance.concat(
            {
                Category.AUDIO: [],
                Category.MOVIE: [
                    ((str(movie1.parent) + "/"), "m1", "mp4"),
                    ((str(movie2.parent) + "/"), "m2", "mp4"),
                ],
                Category.IMAGE: [],
                Category.DOCUMENT: [],
            }
        )


def test_process_file_paths_calls_concat_when_concatenating(controller_instance):
    """process_file_paths should dispatch to concat when self.concatenating is True,
    even when self.target_format is not set (no --format given)."""
    controller_instance.output = "/tmp"
    controller_instance.merging = False
    controller_instance.concatenating = True
    controller_instance.concat = mock.MagicMock()
    file_paths = {
        Category.AUDIO: [("/tmp/", "test", "mp3")],
        Category.MOVIE: [],
        Category.IMAGE: [],
        Category.DOCUMENT: [],
    }
    controller_instance.process_file_paths(file_paths)
    controller_instance.concat.assert_called_once_with(file_paths, None)


def test_process_file_paths_calls_merge_when_merging(controller_instance):
    """process_file_paths should dispatch to merge when self.merging is True,
    even when self.target_format is not set."""
    controller_instance.output = "/tmp"
    controller_instance.merging = True
    controller_instance.merge = mock.MagicMock()
    file_paths = {
        Category.AUDIO: [("/tmp/", "test", "mp3")],
        Category.MOVIE: [("/tmp/", "test", "mp4")],
        Category.IMAGE: [],
        Category.DOCUMENT: [],
    }
    controller_instance.process_file_paths(file_paths)
    controller_instance.merge.assert_called_once_with(file_paths, False)


def test_concat_ignores_non_pdf_docs(controller_instance, tmp_path):
    """concat should skip non-PDF Document entries when building the pdf list
    and not crash on None entries."""
    out = tmp_path / "out"
    out.mkdir()
    controller_instance.output = str(out)
    controller_instance.delete = False
    controller_instance.framerate = None
    controller_instance.quality = None

    srt1 = tmp_path / "sub1.srt"
    srt1.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n")

    controller_instance.concat(
        {
            Category.AUDIO: [],
            Category.MOVIE: [],
            Category.IMAGE: [],
            Category.DOCUMENT: [
                ((str(srt1.parent) + "/"), "sub1", "srt"),
            ],
        }
    )

    assert (out / "concatenated_subtitles.srt").exists()


def test_concat_mismatched_format_no_false_success(
    controller_instance, tmp_path, caplog
):
    """concat() with a format matching no present category must not log
    concat_success (previously it reported success having done nothing)"""
    out = tmp_path / "out"
    out.mkdir()
    controller_instance.output = str(out)
    controller_instance.delete = False

    controller_instance.concat(
        {
            Category.AUDIO: [],
            Category.MOVIE: [(str(tmp_path) + "/", "video", "mp4")],
            Category.IMAGE: [],
            Category.DOCUMENT: [],
        },
        format="mp3",
    )

    assert list(out.iterdir()) == []
    success = lang.get_translation("concat_success", controller_instance.locale)
    assert success not in caplog.text
    assert "nothing to concatenate" in caplog.text


def test_merge_does_not_overwrite_existing_output(controller_instance, tmp_path):
    """merge() must conflict-resolve its output instead of silently
    overwriting a previous merge of the same inputs"""
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "clip_merged.mp4"
    existing.write_bytes(b"original")
    controller_instance.output = str(out)
    controller_instance.delete = False
    controller_instance.framerate = 24

    video_clip = mock.MagicMock()
    video_clip.with_audio.return_value = video_clip
    with mock.patch(
        "core.controller.VideoFileClip", return_value=video_clip
    ), mock.patch("core.controller.AudioFileClip"):
        controller_instance.merge(
            {
                Category.MOVIE: [(str(tmp_path) + "/", "clip", "mp4")],
                Category.AUDIO: [(str(tmp_path) + "/", "clip", "mp3")],
            }
        )

    written = video_clip.write_videofile.call_args[0][0]
    assert os.path.abspath(written) != os.path.abspath(str(existing))
    assert existing.read_bytes() == b"original"


def _srt_paths(tmp_path):
    srt1 = tmp_path / "sub1.srt"
    srt1.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nWorld\n\n"
    )
    srt2 = tmp_path / "sub2.srt"
    srt2.write_text(
        "1\n00:00:01,500 --> 00:00:02,500\nFoo\n\n"
        "2\n00:00:03,500 --> 00:00:05,000\nBar\n\n"
    )
    return [
        ((str(tmp_path) + "/"), "sub1", "srt"),
        ((str(tmp_path) + "/"), "sub2", "srt"),
    ]


def _concat_srts(controller_instance, tmp_path):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    controller_instance.output = str(out)
    controller_instance.delete = False
    controller_instance.concat(
        {
            Category.AUDIO: [],
            Category.MOVIE: [],
            Category.IMAGE: [],
            Category.DOCUMENT: _srt_paths(tmp_path),
        }
    )
    return out / "concatenated_subtitles.srt"


def test_concat_srt_renumbers_and_offsets_timestamps(
    controller_instance, tmp_path
):
    """SRT concat must renumber entries sequentially and shift each file
    past the previous file's end (sub2 starts at 00:00:04,000)."""
    merged = _concat_srts(controller_instance, tmp_path)

    assert merged.read_text() == (
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nWorld\n\n"
        "3\n00:00:05,500 --> 00:00:06,500\nFoo\n\n"
        "4\n00:00:07,500 --> 00:00:09,000\nBar\n"
    )


def test_concat_srt_rerun_overwrites_instead_of_appending(
    controller_instance, tmp_path
):
    """Re-running concat must rewrite the output, not append to it."""
    first = _concat_srts(controller_instance, tmp_path).read_text()
    second = _concat_srts(controller_instance, tmp_path).read_text()

    assert first == second
    assert second.count("-->") == 4


def test_concat_movie_none_fps_falls_back_to_default(
    controller_instance, tmp_path
):
    """concat() must not pass fps=None to write_videofile, but fall back to"""
    controller_instance.output = str(tmp_path)
    controller_instance.delete = False
    controller_instance.framerate = None
    with mock.patch(
        "core.controller.VideoFileClip"
    ) as mock_vfc, mock.patch(
        "core.controller.concatenate_videoclips"
    ) as mock_concat:
        mock_vfc.return_value = mock.MagicMock(fps=24)
        composite = mock.MagicMock(fps=None)
        mock_concat.return_value = composite
        controller_instance.concat(
            {
                Category.AUDIO: [],
                Category.MOVIE: [("/d/", "m1", "mp4"), ("/d/", "m2", "mp4")],
                Category.IMAGE: [],
                Category.DOCUMENT: [],
            },
            format="mp4",
        )
    written_fps = composite.write_videofile.call_args[1]["fps"]
    assert written_fps == 24
