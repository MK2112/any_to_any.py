import os
import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.category import Category
from core.converter.image_converter import ImageConverter, office_to_frames


class TestOfficeToFrames:
    # Test the standalone office_to_frames function

    @pytest.fixture
    def mock_dependencies(self):
        file_handler = Mock()
        event_logger = Mock()
        file_handler.join_back.return_value = "/path/to/file.docx"
        file_handler.post_process = Mock()
        return file_handler, event_logger

    # Note: docx is mocked using new_callable=MagicMock, so no need to import it
    @patch("core.converter.image_converter.tqdm")
    @patch("core.converter.image_converter.os")
    @patch("core.converter.image_converter.docx", new_callable=MagicMock)
    def test_office_to_frames_docx_success(
        self, mock_docx, mock_os, mock_tqdm, mock_dependencies
    ):
        # Test successful DOCX image extraction
        file_handler, event_logger = mock_dependencies

        # Setup mocks
        mock_doc = MagicMock()
        mock_rel1 = MagicMock()
        mock_rel1.reltype = "http://image"
        mock_rel1.target_part.blob = b"fake_image_data"
        mock_rel2 = MagicMock()
        mock_rel2.reltype = "http://other"

        mock_doc.part.rels.values.return_value = [mock_rel1, mock_rel2]
        mock_docx.Document.return_value = mock_doc
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.makedirs = Mock()
        mock_tqdm.return_value = [(0, mock_rel1), (1, mock_rel2)]

        doc_path_set = ("base", "filename_docx", "docx")

        with patch("builtins.open", mock_open()) as mock_file:
            office_to_frames(
                doc_path_set, "png", "/output", False, file_handler, event_logger
            )

        # Assertions
        mock_docx.Document.assert_called_once_with("/path/to/file.docx")
        mock_os.makedirs.assert_called_once_with("/output/filename_docx", exist_ok=True)
        mock_file.assert_called_once()
        file_handler.post_process.assert_called_once()
        event_logger.error.assert_not_called()

    @patch("core.converter.image_converter.tqdm")
    @patch("core.converter.image_converter.os")
    @patch("core.converter.image_converter.pptx")
    def test_office_to_frames_pptx_success(
        self, mock_pptx, mock_os, mock_tqdm, mock_dependencies
    ):
        # Test successful PPTX image extraction
        file_handler, event_logger = mock_dependencies

        # Setup mocks
        mock_presentation = Mock()
        mock_slide = Mock()
        mock_shape = Mock()
        mock_shape.shape_type = 13  # Picture type
        mock_shape.image.blob = b"fake_image_data"
        mock_slide.shapes = [mock_shape]
        mock_presentation.slides = [mock_slide]

        mock_pptx.Presentation.return_value = mock_presentation
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.makedirs = Mock()
        mock_tqdm.return_value = [(0, mock_slide)]

        doc_path_set = ("base", "filename_pptx", "pptx")

        with patch("builtins.open", mock_open()) as mock_file:
            office_to_frames(
                doc_path_set, "png", "/output", False, file_handler, event_logger
            )

        # Assertions
        mock_pptx.Presentation.assert_called_once_with("/path/to/file.docx")
        mock_os.makedirs.assert_called_once_with("/output/filename_pptx", exist_ok=True)
        mock_file.assert_called_once()
        file_handler.post_process.assert_called_once()

    @patch("core.converter.image_converter.tqdm")
    @patch("core.converter.image_converter.os")
    @patch("core.converter.image_converter.docx", new_callable=MagicMock)
    def test_office_to_frames_exception_handling(
        self, mock_docx, mock_os, mock_tqdm, mock_dependencies
    ):
        # Test exception handling in office_to_frames
        file_handler, event_logger = mock_dependencies

        # Setup mocks
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.makedirs = Mock()

        # Make Document raise an exception
        mock_docx.Document.side_effect = Exception("Test error")

        doc_path_set = ("base", "filename_err", "docx")
        office_to_frames(
            doc_path_set, "png", "/output", False, file_handler, event_logger
        )

        # Verify error was logged
        event_logger.error.assert_called_once()


class TestGifToFrames:
    # Test the gif_to_frames function

    @pytest.fixture
    def mock_file_handler(self):
        handler = MagicMock()
        handler.join_back.return_value = "/path/to/test.gif"
        return handler

    @pytest.fixture
    def mock_event_logger(self):
        return MagicMock()

    @pytest.fixture
    def converter(self, mock_file_handler):
        prog_logger = MagicMock()
        event_logger = MagicMock()
        return ImageConverter(mock_file_handler, prog_logger, event_logger, "English")


class TestImageConverter:
    # Test the ImageConverter class

    @pytest.fixture
    def converter(self):
        file_handler = MagicMock()
        prog_logger = MagicMock()
        event_logger = MagicMock()

        # Setup default return values
        def join_back_side_effect(path_set):
            if len(path_set) == 3:
                return f"/mocked/path/{path_set[1]}.{path_set[2]}"
            return "/mocked/path/" + "/".join(path_set)

        file_handler.join_back.side_effect = join_back_side_effect
        file_handler.has_visuals.return_value = True
        file_handler.post_process = MagicMock()
        converter = ImageConverter(file_handler, prog_logger, event_logger, "English")
        return converter

    class TestToGif:
        # Test to_gif method

        @patch("core.converter.image_converter.VideoFileClip")
        @patch("core.converter.image_converter.Image.open")
        @patch("core.converter.image_converter.os")
        def test_to_gif_image_conversion(
            self, mock_os, mock_image_open, mock_video_clip, converter
        ):
            # Test image to GIF conversion
            # Setup mocks
            mock_os.path.exists.return_value = True
            mock_os.makedirs = Mock()
            mock_os.path.join.side_effect = lambda *args: "/".join(args)

            # Setup mock image
            mock_img = MagicMock()
            mock_image_open.return_value.__enter__.return_value = mock_img

            # Call the method
            converter.to_gif(
                input="/input",
                output="/output",
                file_paths={
                    Category.IMAGE: [("base", "test", "png")],
                    Category.MOVIE: [],
                    Category.DOCUMENT: [],
                    Category.AUDIO: [],
                },
                supported_formats={
                    Category.IMAGE: ["png", "gif"],
                    Category.MOVIE: ["mp4"],
                },
                framerate=30,
                format="gif",
                delete=False,
            )

            # Verify image was processed
            mock_image_open.assert_called_once()
            mock_img.convert.assert_called_once_with("RGB")

    class TestErrorHandling:
        # Test error handling

        @patch("core.converter.image_converter.VideoFileClip")
        @patch("core.converter.image_converter.os")
        def test_unsupported_movie_format(self, mock_os, mock_video_clip, converter):
            # Test handling of unsupported movie formats
            # Setup mocks
            mock_os.path.exists.return_value = True
            mock_os.makedirs = Mock()
            mock_os.path.join.side_effect = lambda *args: "/".join(args)

            # Call the method with unsupported format
            converter.to_frames(
                input="/input",
                output="/output",
                file_paths={
                    Category.MOVIE: [("base", "test", "unsupported")],
                    Category.IMAGE: [],
                    Category.DOCUMENT: [],
                    Category.AUDIO: [],
                },
                supported_formats={Category.IMAGE: ["png"], Category.MOVIE: ["mp4"]},
                framerate=30,
                format="png",
                delete=False,
            )

            # Verify error was logged
            converter.event_logger.info.assert_called()
            assert "unsupported" in converter.event_logger.info.call_args[0][0].lower()

    class TestEdgeCases:
        # Test edge cases

        @patch("core.converter.image_converter.VideoFileClip")
        @patch("core.converter.image_converter.os")
        def test_empty_file_paths(self, mock_os, mock_video_clip, converter):
            # Test with empty file paths
            # Setup mocks
            mock_os.path.exists.return_value = True
            mock_os.makedirs = Mock()
            mock_os.path.join.side_effect = lambda *args: "/".join(args)

            # Call the method with empty file paths
            converter.to_frames(
                input="/input",
                output="/output",
                file_paths={
                    Category.IMAGE: [],
                    Category.MOVIE: [],
                    Category.DOCUMENT: [],
                    Category.AUDIO: [],
                },
                supported_formats={Category.IMAGE: ["png"], Category.MOVIE: ["mp4"]},
                framerate=30,
                format="png",
                delete=False,
            )

            # Verify no errors occurred
            converter.event_logger.error.assert_not_called()
            converter.event_logger.info.assert_not_called()

        @patch("core.converter.image_converter.VideoFileClip")
        @patch("core.converter.image_converter.os")
        def test_format_already_matches_target(
            self, mock_os, mock_video_clip, converter
        ):
            # Test when source format matches target format
            # Setup mocks
            mock_os.path.exists.return_value = True
            mock_os.makedirs = Mock()
            mock_os.path.join.side_effect = lambda *args: "/".join(args)

            # Call the method with matching format
            converter.to_frames(
                input="/input",
                output="/output",
                file_paths={
                    Category.IMAGE: [("base", "test", "png")],
                    Category.MOVIE: [],
                    Category.DOCUMENT: [],
                    Category.AUDIO: [],
                },
                supported_formats={Category.IMAGE: ["png"], Category.MOVIE: ["mp4"]},
                framerate=30,
                format="png",
                delete=False,
            )

            # Verify no conversion was done
            converter.file_handler.post_process.assert_not_called()

        @patch("core.converter.image_converter.VideoFileClip")
        @patch("core.converter.image_converter.os")
        def test_localization(self, mock_os, mock_video_clip, converter):
            mock_os.path.exists.return_value = True
            mock_os.makedirs = Mock()
            mock_os.path.join.side_effect = lambda *args: "/".join(args)

            # Call the method with unsupported format to trigger error message
            converter.to_frames(
                input="/input",
                output="/output",
                file_paths={
                    Category.MOVIE: [("base", "test", "unsupported")],
                    Category.IMAGE: [],
                    Category.DOCUMENT: [],
                    Category.AUDIO: [],
                },
                supported_formats={Category.IMAGE: ["png"], Category.MOVIE: ["mp4"]},
                framerate=30,
                format="png",
                delete=False,
            )

            # Verify localized message was used
            assert (
                "unsupported_format"
                in converter.event_logger.info.call_args[0][0].lower()
                or "skipping" in converter.event_logger.info.call_args[0][0].lower()
            )

    @pytest.fixture
    def sample_file_paths(self):
        return {
            Category.IMAGE: [
                ("base", "test_image", "jpg"),
                ("base", "test_png", "png"),
            ],
            Category.DOCUMENT: [
                ("base", "test_doc", "pdf"),
                ("base", "test_docx", "docx"),
            ],
            Category.MOVIE: [
                ("base", "test_video", "mp4"),
                ("base", "test_avi", "avi"),
            ],
            Category.AUDIO: [("base", "test_audio", "mp3")],
        }

    @pytest.fixture
    def supported_formats(self):
        return {Category.MOVIE: ["mp4", "avi", "mov"]}


def test_gif_to_frames_creates_folder_and_files(
    tmp_path, monkeypatch, mock_file_handler=None
):
    fh = MagicMock()
    fh.join_back.return_value = str(tmp_path / "file.gif")
    monkeypatch.setattr("core.converter.image_converter.os", __import__("os"))
    # Call gif_to_frames with no gifs - should be no-op / not raise
    from core.converter.image_converter import gif_to_frames

    gif_files = {Category.IMAGE: []}
    gif_to_frames(str(tmp_path), gif_files, fh)


class TestSaveFormat:
    def test_jpg_aliases_to_jpeg(self):
        from core.converter.image_converter import _save_format

        assert _save_format("jpg") == "JPEG"
        assert _save_format("jpeg") == "JPEG"

    def test_heif_family(self):
        from core.converter.image_converter import _save_format

        assert _save_format("heic") == "HEIF"
        assert _save_format("heif") == "HEIF"
        assert _save_format("avif") == "AVIF"

    def test_unchanged_format(self):
        from core.converter.image_converter import _save_format

        assert _save_format("png") == "PNG"
        assert _save_format("webp") == "WEBP"
        assert _save_format("bmp") == "BMP"


class TestToHeic:
    # Test to_heic with in-memory image mocks
    def test_jpeg_to_heic(self, tmp_path):
        import numpy as np
        from PIL import Image

        img = Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype="uint8"))
        src = tmp_path / "photo.jpg"
        img.save(str(src), format="JPEG")

        file_paths = {
            Category.IMAGE: [(str(tmp_path) + "/", "photo", "jpg")],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
            Category.AUDIO: [],
        }
        converter = ImageConverter(MagicMock(), MagicMock(), MagicMock(), "English")
        converter.file_handler.join_back.return_value = str(src)
        converter.file_handler.post_process = MagicMock()
        converter.event_logger = MagicMock()
        converter.file_handler._resolve_output_file_conflict = MagicMock(
            side_effect=lambda x: x
        )

        converter.to_heic(
            input=str(tmp_path),
            output=str(tmp_path),
            file_paths=file_paths,
            supported_formats={Category.IMAGE: ["heic"]},
            framerate=0,
            format="heic",
            delete=False,
        )

        out = tmp_path / "photo.heic"
        assert out.exists()


class TestHeicToFrames:
    @pytest.fixture
    def heic_src(self, tmp_path):
        import numpy as np
        import pillow_heif
        from PIL import Image

        pillow_heif.register_heif_opener()
        img = Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype="uint8"))
        src = tmp_path / "photo.heic"
        img.save(str(src), format="HEIF")
        return src

    def _converter(self, src):
        converter = ImageConverter(MagicMock(), MagicMock(), MagicMock(), "English")
        converter.file_handler.join_back.return_value = str(src)
        converter.file_handler.post_process = MagicMock()
        converter.event_logger = MagicMock()
        converter.file_handler._resolve_output_file_conflict = MagicMock(
            side_effect=lambda x: x
        )
        return converter

    def test_heic_to_jpeg(self, tmp_path, heic_src):
        converter = self._converter(heic_src)
        file_paths = {
            Category.IMAGE: [(str(tmp_path) + "/", "photo", "heic")],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
            Category.AUDIO: [],
        }
        converter.to_frames(
            input=str(tmp_path),
            output=str(tmp_path),
            file_paths=file_paths,
            supported_formats={Category.IMAGE: ["jpeg"]},
            framerate=0,
            format="jpeg",
            delete=False,
        )
        assert (tmp_path / "photo.jpeg").exists()

    def test_heic_to_png(self, tmp_path, heic_src):
        converter = self._converter(heic_src)
        file_paths = {
            Category.IMAGE: [(str(tmp_path) + "/", "photo", "heic")],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
            Category.AUDIO: [],
        }
        converter.to_frames(
            input=str(tmp_path),
            output=str(tmp_path),
            file_paths=file_paths,
            supported_formats={Category.IMAGE: ["png"]},
            framerate=0,
            format="png",
            delete=False,
        )
        assert (tmp_path / "photo.png").exists()


class TestHeicToBmpAndWebp:
    @pytest.fixture
    def heic_src(self, tmp_path):
        import numpy as np
        import pillow_heif
        from PIL import Image

        pillow_heif.register_heif_opener()
        img = Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype="uint8"))
        src = tmp_path / "photo.heic"
        img.save(str(src), format="HEIF")
        return src

    def _converter(self, src):
        converter = ImageConverter(MagicMock(), MagicMock(), MagicMock(), "English")
        converter.file_handler.join_back.return_value = str(src)
        converter.file_handler.post_process = MagicMock()
        converter.event_logger = MagicMock()
        converter.file_handler._resolve_output_file_conflict = MagicMock(
            side_effect=lambda x: x
        )
        return converter

    def test_heic_to_bmp(self, tmp_path, heic_src):
        converter = self._converter(heic_src)
        file_paths = {
            Category.IMAGE: [(str(tmp_path) + "/", "photo", "heic")],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
            Category.AUDIO: [],
        }
        converter.to_bmp(
            input=str(tmp_path),
            output=str(tmp_path),
            file_paths=file_paths,
            supported_formats={Category.IMAGE: ["bmp"]},
            framerate=0,
            format="bmp",
            delete=False,
        )
        assert (tmp_path / "photo.bmp").exists()

    def test_heic_to_webp(self, tmp_path, heic_src):
        converter = self._converter(heic_src)
        file_paths = {
            Category.IMAGE: [(str(tmp_path) + "/", "photo", "heic")],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
            Category.AUDIO: [],
        }
        converter.to_webp(
            input=str(tmp_path),
            output=str(tmp_path),
            file_paths=file_paths,
            supported_formats={Category.IMAGE: ["webp"]},
            framerate=0,
            format="webp",
            delete=False,
        )
        assert (tmp_path / "photo.webp").exists()


class TestDeleteAndLogAfterFrameConversion:
    """-d must remove sources and a converted log must be emitted."""

    def _converter(self, logger_name):
        import logging
        from core.utils.file_handler import FileHandler

        event_logger = logging.getLogger(logger_name)
        file_handler = FileHandler(event_logger, "English")
        return ImageConverter(file_handler, MagicMock(), event_logger, "English")

    def test_gif_to_frames_delete_source_and_log(self, tmp_path, caplog, monkeypatch):
        import logging

        caplog.set_level(logging.INFO)
        converter = self._converter("gif-delete-test")

        src = tmp_path / "anim.gif"
        src.touch()
        frame_dir = tmp_path / "anim_frames"
        frame_dir.mkdir()
        (frame_dir / "anim-0.png").touch()
        (frame_dir / "anim-1.png").touch()

        monkeypatch.setattr(
            "core.converter.image_converter.gif_to_frames",
            lambda output, file_paths, file_handler, format="png": {
                "anim": str(frame_dir)
            },
        )

        converter.to_frames(
            input=str(tmp_path),
            output=str(tmp_path),
            file_paths={
                Category.IMAGE: [(str(tmp_path) + os.sep, "anim", "gif")],
                Category.MOVIE: [],
                Category.DOCUMENT: [],
                Category.AUDIO: [],
            },
            supported_formats={Category.IMAGE: ["png"]},
            framerate=None,
            format="png",
            delete=True,
        )

        assert not src.exists()
        assert str(frame_dir / "anim-1.png") in caplog.text

    @pytest.mark.parametrize("method,format", [("to_bmp", "bmp"), ("to_webp", "webp")])
    def test_pdf_to_frames_delete_source_and_log(
        self, tmp_path, caplog, method, format
    ):
        import logging
        import pymupdf

        caplog.set_level(logging.INFO)
        converter = self._converter(f"pdf-{format}-delete-test")

        src = tmp_path / "pages.pdf"
        pdf = pymupdf.open()
        pdf.new_page(width=72, height=72)
        pdf.new_page(width=72, height=72)
        pdf.save(str(src))
        pdf.close()

        out = tmp_path / "out"
        out.mkdir()

        getattr(converter, method)(
            input=str(tmp_path),
            output=str(out),
            file_paths={
                Category.DOCUMENT: [(str(tmp_path) + os.sep, "pages", "pdf")],
                Category.IMAGE: [],
                Category.MOVIE: [],
                Category.AUDIO: [],
            },
            supported_formats={Category.DOCUMENT: [format]},
            framerate=None,
            format=format,
            delete=True,
        )

        assert not src.exists()
        frames = sorted((out / "pages").glob(f"*.{format}"))
        assert frames
        assert frames[-1].name in caplog.text

    def test_images_to_gif_delete_sources_and_log(self, tmp_path, caplog):
        import logging
        from PIL import Image

        caplog.set_level(logging.INFO)
        converter = self._converter("images-gif-delete-test")

        first = tmp_path / "a.png"
        second = tmp_path / "b.png"
        Image.new("RGB", (8, 8), "red").save(first)
        Image.new("RGB", (8, 8), "blue").save(second)

        out = tmp_path / "out"
        out.mkdir()

        converter.to_gif(
            input=str(tmp_path),
            output=str(out),
            file_paths={
                Category.IMAGE: [
                    (str(tmp_path) + os.sep, "a", "png"),
                    (str(tmp_path) + os.sep, "b", "png"),
                ],
                Category.MOVIE: [],
                Category.DOCUMENT: [],
                Category.AUDIO: [],
            },
            supported_formats={Category.IMAGE: ["gif"]},
            framerate=None,
            format="gif",
            delete=True,
        )

        assert (out / "merged.gif").exists()
        assert not first.exists()
        assert not second.exists()
        assert "merged.gif" in caplog.text


class TestGifFramesHonorTargetFormat:
    """M5: GIF frame extraction must use the requested target format."""

    @staticmethod
    def _make_gif(path):
        from PIL import Image

        frames = [
            Image.new("RGB", (16, 16), color) for color in ("red", "green", "blue")
        ]
        frames[0].save(
            path,
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
        )

    @pytest.mark.parametrize(
        "fmt,extension,pil_format",
        [
            ("png", "png", "PNG"),
            ("jpeg", "jpeg", "JPEG"),
            ("jpg", "jpeg", "JPEG"),
            ("tiff", "tiff", "TIFF"),
        ],
    )
    def test_gif_to_frames_uses_requested_format(
        self, tmp_path, fmt, extension, pil_format
    ):
        import logging
        from PIL import Image
        from core.utils.file_handler import FileHandler
        from core.converter.image_converter import gif_to_frames

        logger = logging.getLogger(f"m5-{fmt}")
        file_handler = FileHandler(logger, "English")

        src = tmp_path / "anim.gif"
        self._make_gif(str(src))

        out = tmp_path / "out"
        out.mkdir()

        created = gif_to_frames(
            str(out),
            {Category.IMAGE: [(str(tmp_path) + os.sep, "anim", "gif")]},
            file_handler,
            fmt,
        )

        written = sorted(os.listdir(created["anim"]))
        assert len(written) == 3
        assert all(name.endswith(f".{extension}") for name in written)
        for name in written:
            with Image.open(os.path.join(created["anim"], name)) as img:
                assert img.format == pil_format

    def test_to_frames_gif_to_jpeg_end_to_end(self, tmp_path, caplog):
        import glob
        import logging
        from PIL import Image
        from core.utils.file_handler import FileHandler

        caplog.set_level(logging.INFO)
        logger = logging.getLogger("m5-to-frames-e2e")
        file_handler = FileHandler(logger, "English")
        converter = ImageConverter(file_handler, MagicMock(), logger, "English")

        src = tmp_path / "anim.gif"
        self._make_gif(str(src))

        out = tmp_path / "out"
        out.mkdir()

        converter.to_frames(
            input=str(tmp_path),
            output=str(out),
            file_paths={
                Category.IMAGE: [(str(tmp_path) + os.sep, "anim", "gif")],
                Category.MOVIE: [],
                Category.DOCUMENT: [],
                Category.AUDIO: [],
            },
            supported_formats={Category.IMAGE: ["jpeg"]},
            framerate=None,
            format="jpeg",
            delete=True,
        )

        frames = sorted(glob.glob(str(out / "anim" / "*.jpeg")))
        assert len(frames) == 3
        assert not glob.glob(str(out / "anim" / "*.png"))
        for path in frames:
            with Image.open(path) as img:
                assert img.format == "JPEG"
        assert not src.exists()
        assert os.path.basename(frames[-1]) in caplog.text


class TestOfficeDocFrameDirClaim:
    """docx/pptx -> frames must claim the output dir exactly once"""

    @staticmethod
    def _make_docx(tmp_path):
        import docx
        from PIL import Image

        Image.new("RGB", (32, 32), "teal").save(tmp_path / "pic.png")
        doc = docx.Document()
        doc.add_picture(str(tmp_path / "pic.png"))
        doc_path = tmp_path / "report.docx"
        doc.save(str(doc_path))
        return doc_path

    def _run(self, converter, tmp_path, out):
        converter.to_frames(
            input=str(tmp_path),
            output=str(out),
            file_paths={
                Category.IMAGE: [],
                Category.MOVIE: [],
                Category.DOCUMENT: [(str(tmp_path) + os.sep, "report", "docx")],
                Category.AUDIO: [],
            },
            supported_formats={Category.IMAGE: ["png"]},
            framerate=None,
            format="png",
            delete=False,
        )

    def _converter(self, logger_name):
        import logging
        from core.utils.file_handler import FileHandler

        logger = logging.getLogger(logger_name)
        file_handler = FileHandler(logger, "English")
        return ImageConverter(file_handler, MagicMock(), logger, "English")

    def test_docx_frames_land_in_resolved_dir_without_duplicate(self, tmp_path):
        converter = self._converter("m4-single-claim")
        doc_path = self._make_docx(tmp_path)

        out = tmp_path / "out"
        out.mkdir()

        self._run(converter, tmp_path, out)

        frames = list((out / "report").glob("*.png"))
        assert frames
        assert not (out / "report_1").exists()

    def test_docx_frames_use_conflict_resolved_dir_only_once(self, tmp_path):
        converter = self._converter("m4-conflict-claim")
        self._make_docx(tmp_path)

        out = tmp_path / "out"
        (out / "report").mkdir(parents=True)
        (out / "report" / "keep.txt").write_text("user data")

        self._run(converter, tmp_path, out)

        assert (out / "report" / "keep.txt").read_text() == "user data"
        assert list((out / "report_1").glob("*.png"))
        assert not (out / "report_2").exists()


class TestManualProgressReporting:
    # Manual (tqdm) loops have to report progress to shared dict (for GUI/web to react to)

    def test_pdf_to_frames_reports_each_page(self, tmp_path):
        import logging
        import pymupdf
        from core.utils.file_handler import FileHandler
        from utils.prog_logger import ProgLogger

        src = tmp_path / "pages.pdf"
        pdf = pymupdf.open()
        for _ in range(4):
            pdf.new_page(width=72, height=72)
        pdf.save(str(src))
        pdf.close()

        shared = {}
        prog_logger = ProgLogger(
            job_id="job-pdf-frames", shared_progress_dict=shared, is_web=True
        )
        file_handler = FileHandler(logging.getLogger("pdf-frames-progress"), "English")
        converter = ImageConverter(file_handler, prog_logger, MagicMock(), "English")

        out = tmp_path / "out"
        out.mkdir()

        converter.to_bmp(
            input=str(tmp_path),
            output=str(out),
            file_paths={
                Category.DOCUMENT: [(str(tmp_path) + os.sep, "pages", "pdf")],
                Category.IMAGE: [],
                Category.MOVIE: [],
                Category.AUDIO: [],
            },
            supported_formats={Category.DOCUMENT: ["bmp"]},
            framerate=None,
            format="bmp",
            delete=False,
        )

        state = shared["job-pdf-frames"]
        assert state["total"] == 4
        assert state["progress"] == 4
        assert state["status"] == "pages (4/4)"


class TestRasterConvertibleSources:
    def _converter(self, logger_name):
        import logging

        from core.utils.file_handler import FileHandler

        event_logger = logging.getLogger(logger_name)
        return ImageConverter(
            FileHandler(event_logger, "English"), MagicMock(), event_logger, "English"
        )

    def test_raster_convertible_covers_advertised_image_sources(self):
        from core.controller import Controller
        from core.converter.image_converter import _RASTER_CONVERTIBLE

        advertised = set(Controller()._supported_formats[Category.IMAGE])
        assert advertised - {"gif"} <= _RASTER_CONVERTIBLE

    @pytest.mark.parametrize(
        "method, target, source_ext, save_format",
        [
            ("to_bmp", "bmp", "webp", "WEBP"),
            ("to_bmp", "bmp", "ico", "ICO"),
            ("to_bmp", "bmp", "pcx", "PCX"),
            ("to_bmp", "bmp", "ppm", "PPM"),
            ("to_webp", "webp", "bmp", "BMP"),
            ("to_webp", "webp", "tiff", "TIFF"),
        ],
    )
    def test_advertised_still_converts(
        self, tmp_path, method, target, source_ext, save_format
    ):
        from PIL import Image

        src = tmp_path / f"photo.{source_ext}"
        Image.new("RGB", (16, 16), (10, 20, 30)).save(src, format=save_format)

        out = tmp_path / "out"
        out.mkdir()
        converter = self._converter("advertised-still-converts")

        getattr(converter, method)(
            input=str(tmp_path),
            output=str(out),
            file_paths={
                Category.IMAGE: [(str(tmp_path) + os.sep, "photo", source_ext)],
                Category.MOVIE: [],
                Category.DOCUMENT: [],
                Category.AUDIO: [],
            },
            supported_formats={Category.IMAGE: [target]},
            framerate=None,
            format=target,
            delete=False,
        )

        assert (out / f"photo.{target}").exists()


class TestNonOpenableSourcesAreSkipped:
    def _garbage_source(self, tmp_path, name):
        src = tmp_path / name
        src.write_bytes(b"\x00" * 64)
        return src

    def _converter(self, logger_name):
        import logging

        from core.utils.file_handler import FileHandler

        event_logger = logging.getLogger(logger_name)
        return ImageConverter(
            FileHandler(event_logger, "English"), MagicMock(), event_logger, "English"
        )

    def test_to_bmp_skips_source_pil_cannot_open(self, tmp_path, caplog):
        import logging

        caplog.set_level(logging.INFO)
        src = self._garbage_source(tmp_path, "broken.webp")
        converter = self._converter("bmp-skip-unopenable")
        out = tmp_path / "out"
        out.mkdir()

        converter.to_bmp(
            input=str(tmp_path),
            output=str(out),
            file_paths={
                Category.IMAGE: [(str(tmp_path) + os.sep, "broken", "webp")],
                Category.MOVIE: [],
                Category.DOCUMENT: [],
                Category.AUDIO: [],
            },
            supported_formats={Category.IMAGE: ["bmp"]},
            framerate=None,
            format="bmp",
            delete=True,
        )

        assert all(record.levelno < logging.ERROR for record in caplog.records)
        assert "Skipping" in caplog.text
        assert "Unsupported format" in caplog.text
        assert not (out / "broken.bmp").exists()
        assert src.exists()

    def test_to_frames_skips_source_pil_cannot_open(self, tmp_path, caplog):
        import logging

        caplog.set_level(logging.INFO)
        src = self._garbage_source(tmp_path, "broken.tga")
        converter = self._converter("frames-skip-unopenable")
        out = tmp_path / "out"
        out.mkdir()

        converter.to_frames(
            input=str(tmp_path),
            output=str(out),
            file_paths={
                Category.IMAGE: [(str(tmp_path) + os.sep, "broken", "tga")],
                Category.MOVIE: [],
                Category.DOCUMENT: [],
                Category.AUDIO: [],
            },
            supported_formats={Category.IMAGE: ["bmp"], Category.MOVIE: ["mp4"]},
            framerate=None,
            format="bmp",
            delete=True,
        )

        assert all(record.levelno < logging.ERROR for record in caplog.records)
        assert "Skipping" in caplog.text
        assert "Unsupported format" in caplog.text
        assert not (out / "broken.bmp").exists()
        assert src.exists()


class TestAlphaHandling:

    def _converter(self, logger_name):
        import logging

        from core.utils.file_handler import FileHandler

        event_logger = logging.getLogger(logger_name)
        return ImageConverter(
            FileHandler(event_logger, "English"), MagicMock(), event_logger, "English"
        )

    def _rgba_source(self, tmp_path):
        from PIL import Image

        src = tmp_path / "logo.png"
        img = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        img.putpixel((0, 0), (255, 0, 0, 255))
        img.save(src)
        return src

    def _file_paths(self, tmp_path, ext):
        return {
            Category.IMAGE: [(str(tmp_path) + os.sep, "logo", ext)],
            Category.MOVIE: [],
            Category.DOCUMENT: [],
            Category.AUDIO: [],
        }

    def _run_stills(self, method, tmp_path, format):
        from pathlib import Path

        out = Path(tmp_path) / "out"
        out.mkdir()
        converter = self._converter(f"alpha-{format}")
        getattr(converter, method)(
            input=str(tmp_path),
            output=str(out),
            file_paths=self._file_paths(tmp_path, "png"),
            supported_formats={Category.IMAGE: [format], Category.MOVIE: ["mp4"]},
            framerate=None,
            format=format,
            delete=False,
        )
        return out

    def test_rgba_png_to_tiff_keeps_alpha(self, tmp_path):
        from PIL import Image

        self._rgba_source(tmp_path)
        out = self._run_stills("to_frames", tmp_path, "tiff")

        with Image.open(out / "logo.tiff") as result:
            assert result.mode == "RGBA"
            assert result.getpixel((0, 0)) == (255, 0, 0, 255)
            assert result.getpixel((1, 1))[3] == 0

    def test_rgba_png_to_jpeg_flattens_onto_white(self, tmp_path):
        from PIL import Image

        src = tmp_path / "logo.png"
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        for x in range(8):
            for y in range(8):
                img.putpixel((x, y), (255, 0, 0, 255))
        img.save(src)
        out = self._run_stills("to_frames", tmp_path, "jpeg")

        with Image.open(out / "logo.jpeg") as result:
            assert result.mode == "RGB"
            assert min(result.getpixel((14, 14))) > 220
            r, g = result.getpixel((4, 4))[:2]
            assert r > 180 and g < 80

    def test_rgba_png_to_webp_keeps_alpha(self, tmp_path):
        from PIL import Image

        self._rgba_source(tmp_path)
        out = self._run_stills("to_webp", tmp_path, "webp")

        with Image.open(out / "logo.webp") as result:
            assert result.mode == "RGBA"
            assert result.getpixel((1, 1))[3] == 0

    def test_rgba_png_to_bmp_flattens_onto_white(self, tmp_path):
        from PIL import Image

        self._rgba_source(tmp_path)
        out = self._run_stills("to_bmp", tmp_path, "bmp")

        with Image.open(out / "logo.bmp") as result:
            assert result.mode == "RGB"
            assert min(result.getpixel((1, 1))) > 220

    def test_rgba_png_to_heic_keeps_alpha(self, tmp_path):
        from PIL import Image

        self._rgba_source(tmp_path)
        out = self._run_stills("to_heic", tmp_path, "heic")

        with Image.open(out / "logo.heic") as result:
            assert result.mode == "RGBA"
            assert result.getpixel((1, 1))[3] == 0

    def test_office_frame_extraction_keeps_alpha(self, tmp_path):
        import io

        from PIL import Image
        from core.converter.image_converter import _write_office_frame

        buf = io.BytesIO()
        Image.new("RGBA", (4, 4), (10, 20, 30, 128)).save(buf, format="PNG")
        out = tmp_path / "frame.tiff"

        _write_office_frame(buf.getvalue(), str(out), "tiff")

        with Image.open(out) as result:
            assert result.mode == "RGBA"
            assert result.getpixel((0, 0)) == (10, 20, 30, 128)
