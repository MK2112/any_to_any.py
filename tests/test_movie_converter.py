import os

import pytest

from utils.category import Category
from core.converter.movie_converter import MovieConverter
from unittest.mock import MagicMock, patch, call
from tests.test_fixtures import setup_file_handler_mock


@pytest.fixture
def mock_converter():
    file_handler = MagicMock()
    prog_logger = MagicMock()
    event_logger = MagicMock()
    setup_file_handler_mock(file_handler)
    return MovieConverter(file_handler, prog_logger, event_logger, locale="English")


@patch("core.converter.movie_converter.ImageClip")
@patch("core.converter.movie_converter.concatenate_videoclips")
def test_to_movie_from_jpgs(mock_concat, mock_imageclip, mock_converter):
    img_clip = MagicMock()
    mock_imageclip.return_value.with_duration.return_value = img_clip
    final_clip = MagicMock()
    mock_concat.return_value = final_clip

    jpg1 = ("dir", "img1", "jpg")
    jpg2 = ("dir", "img2", "jpg")
    mock_converter.file_handler.join_back.side_effect = ["dir/img1.jpg", "dir/img2.jpg"]

    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [jpg1, jpg2],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=True,
    )

    assert mock_imageclip.call_count == 2
    assert final_clip.write_videofile.call_count == 1
    assert final_clip.close.call_count == 1


@patch("core.converter.movie_converter.ImageClip")
@patch("core.converter.movie_converter.concatenate_videoclips")
@patch("core.converter.movie_converter.pypdf.open")
@patch("core.converter.movie_converter.Image.frombytes")
@patch("os.listdir")
@patch("os.makedirs")
@patch("shutil.rmtree")
def test_to_movie_pdf_to_video(
    mock_rmtree,
    mock_makedirs,
    mock_listdir,
    mock_frombytes,
    mock_pypdf_open,
    mock_concat,
    mock_imageclip,
    mock_converter,
):
    doc_path = ("dir", "file", "pdf")
    page = MagicMock()
    pix = MagicMock(width=100, height=100, samples=b"0" * 30000)
    page.get_pixmap.return_value = pix
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 1
    mock_doc.load_page.return_value = page
    mock_pypdf_open.return_value = mock_doc
    mock_frombytes.return_value.convert.return_value = MagicMock()
    mock_listdir.return_value = ["file-0.jpeg"]
    mock_concat.return_value = MagicMock()

    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [],
            Category.MOVIE: [],
            Category.DOCUMENT: [doc_path],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=True,
    )

    mock_pypdf_open.assert_called_once()
    mock_concat.return_value.write_videofile.assert_called_once()
    mock_rmtree.assert_called_once()


@patch("core.converter.movie_converter.ImageClip")
@patch("core.converter.movie_converter.concatenate_videoclips")
def test_to_movie_resizes_merged_images(mock_concat, mock_imageclip, mock_converter):
    mock_imageclip.return_value.with_duration.return_value = MagicMock()
    final_clip = MagicMock()
    mock_concat.return_value = final_clip
    mock_converter.file_handler.join_back.return_value = "dir/photo.png"
    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [("dir", "photo", "png")],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=False,
        resolution="640x360",
    )
    final_clip.resized.assert_called_once_with(new_size=(640, 360))
    final_clip.resized.return_value.write_videofile.assert_called_once()


@patch("core.converter.movie_converter.VideoFileClip")
def test_to_movie_resizes_gif_video(mock_vfc, mock_converter):
    clip = MagicMock()
    mock_vfc.return_value = clip
    mock_converter.file_handler.join_back.return_value = "dir/anim.gif"
    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [("dir", "anim", "gif")],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=False,
        resolution="640x360",
    )
    clip.resized.assert_called_once_with(new_size=(640, 360))
    clip.resized.return_value.write_videofile.assert_called_once()


@patch("core.converter.movie_converter.ImageClip")
@patch("core.converter.movie_converter.concatenate_videoclips")
@patch("core.converter.movie_converter.pypdf.open")
@patch("core.converter.movie_converter.Image.frombytes")
@patch("os.listdir")
@patch("os.makedirs")
@patch("shutil.rmtree")
def test_to_movie_resizes_pdf_frames(
    mock_rmtree,
    mock_makedirs,
    mock_listdir,
    mock_frombytes,
    mock_pypdf_open,
    mock_concat,
    mock_imageclip,
    mock_converter,
):
    page = MagicMock()
    pix = MagicMock(width=100, height=100, samples=b"0" * 30000)
    page.get_pixmap.return_value = pix
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 1
    mock_doc.load_page.return_value = page
    mock_pypdf_open.return_value = mock_doc
    mock_frombytes.return_value.convert.return_value = MagicMock()
    mock_listdir.return_value = ["file-0.jpeg"]
    mock_concat.return_value = MagicMock()
    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [],
            Category.MOVIE: [],
            Category.DOCUMENT: [("dir", "file", "pdf")],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=True,
        resolution="640x360",
    )
    mock_concat.return_value.resized.assert_called_once_with(new_size=(640, 360))


@patch("core.converter.movie_converter.office_to_frames")
def test_to_movie_docx_forwards_resolution(mock_office, mock_converter, tmp_path):
    (tmp_path / "doc-0.jpeg").write_bytes(b"frame")
    mock_office.return_value = str(tmp_path)
    mock_converter._frames_to_movie = MagicMock()
    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [],
            Category.MOVIE: [],
            Category.DOCUMENT: [("dir", "doc", "docx")],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=False,
        resolution="640x360",
    )
    assert mock_converter._frames_to_movie.call_args.args[-1] == "640x360"


@patch("core.converter.movie_converter.VideoFileClip")
def test_to_codec_fallback_on_error(mock_vfc, mock_converter):
    mock_clip = MagicMock()
    mock_clip.write_videofile.side_effect = [Exception("fail"), None]
    mock_vfc.return_value = mock_clip
    movie = ("dir", "video", "mp4")
    mock_converter.file_handler.join_back.return_value = "dir/video.mp4"

    mock_converter.to_codec(
        input="in",
        output="out",
        format="mp4",
        recursive=False,
        file_paths={Category.MOVIE: [movie]},
        framerate=24,
        codec=("libx264", "x264"),
        delete=False,
    )

    assert mock_clip.write_videofile.call_count == 2


@patch("core.converter.movie_converter.subprocess.run")
def test_to_protocol_hls(mock_run, mock_converter):
    movie = ("dir", "sample", "mp4")
    mock_converter.file_handler.join_back.return_value = "dir/sample.mp4"

    mock_run.return_value = MagicMock(stdout="ok", stderr="")

    mock_converter.to_protocol(
        output="out",
        file_paths={Category.MOVIE: [movie]},
        supported_formats={Category.PROTOCOLS: {"hls": True}},
        protocol=["hls"],
        delete=True,
    )

    assert mock_run.called
    mock_converter.file_handler.post_process.assert_called()


@patch("core.converter.movie_converter.subprocess.run")
def test_to_protocol_hls_master_playlist(mock_run, mock_converter, tmp_path):
    # master.m3u8 must reference each real rendition playlist, BANDWIDTH must include audio, ffmpeg must not block overwriting
    movie = ("dir", "sample", "mp4")
    mock_converter.file_handler.join_back.return_value = "dir/sample.mp4"
    mock_run.return_value = MagicMock(stdout="ok", stderr="")

    mock_converter.to_protocol(
        output=str(tmp_path),
        file_paths={Category.MOVIE: [movie]},
        supported_formats={Category.PROTOCOLS: {"hls": True}},
        protocol=["hls"],
        delete=False,
    )

    master = tmp_path / "sample_hls" / "master.m3u8"
    assert master.exists()
    content = master.read_text()
    assert "426x240/426x240.m3u8" in content
    assert "1920x1080/1920x1080.m3u8" in content
    # 426x240 rung: 400k video + 64k audio = 464000 b/s
    assert "#EXT-X-STREAM-INF:BANDWIDTH=464000,RESOLUTION=426x240" in content
    cmd = mock_run.call_args[0][0]
    assert "-y" in cmd
    assert "0:a?" in cmd


@patch("core.converter.movie_converter.subprocess.run")
def test_to_protocol_hls_resolution_single_rendition(
    mock_run, mock_converter, tmp_path
):
    # --resolution narrows the HLS ladder to the matching rung only
    movie = ("dir", "sample", "mp4")
    mock_converter.file_handler.join_back.return_value = "dir/sample.mp4"
    mock_run.return_value = MagicMock(stdout="ok", stderr="")

    mock_converter.to_protocol(
        output=str(tmp_path),
        file_paths={Category.MOVIE: [movie]},
        supported_formats={Category.PROTOCOLS: {"hls": True}},
        protocol=["hls"],
        resolution="1280x720",
        delete=False,
    )

    master = tmp_path / "sample_hls" / "master.m3u8"
    assert master.exists()
    content = master.read_text()
    assert "1280x720/1280x720.m3u8" in content
    assert "426x240" not in content
    assert "1920x1080" not in content


@patch("core.converter.movie_converter.subprocess.run")
def test_to_protocol_hls_out_dirs_use_basename_not_extension(
    mock_run, mock_converter, tmp_path
):
    # Ensure output dir is named using basename of input file, without extension
    mock_run.return_value = MagicMock(stdout="ok", stderr="")
    mock_converter.file_handler.join_back.side_effect = (
        lambda ps: f"{ps[0]}/{ps[1]}.{ps[2]}"
    )

    mock_converter.to_protocol(
        output=str(tmp_path),
        file_paths={
            Category.MOVIE: [("d1", "clip_a", "mp4"), ("d2", "clip_b", "mp4")]
        },
        supported_formats={Category.PROTOCOLS: {"hls": True}},
        protocol=["hls"],
        delete=False,
    )

    assert (tmp_path / "clip_a_hls" / "master.m3u8").exists()
    assert (tmp_path / "clip_b_hls" / "master.m3u8").exists()
    assert not (tmp_path / "mp4_hls").exists()


@patch("core.converter.movie_converter.subprocess.run")
def test_to_protocol_hls_unknown_resolution_fails_loudly(
    mock_run, mock_converter, tmp_path
):
    # If a resolution is specified whily not matching any rung in HLS ladder, raise ValueError + output no files
    movie = ("dir", "sample", "mp4")
    mock_converter.file_handler.join_back.return_value = "dir/sample.mp4"
    mock_run.return_value = MagicMock(stdout="ok", stderr="")

    with pytest.raises(ValueError, match="2560x1440"):
        mock_converter.to_protocol(
            output=str(tmp_path),
            file_paths={Category.MOVIE: [movie]},
            supported_formats={Category.PROTOCOLS: {"hls": True}},
            protocol=["hls"],
            resolution="2560x1440",
            delete=False,
        )

    mock_run.assert_not_called()
    assert not (tmp_path / "sample_hls" / "master.m3u8").exists()


@patch("core.converter.movie_converter.subprocess.run", side_effect=Exception("fail"))
def test_to_protocol_dash_fails(mock_run, mock_converter):
    movie = ("dir", "video", "mp4")
    mock_converter.file_handler.join_back.return_value = "dir/video.mp4"

    with patch("core.converter.movie_converter.end_with_msg") as mock_end:
        mock_converter.to_protocol(
            output="out",
            file_paths={Category.MOVIE: [movie]},
            supported_formats={Category.PROTOCOLS: {"dash": True}},
            protocol=["dash"],
            delete=False,
        )
        mock_end.assert_called()


def test_to_movie_no_images_no_movies(mock_converter):
    # No exceptions when no inputs provided, graceful handling instead
    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={Category.IMAGE: [], Category.MOVIE: [], Category.DOCUMENT: []},
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=False,
    )


@patch("core.converter.movie_converter.VideoFileClip")
@patch("core.converter.movie_converter.ImageClip")
@patch("core.converter.movie_converter.concatenate_videoclips")
def test_to_movie_gif_excluded_from_merged_video(
    mock_concat, mock_imageclip, mock_vfc, mock_converter
):
    img_clip = MagicMock()
    mock_imageclip.return_value.with_duration.return_value = img_clip
    final_clip = MagicMock()
    mock_concat.return_value = final_clip

    mock_converter.file_handler.join_back.side_effect = [
        "dir/photo.jpg",
        "dir/animation.gif",
    ]

    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [
                ("dir", "photo", "jpg"),
                ("dir", "animation", "gif"),
            ],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=False,
    )

    # Only the jpg (non-gif) should be passed to concatenate_videoclips
    concat_args = mock_concat.call_args[0][0]
    assert len(concat_args) == 1, "GIF should be excluded from merged clip"


@patch("core.converter.movie_converter.VideoFileClip")
def test_to_movie_gifs_single_cpu_does_not_crash(
    mock_vfc, mock_converter, monkeypatch
):
    monkeypatch.setattr(os, "cpu_count", lambda: 1)
    monkeypatch.delenv("Any2Any_MAX_WORKERS", raising=False)
    mock_clip = MagicMock()
    mock_vfc.return_value = mock_clip
    mock_converter.file_handler.join_back.side_effect = ["dir/a.gif", "dir/b.gif"]

    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [("dir", "a", "gif"), ("dir", "b", "gif")],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=False,
    )

    assert mock_clip.write_videofile.call_count == 2


@patch("core.converter.movie_converter.VideoFileClip")
def test_to_movie_only_gifs_skips_merge(mock_vfc, mock_converter):
    mock_clip = MagicMock()
    mock_vfc.return_value = mock_clip
    mock_converter.file_handler.join_back.return_value = "dir/anim.gif"

    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [("dir", "anim", "gif")],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=False,
    )

    # GIF should be individually converted, no merged video created
    mock_vfc.assert_called_once()
    mock_clip.write_videofile.assert_called_once()


@patch("core.converter.movie_converter.VideoFileClip")
def test_to_movie_gif_plus_png_and_jpg(mock_vfc, mock_converter):
    img_clip = MagicMock()
    mock_converter.file_handler.join_back.side_effect = [
        "dir/img1.png",
        "dir/img2.jpg",
        "dir/anim.gif",
    ]
    mock_clip = MagicMock()
    mock_vfc.return_value = mock_clip

    with patch("core.converter.movie_converter.ImageClip") as mock_ic:
        with patch(
            "core.converter.movie_converter.concatenate_videoclips"
        ) as mock_concat:
            mock_ic.return_value.with_duration.return_value = img_clip
            final_clip = MagicMock()
            mock_concat.return_value = final_clip

            mock_converter.to_movie(
                input="in",
                output="out",
                recursive=False,
                file_paths={
                    Category.IMAGE: [
                        ("dir", "img1", "png"),
                        ("dir", "img2", "jpg"),
                        ("dir", "anim", "gif"),
                    ],
                    Category.MOVIE: [],
                    Category.DOCUMENT: [],
                },
                format="mp4",
                framerate=24,
                codec="libx264",
                delete=False,
            )

            # Only png and jpg should be in the merged clip, not the gif
            concat_args = mock_concat.call_args[0][0]
            assert len(concat_args) == 2
            # GIF individual conversion still happens
            mock_vfc.assert_called_once()


@patch("core.converter.movie_converter.office_to_frames")
@patch("core.converter.movie_converter.ImageClip")
@patch("core.converter.movie_converter.concatenate_videoclips")
@patch("core.converter.movie_converter.shutil.rmtree")
@patch("core.converter.movie_converter.os.makedirs")
def test_to_movie_docx_frames_become_clips_case_insensitive(
    mock_makedirs, mock_rmtree, mock_concat, mock_imageclip, mock_office,
    mock_converter,
):
    mock_office.return_value = "/out/doc"
    final_clip = MagicMock()
    mock_concat.return_value = final_clip

    with patch("core.converter.movie_converter.os.listdir") as mock_listdir:
        mock_listdir.return_value = [
            "doc-10.jpeg",
            "doc-2.jpeg",
            "doc-1.JPEG",
            "notes.txt",
        ]
        mock_converter.to_movie(
            input="in",
            output="out",
            recursive=False,
            file_paths={
                Category.IMAGE: [],
                Category.MOVIE: [],
                Category.DOCUMENT: [("dir", "doc", "docx")],
            },
            format="mp4",
            framerate=24,
            codec="libx264",
            delete=True,
        )

    # .JPEG is matched case-insensitively and each frame is loaded as a clip
    assert mock_imageclip.call_count == 3
    loaded_paths = [c.args[0] for c in mock_imageclip.call_args_list]
    assert loaded_paths == [
        "/out/doc/doc-1.JPEG",
        "/out/doc/doc-2.jpeg",
        "/out/doc/doc-10.jpeg",
    ]
    concat_args = mock_concat.call_args[0][0]
    assert len(concat_args) == 3
    assert all(not isinstance(c, str) for c in concat_args)
    final_clip.write_videofile.assert_called_once()
    final_clip.close.assert_called_once()


@patch("core.converter.movie_converter.VideoFileClip")
def test_to_movie_gif_none_fps_falls_back_to_default(
    mock_vfc, mock_converter
):
    mock_clip = MagicMock(fps=None)
    mock_vfc.return_value = mock_clip
    mock_converter.file_handler.join_back.return_value = "dir/anim.gif"

    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [("dir", "anim", "gif")],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=None,
        codec="libx264",
        delete=False,
    )

    written_fps = mock_clip.write_videofile.call_args[1]["fps"]
    assert written_fps == 24


@patch("core.converter.movie_converter.ImageClip")
@patch("core.converter.movie_converter.AudioFileClip")
def test_to_movie_audio_only_placeholder_is_720p(
    mock_audio, mock_imageclip, mock_converter
):
    # Audio-only inputs render over a black placeholder frame
    mock_converter.file_handler.has_visuals.return_value = False
    mock_converter.file_handler.join_back.return_value = "dir/song.mp3"
    mock_audio.return_value.duration = 5.0
    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [],
            Category.MOVIE: [("dir", "song", "mp3")],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=False,
    )

    assert mock_imageclip.call_args[0][0].shape == (720, 1280, 3)


@patch("core.converter.movie_converter.ImageClip")
@patch("core.converter.movie_converter.AudioFileClip")
def test_to_codec_audio_only_placeholder_is_720p(
    mock_audio, mock_imageclip, mock_converter
):
    mock_converter.file_handler.has_visuals.return_value = False
    mock_converter.file_handler.join_back.return_value = "dir/song.mp4"
    mock_audio.return_value.duration = 5.0
    mock_converter.to_codec(
        input="in",
        output="out",
        format="h264",
        recursive=False,
        file_paths={Category.MOVIE: [("dir", "song", "mp4")]},
        framerate=24,
        codec=("libx264", "mkv"),
        delete=False,
    )

    assert mock_imageclip.call_args[0][0].shape == (720, 1280, 3)


@patch("core.converter.movie_converter.subprocess.run")
def test_to_protocol_hls_uses_libx264_and_scale_filter(
    mock_run, mock_converter, tmp_path
):
    # The HLS ladder must use the real libx264 encoder
    mock_converter.file_handler.join_back.return_value = "dir/sample.mp4"
    mock_run.return_value = MagicMock(stdout="ok", stderr="")

    mock_converter.to_protocol(
        output=str(tmp_path),
        file_paths={Category.MOVIE: [("dir", "sample", "mp4")]},
        supported_formats={Category.PROTOCOLS: {"hls": True}},
        protocol=["hls"],
        delete=False,
    )

    cmd = mock_run.call_args[0][0]
    assert "libx264" in cmd
    assert "-vf" in cmd
    assert "scale=640:360" in cmd
    assert "-s" not in cmd


@patch("core.converter.movie_converter.subprocess.run")
def test_run_command_applies_timeout(mock_run, mock_converter):
    mock_run.return_value = MagicMock(stdout="", stderr="")
    mock_converter._run_command(["ffmpeg", "-version"])
    assert mock_run.call_args[1]["timeout"] == 3600


@patch("core.converter.movie_converter.subprocess.run")
def test_run_command_timeout_surfaces_as_runtime_error(mock_run, mock_converter):
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(["ffmpeg"], 3600)
    with pytest.raises(RuntimeError, match="[Tt]imed out"):
        mock_converter._run_command(["ffmpeg"])


@patch("core.converter.movie_converter.ImageClip")
@patch("core.converter.movie_converter.concatenate_videoclips")
def test_to_movie_includes_all_supported_image_formats(
    mock_concat, mock_imageclip, mock_converter
):
    img_clip = MagicMock()
    mock_imageclip.return_value.with_duration.return_value = img_clip
    final_clip = MagicMock()
    mock_concat.return_value = final_clip

    pics = [
        ("dir", "a", "tiff"),
        ("dir", "b", "tga"),
        ("dir", "c", "heic"),
        ("dir", "d", "ppm"),
        ("dir", "e", "ico"),
    ]
    mock_converter.file_handler.join_back.side_effect = (
        lambda s: f"{s[0]}/{s[1]}.{s[2]}"
    )

    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: pics,
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=True,
    )

    assert mock_imageclip.call_count == len(pics)
    concat_args = mock_concat.call_args[0][0]
    assert len(concat_args) == len(pics)
    processed = [
        c.args[0]
        for c in mock_converter.file_handler.post_process.call_args_list
    ]
    assert processed == pics


@patch("core.converter.movie_converter.ImageClip")
@patch("core.converter.movie_converter.concatenate_videoclips")
def test_to_movie_unreadable_image_is_skipped(
    mock_concat, mock_imageclip, mock_converter
):
    # A file that cannot be opened as an image must not abort the merge,
    # and must not be deleted or reported as converted
    img_clip = MagicMock()
    good_clip = MagicMock()
    good_clip.with_duration.return_value = img_clip
    final_clip = MagicMock()
    mock_concat.return_value = final_clip

    def make_clip(path):
        if path.endswith(".tiff"):
            raise OSError("cannot identify image file")
        return good_clip

    mock_imageclip.side_effect = make_clip
    mock_converter.file_handler.join_back.side_effect = (
        lambda s: f"{s[0]}/{s[1]}.{s[2]}"
    )

    damaged = ("dir", "damaged", "tiff")
    fine = ("dir", "fine", "png")
    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [damaged, fine],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=24,
        codec="libx264",
        delete=True,
    )

    concat_args = mock_concat.call_args[0][0]
    assert len(concat_args) == 1
    processed = [
        c.args[0]
        for c in mock_converter.file_handler.post_process.call_args_list
    ]
    assert processed == [fine]
    mock_converter.event_logger.error.assert_called()


def test_to_movie_merges_png_and_tiff_end_to_end(tmp_path):
    import logging
    from PIL import Image
    from core.utils.file_handler import FileHandler
    from utils.prog_logger import ProgLogger

    logger = logging.getLogger("m6-e2e")
    file_handler = FileHandler(logger, "English")
    converter = MovieConverter(file_handler, ProgLogger(), logger, "English")

    pics = []
    for name, ext in (("a", "png"), ("b", "tiff")):
        Image.new("RGB", (32, 32), "red").save(tmp_path / f"{name}.{ext}")
        pics.append((str(tmp_path) + os.sep, name, ext))

    out = tmp_path / "out"
    out.mkdir()

    converter.to_movie(
        input=str(tmp_path),
        output=str(out),
        recursive=False,
        file_paths={
            Category.IMAGE: pics,
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=2,
        codec="libx264",
        delete=True,
    )

    merged = out / "merged.mp4"
    assert merged.exists()

    from moviepy import VideoFileClip

    with VideoFileClip(str(merged)) as clip:
        frame_total = sum(1 for _ in clip.iter_frames())
    assert frame_total == 2

    assert not (tmp_path / "a.png").exists()
    assert not (tmp_path / "b.tiff").exists()


def test_to_movie_image_resolution_end_to_end(tmp_path):
    import logging
    from PIL import Image
    from core.utils.file_handler import FileHandler
    from utils.prog_logger import ProgLogger

    logger = logging.getLogger("res-e2e")
    file_handler = FileHandler(logger, "English")
    converter = MovieConverter(file_handler, ProgLogger(), logger, "English")

    Image.new("RGB", (320, 240), "red").save(tmp_path / "photo.png")
    pics = [(str(tmp_path) + os.sep, "photo", "png")]

    out = tmp_path / "out"
    out.mkdir()

    converter.to_movie(
        input=str(tmp_path),
        output=str(out),
        recursive=False,
        file_paths={
            Category.IMAGE: pics,
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=2,
        codec="libx264",
        delete=False,
        resolution="160x120",
    )

    merged = out / "merged.mp4"
    assert merged.exists()

    from moviepy import VideoFileClip

    with VideoFileClip(str(merged)) as clip:
        assert tuple(clip.size) == (160, 120)


def test_docx_to_movie_failure_preserves_source(tmp_path):
    import logging
    import docx as docx_lib
    from PIL import Image
    from core.utils.file_handler import FileHandler
    from utils.prog_logger import ProgLogger

    Image.new("RGB", (32, 32), "red").save(tmp_path / "pic.png")
    document = docx_lib.Document()
    document.add_picture(str(tmp_path / "pic.png"))
    document.save(tmp_path / "doc.docx")

    out = tmp_path / "out"
    out.mkdir()

    logger = logging.getLogger("docx-movie-fail")
    file_handler = FileHandler(logger, "English")
    converter = MovieConverter(file_handler, ProgLogger(), logger, "English")
    converter._frames_to_movie = MagicMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        converter.to_movie(
            input=str(tmp_path) + os.sep,
            output=str(out),
            recursive=False,
            file_paths={
                Category.IMAGE: [],
                Category.MOVIE: [],
                Category.DOCUMENT: [(str(tmp_path) + os.sep, "doc", "docx")],
            },
            format="mp4",
            framerate=2,
            codec="libx264",
            delete=True,
        )

    assert (tmp_path / "doc.docx").exists()
    assert not list(out.glob("*.mp4"))
    assert not (out / "doc").exists()
