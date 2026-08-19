import sys
import subprocess
import os
import pytest

from unittest import mock
from unittest.mock import MagicMock, patch

from utils.category import Category
from core.utils import resolution as res
from core.converter.movie_converter import MovieConverter
from tests.test_fixtures import controller_instance, setup_file_handler_mock


@pytest.fixture
def mock_converter():
    file_handler = MagicMock()
    prog_logger = MagicMock()
    event_logger = MagicMock()
    setup_file_handler_mock(file_handler)
    return MovieConverter(file_handler, prog_logger, event_logger, locale="English")


@pytest.fixture
def movie_category(controller_instance):
    return controller_instance._supported_formats[Category.MOVIE]


@pytest.fixture
def protocol_category(controller_instance):
    return controller_instance._supported_formats[Category.PROTOCOLS]


class TestResolutionModule:
    def test_available_resolutions_full_ladder(self, movie_category):
        available = res.available_resolutions(movie_category, "mp4")
        assert available[0] == "3840x2160"
        assert "1920x1080" in available
        assert "426x240" in available

    def test_available_resolutions_restricted_sd(self, movie_category):
        available = res.available_resolutions(movie_category, "3gp")
        assert available == ["854x480", "640x360", "426x240"]
        assert "1920x1080" not in available

    def test_available_resolutions_protocol_renditions(self, protocol_category):
        for protocol in ("hls", "dash"):
            available = res.available_resolutions(protocol_category, protocol)
            assert available == [
                "1920x1080",
                "1280x720",
                "842x480",
                "640x360",
                "426x240",
            ]

    def test_available_resolutions_unknown_format(self, movie_category):
        assert res.available_resolutions(movie_category, "mp3") == []
        assert res.available_resolutions(movie_category, "nonexistent") == []

    def test_resolution_allowed(self, movie_category):
        assert (
            res.resolution_allowed(movie_category, "mp4", "3840x2160") is True
        )
        assert res.resolution_allowed(movie_category, "mp4", "1280x720") is True
        assert res.resolution_allowed(movie_category, "3gp", "1920x1080") is False
        assert res.resolution_allowed(movie_category, "3gp", "640x360") is True

    def test_normalize_resolution(self, controller_instance):
        normalize = lambda value: res.normalize_resolution(  # noqa: E731
            controller_instance._RES_ALIASES, controller_instance._RES_ALL, value
        )
        assert normalize("1920x1080") == "1920x1080"
        assert normalize("1080p") == "1920x1080"
        assert normalize("720p") == "1280x720"
        assert normalize("480p") == "854x480"
        assert normalize("240p") == "426x240"
        assert normalize("1440p") == "2560x1440"
        assert normalize("4k") == "3840x2160"
        assert normalize(" 1080P ") == "1920x1080"

    def test_normalize_resolution_invalid(self, controller_instance):
        normalize = lambda value: res.normalize_resolution(  # noqa: E731
            controller_instance._RES_ALIASES, controller_instance._RES_ALL, value
        )
        assert normalize(None) is None
        assert normalize("") is None
        assert normalize("bogus") is None
        assert normalize("1920x666") is None

    def test_parse_resolution_canonical(self):
        assert res.parse_resolution("1920x1080") == (1920, 1080)
        assert res.parse_resolution("1280x720") == (1280, 720)

    def test_parse_resolution_rejects_non_canonical(self):
        # Canonicalization happens in the controller; parse only splits 'WxH'
        with pytest.raises(ValueError):
            res.parse_resolution("720p")
        with pytest.raises(ValueError):
            res.parse_resolution("bogus")
        with pytest.raises(ValueError):
            res.parse_resolution(None)


class TestControllerResolutionValidation:
    def _movie_file_paths(self):
        return {
            Category.AUDIO: [],
            Category.MOVIE: [("/media/", "video", "mp4")],
            Category.IMAGE: [],
            Category.DOCUMENT: [],
        }

    def test_validate_rejected_resolution_lists_available(
        self, controller_instance
    ):
        controller_instance.resolution = "1920x1080"
        with pytest.raises(ValueError) as exc:
            controller_instance._validate_resolution(
                self._movie_file_paths(), ["3gp"]
            )
        message = str(exc.value)
        assert "1920x1080" in message
        assert "3gp" in message
        assert "854x480, 640x360, 426x240" in message

    def test_validate_unknown_resolution_raises(self, controller_instance):
        controller_instance.resolution = "bogus"
        with pytest.raises(ValueError) as exc:
            controller_instance._validate_resolution(
                self._movie_file_paths(), ["mp4"]
            )
        assert "bogus" in str(exc.value)

    def test_validate_alone_without_movies(self, controller_instance):
        empty = {
            Category.AUDIO: [],
            Category.MOVIE: [],
            Category.IMAGE: [],
            Category.DOCUMENT: [],
        }
        controller_instance.resolution = "1280x720"
        with pytest.raises(ValueError) as exc:
            controller_instance._validate_resolution(empty, [])
        assert "no movie files found" in str(exc.value)

    def test_validate_codec_target(self, controller_instance):
        controller_instance.resolution = "1280x720"
        controller_instance._validate_resolution(
            self._movie_file_paths(), ["h264"]
        )
        assert controller_instance.resolution == "1280x720"

    def test_validate_protocol_target(self, controller_instance):
        controller_instance.resolution = "1920x1080"
        controller_instance._validate_resolution(
            self._movie_file_paths(), ["hls"]
        )
        assert controller_instance.resolution == "1920x1080"

    def test_validate_non_resizable_target(self, controller_instance):
        controller_instance.resolution = "1280x720"
        with pytest.raises(ValueError) as exc:
            controller_instance._validate_resolution(
                self._movie_file_paths(), ["mp3"]
            )
        assert "mp3" in str(exc.value)

    def test_run_unknown_resolution_raises_early(self, controller_instance, tmp_path):
        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get:
            mock_get.return_value = self._movie_file_paths()
            with pytest.raises(ValueError) as exc:
                controller_instance.run(
                    input_path_args=[str(tmp_path)],
                    format="mp4",
                    output=str(tmp_path),
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
                    resolution="bogus",
                )
            assert "bogus" in str(exc.value)

    def test_run_resize_with_format_passes_resolution(
        self, controller_instance, tmp_path
    ):
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get, mock.patch.object(
            controller_instance.movie_converter, "to_movie"
        ) as mock_to_movie:
            mock_get.return_value = {
                Category.AUDIO: [],
                Category.MOVIE: [("/media/", "video", "mp4")],
                Category.IMAGE: [],
                Category.DOCUMENT: [],
            }
            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format="mkv",
                output=str(tmp_path),
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
                resolution="1080p",
            )

        mock_to_movie.assert_called_once()
        _, kwargs = mock_to_movie.call_args
        assert kwargs["format"] == "mkv"
        assert kwargs["resolution"] == "1920x1080"
        assert kwargs["codec"] == "libx264"

    def test_run_resize_alone_keeps_input_format(
        self, controller_instance, tmp_path
    ):
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get, mock.patch.object(
            controller_instance.movie_converter, "to_movie"
        ) as mock_to_movie:
            mock_get.return_value = {
                Category.AUDIO: [],
                Category.MOVIE: [("/media/", "video", "mp4")],
                Category.IMAGE: [],
                Category.DOCUMENT: [],
            }
            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format=None,
                output=str(tmp_path),
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
                resolution="720p",
            )

        mock_to_movie.assert_called_once()
        _, kwargs = mock_to_movie.call_args
        assert kwargs["format"] == "mp4"
        assert kwargs["resolution"] == "1280x720"
        assert kwargs["codec"] == "libx264"

    def test_run_resize_rejected_on_incompatible_format(
        self, controller_instance, tmp_path
    ):
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get, mock.patch.object(
            controller_instance.movie_converter, "to_movie"
        ) as mock_to_movie:
            mock_get.return_value = {
                Category.AUDIO: [],
                Category.MOVIE: [("/media/", "video", "mp4")],
                Category.IMAGE: [],
                Category.DOCUMENT: [],
            }
            with pytest.raises(ValueError) as exc:
                controller_instance.run(
                    input_path_args=[str(tmp_path)],
                    format="3gp",
                    output=str(tmp_path),
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
                    resolution="1920x1080",
                )
            assert "Available resolutions for '3gp'" in str(exc.value)
        mock_to_movie.assert_not_called()

    def test_run_resize_with_codec_passes_full_codec_list(
        self, controller_instance, tmp_path
    ):
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get, mock.patch.object(
            controller_instance.movie_converter, "to_codec"
        ) as mock_to_codec:
            mock_get.return_value = {
                Category.AUDIO: [],
                Category.MOVIE: [("/media/", "video", "mp4")],
                Category.IMAGE: [],
                Category.DOCUMENT: [],
            }
            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format="h264",
                output=str(tmp_path),
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
                resolution="720p",
            )

        mock_to_codec.assert_called_once()
        _, kwargs = mock_to_codec.call_args
        assert kwargs["format"] == "h264"
        assert kwargs["resolution"] == "1280x720"
        assert kwargs["codec"] == ["libx264", "mkv"]

    def test_process_file_paths_routes_alone_resize(self, controller_instance):
        controller_instance.resolution = "1280x720"
        controller_instance.target_format = None
        controller_instance.input = "/tmp"
        controller_instance.output = "/tmp/out"
        controller_instance.recursive = False
        controller_instance.delete = False
        controller_instance.framerate = None
        controller_instance.merging = False
        controller_instance.concatenating = False

        file_paths = {
            Category.IMAGE: [],
            Category.MOVIE: [("/media/", "video", "mp4")],
            Category.DOCUMENT: [],
        }
        with mock.patch.object(
            controller_instance.movie_converter, "to_movie"
        ) as mock_to_movie:
            controller_instance.process_file_paths(file_paths)

        mock_to_movie.assert_called_once()
        _, kwargs = mock_to_movie.call_args
        assert kwargs["format"] == "mp4"
        assert kwargs["resolution"] == "1280x720"

    def test_concat_movie_branch_respects_format(self, controller_instance):
        # Regression: a non-movie target format must not trigger the movie concat
        controller_instance.output = "/tmp/out"
        controller_instance.framerate = None
        controller_instance.quality = None
        controller_instance.delete = False

        file_paths = {
            Category.AUDIO: [],
            Category.MOVIE: [("/media/", "video", "mp4")],
            Category.IMAGE: [],
            Category.DOCUMENT: [],
        }
        with patch("core.controller.concatenate_videoclips") as mock_concat, patch(
            "core.controller.VideoFileClip"
        ) as mock_vfc:
            controller_instance.concat(file_paths, format="mp3")

        mock_concat.assert_not_called()
        mock_vfc.assert_not_called()


class TestMovieConverterResolution:
    @patch("core.converter.movie_converter.VideoFileClip")
    def test_to_movie_resizes_same_format(self, mock_vfc, mock_converter):
        mock_clip = MagicMock()
        resized_clip = MagicMock()
        mock_clip.resized.return_value = resized_clip
        mock_vfc.return_value = mock_clip
        mock_converter.file_handler.has_visuals.return_value = True
        movie = ("dir", "video", "mp4")
        mock_converter.file_handler.join_back.return_value = "dir/video.mp4"

        mock_converter.to_movie(
            input="in",
            output="out",
            recursive=False,
            file_paths={
                Category.IMAGE: [],
                Category.MOVIE: [movie],
                Category.DOCUMENT: [],
            },
            format="mp4",
            framerate=None,
            codec="libx264",
            delete=False,
            resolution="1920x1080",
        )

        mock_clip.resized.assert_called_once_with(new_size=(1920, 1080))
        resized_clip.write_videofile.assert_called_once()

    @patch("core.converter.movie_converter.VideoFileClip")
    def test_to_movie_resizes_during_format_conversion(
        self, mock_vfc, mock_converter
    ):
        mock_clip = MagicMock()
        resized_clip = MagicMock()
        mock_clip.resized.return_value = resized_clip
        mock_vfc.return_value = mock_clip
        mock_converter.file_handler.has_visuals.return_value = True
        movie = ("dir", "video", "webm")
        mock_converter.file_handler.join_back.return_value = "dir/video.webm"

        mock_converter.to_movie(
            input="in",
            output="out",
            recursive=False,
            file_paths={
                Category.IMAGE: [],
                Category.MOVIE: [movie],
                Category.DOCUMENT: [],
            },
            format="mp4",
            framerate=None,
            codec="libx264",
            delete=False,
            resolution="1280x720",
        )

        mock_clip.resized.assert_called_once_with(new_size=(1280, 720))
        resized_clip.write_videofile.assert_called_once()

    def test_to_movie_same_format_skips_without_resolution(self, mock_converter):
        movie = ("dir", "video", "mp4")
        with patch(
            "core.converter.movie_converter.VideoFileClip"
        ) as mock_vfc:
            mock_converter.to_movie(
                input="in",
                output="out",
                recursive=False,
                file_paths={
                    Category.IMAGE: [],
                    Category.MOVIE: [movie],
                    Category.DOCUMENT: [],
                },
                format="mp4",
                framerate=None,
                codec="libx264",
                delete=False,
            )

        mock_vfc.assert_not_called()

    @patch("core.converter.movie_converter.VideoFileClip")
    def test_to_codec_resizes(self, mock_vfc, mock_converter):
        mock_clip = MagicMock()
        resized_clip = MagicMock()
        mock_clip.resized.return_value = resized_clip
        mock_vfc.return_value = mock_clip
        mock_converter.file_handler.has_visuals.return_value = True
        mock_converter.file_handler.join_back.return_value = "dir/video.mp4"
        movie = ("dir", "video", "mp4")

        mock_converter.to_codec(
            input="in",
            output="out",
            format="h264",
            recursive=False,
            file_paths={Category.MOVIE: [movie]},
            framerate=None,
            codec=("libx264", "mkv"),
            delete=False,
            resolution="1280x720",
        )

        mock_clip.resized.assert_called_once_with(new_size=(1280, 720))
        resized_clip.write_videofile.assert_called_once()


def test_cli_resolution_flag_recognized(tmp_path):
    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "any_to_any.py")
    )
    result = subprocess.run(
        [sys.executable, script_path, "-i", str(tmp_path), "--resolution", "720p"],
        capture_output=True,
        text=True,
    )
    combined = (result.stdout + "\n" + result.stderr).lower()
    assert "unrecognized arguments" not in combined
    assert result.returncode in (0, 1)