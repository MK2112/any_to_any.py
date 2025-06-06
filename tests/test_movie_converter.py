import pytest
from unittest.mock import MagicMock, patch, call
from core.movie_converter import MovieConverter
from utils.category import Category


@pytest.fixture
def mock_converter():
    file_handler = MagicMock()
    prog_logger = MagicMock()
    event_logger = MagicMock()
    return MovieConverter(file_handler, prog_logger, event_logger, locale="English")


@patch("core.movie_converter.VideoFileClip")
def test_to_movie_converts_gif(mock_vfc, mock_converter):
    gif_clip = MagicMock()
    mock_vfc.return_value = gif_clip

    gif_set = ("dir", "clip", "gif")
    mock_converter.file_handler.join_back.return_value = "dir/clip.gif"

    mock_converter.to_movie(
        input="in",
        output="out",
        recursive=False,
        file_paths={
            Category.IMAGE: [gif_set],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
        },
        format="mp4",
        framerate=None,
        codec="libx264",
        delete=False,
    )

    mock_vfc.assert_called_once_with("dir/clip.gif", audio=False)
    gif_clip.write_videofile.assert_called_once()
    gif_clip.close.assert_called_once()


@patch("core.movie_converter.ImageClip")
@patch("core.movie_converter.concatenate_videoclips")
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
    assert final_clip.write_videofile.call_count == 3
    assert final_clip.close.call_count == 3


@patch("core.movie_converter.ImageClip")
@patch("core.movie_converter.concatenate_videoclips")
@patch("core.movie_converter.fitz.open")
@patch("core.movie_converter.Image.frombytes")
@patch("os.listdir")
@patch("os.makedirs")
@patch("shutil.rmtree")
def test_to_movie_pdf_to_video(
    mock_rmtree,
    mock_makedirs,
    mock_listdir,
    mock_frombytes,
    mock_fitz_open,
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
    mock_fitz_open.return_value = mock_doc
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

    mock_fitz_open.assert_called_once()
    mock_concat.return_value.write_videofile.assert_called_once()
    mock_rmtree.assert_called_once()


@patch("core.movie_converter.VideoFileClip")
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


@patch("core.movie_converter.subprocess.run")
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


@patch("core.movie_converter.subprocess.run", side_effect=Exception("fail"))
def test_to_protocol_dash_fails(mock_run, mock_converter):
    movie = ("dir", "video", "mp4")
    mock_converter.file_handler.join_back.return_value = "dir/video.mp4"

    with patch("core.movie_converter.end_with_msg") as mock_end:
        mock_converter.to_protocol(
            output="out",
            file_paths={Category.MOVIE: [movie]},
            supported_formats={Category.PROTOCOLS: {"dash": True}},
            protocol=["dash"],
            delete=False,
        )
        mock_end.assert_called()
