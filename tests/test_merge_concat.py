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
    with (
        mock.patch("core.controller.VideoFileClip", return_value=video_clip),
        mock.patch("core.controller.AudioFileClip"),
    ):
        controller_instance.merge(
            {
                Category.MOVIE: [(str(tmp_path) + "/", "clip", "mp4")],
                Category.AUDIO: [(str(tmp_path) + "/", "clip", "mp3")],
            }
        )

    written = video_clip.write_videofile.call_args[0][0]
    assert os.path.abspath(written) != os.path.abspath(str(existing))
    assert existing.read_bytes() == b"original"


def test_merge_finds_audio_with_capitalized_extension(controller_instance, tmp_path):
    # Directory search for a matching audio file must resolve
    # case-normalized extensions to their on-disk spelling (e.g. clip.MP3)
    out = tmp_path / "out"
    out.mkdir()
    controller_instance.output = str(out)
    controller_instance.delete = False
    controller_instance.framerate = 24

    audio_path = tmp_path / "clip.MP3"
    audio_path.write_bytes(b"\x00" * 128)

    video_clip = mock.MagicMock()
    video_clip.with_audio.return_value = video_clip
    with (
        mock.patch("core.controller.VideoFileClip", return_value=video_clip),
        mock.patch("core.controller.AudioFileClip") as mock_audio,
    ):
        controller_instance.merge(
            {
                Category.MOVIE: [(str(tmp_path) + "/", "clip", "mp4")],
                Category.AUDIO: [],
            }
        )

    mock_audio.assert_called_once_with(str(audio_path))


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


def test_concat_srt_renumbers_and_offsets_timestamps(controller_instance, tmp_path):
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


def test_concat_movie_none_fps_falls_back_to_default(controller_instance, tmp_path):
    """concat() must not pass fps=None to write_videofile, but fall back to"""
    controller_instance.output = str(tmp_path)
    controller_instance.delete = False
    controller_instance.framerate = None
    with (
        mock.patch("core.controller.VideoFileClip") as mock_vfc,
        mock.patch("core.controller.concatenate_videoclips") as mock_concat,
    ):
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


def test_concat_mixed_audio_and_movie_without_format(controller_instance, tmp_path):
    """With format=None, audio and movie inputs must each be concatenated
    with their own default (mp3/mp4), while audio default must not shadow the
    format check of the other categories"""
    controller_instance.output = str(tmp_path)
    controller_instance.delete = False
    controller_instance.framerate = None
    controller_instance.quality = None

    audio_clip = mock.MagicMock()
    with (
        mock.patch("core.controller.AudioFileClip"),
        mock.patch("core.controller.concatenate_audioclips", return_value=audio_clip),
        mock.patch("core.controller.VideoFileClip") as mock_vfc,
        mock.patch("core.controller.concatenate_videoclips") as mock_concat,
    ):
        mock_vfc.return_value = mock.MagicMock(fps=24)
        video_clip = mock.MagicMock(fps=24)
        mock_concat.return_value = video_clip
        controller_instance.concat(
            {
                Category.AUDIO: [("/d/", "a1", "mp3"), ("/d/", "a2", "mp3")],
                Category.MOVIE: [("/d/", "m1", "mp4"), ("/d/", "m2", "mp4")],
                Category.IMAGE: [],
                Category.DOCUMENT: [],
            }
        )

    assert audio_clip.write_audiofile.call_args[0][0].endswith("concatenated_audio.mp3")
    assert video_clip.write_videofile.call_args[0][0].endswith("concatenated_video.mp4")


def test_concat_images_without_framerate_uses_default(controller_instance, tmp_path):
    """Image concat must not pass fps=None to write_gif when no framerate
    was requested"""
    controller_instance.output = str(tmp_path)
    controller_instance.delete = False
    controller_instance.framerate = None
    with (
        mock.patch("core.controller.ImageClip"),
        mock.patch("core.controller.concatenate_videoclips") as mock_concat,
    ):
        combined = mock.MagicMock()
        mock_concat.return_value = combined
        controller_instance.concat(
            {
                Category.AUDIO: [],
                Category.MOVIE: [],
                Category.IMAGE: [("/d/", "i1", "png"), ("/d/", "i2", "png")],
                Category.DOCUMENT: [],
            }
        )

    assert combined.write_gif.call_args[1]["fps"] == 12


def _document_inputs(tmp_path):
    import pymupdf

    pdf = tmp_path / "doc.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(str(pdf))
    document.close()

    srt = tmp_path / "subs.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n", encoding="utf-8")
    return pdf, srt


def _document_file_paths(tmp_path):
    return {
        Category.AUDIO: [],
        Category.MOVIE: [],
        Category.IMAGE: [],
        Category.DOCUMENT: [
            (str(tmp_path) + os.sep, "doc", "pdf"),
            (str(tmp_path) + os.sep, "subs", "srt"),
        ],
    }


def test_concat_pdf_target_builds_only_pdf(controller_instance, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    pdf, srt = _document_inputs(tmp_path)
    controller_instance.output = str(out)
    controller_instance.delete = True
    controller_instance.framerate = None
    controller_instance.quality = None

    controller_instance.concat(_document_file_paths(tmp_path), format="pdf")

    assert (out / "concatenated.pdf").exists()
    assert not (out / "concatenated_subtitles.srt").exists()
    assert not pdf.exists()  # participating source consumed
    assert srt.exists()  # not part of a pdf concat: kept


def test_concat_srt_target_builds_only_srt(controller_instance, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    pdf, srt = _document_inputs(tmp_path)
    controller_instance.output = str(out)
    controller_instance.delete = True
    controller_instance.framerate = None
    controller_instance.quality = None

    controller_instance.concat(_document_file_paths(tmp_path), format="srt")

    assert (out / "concatenated_subtitles.srt").exists()
    assert not (out / "concatenated.pdf").exists()
    assert pdf.exists()
    assert not srt.exists()


def test_concat_document_target_without_matching_source_warns(
    controller_instance, tmp_path, caplog
):
    out = tmp_path / "out"
    out.mkdir()
    pdf, srt = _document_inputs(tmp_path)
    controller_instance.output = str(out)
    controller_instance.delete = True
    controller_instance.framerate = None
    controller_instance.quality = None

    controller_instance.concat(_document_file_paths(tmp_path), format="md")

    assert list(out.iterdir()) == []
    assert pdf.exists() and srt.exists()
    assert "nothing to concatenate" in caplog.text


def test_concat_image_format_mismatch_is_not_silently_a_gif(
    controller_instance, tmp_path, caplog
):
    out = tmp_path / "out"
    out.mkdir()
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    first.touch()
    second.touch()
    controller_instance.output = str(out)
    controller_instance.delete = True
    controller_instance.framerate = None

    with (
        mock.patch("core.controller.ImageClip") as mock_clip,
        mock.patch("core.controller.concatenate_videoclips") as mock_concat,
    ):
        controller_instance.concat(
            {
                Category.AUDIO: [],
                Category.MOVIE: [],
                Category.IMAGE: [
                    (str(tmp_path) + os.sep, "a", "png"),
                    (str(tmp_path) + os.sep, "b", "png"),
                ],
                Category.DOCUMENT: [],
            },
            format="png",
        )

    mock_clip.assert_not_called()
    mock_concat.assert_not_called()
    assert list(out.iterdir()) == []
    assert first.exists() and second.exists()
    assert "nothing to concatenate" in caplog.text


def test_concat_image_gif_target_still_builds(controller_instance, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    controller_instance.output = str(out)
    controller_instance.delete = False
    controller_instance.framerate = None
    with (
        mock.patch("core.controller.ImageClip"),
        mock.patch("core.controller.concatenate_videoclips") as mock_concat,
    ):
        combined = mock.MagicMock()
        mock_concat.return_value = combined
        controller_instance.concat(
            {
                Category.AUDIO: [],
                Category.MOVIE: [],
                Category.IMAGE: [
                    (str(tmp_path) + os.sep, "a", "png"),
                    (str(tmp_path) + os.sep, "b", "png"),
                ],
                Category.DOCUMENT: [],
            },
            format="gif",
        )

    assert combined.write_gif.call_count == 1
