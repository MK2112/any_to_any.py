import pytest
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
