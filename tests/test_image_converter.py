import os
import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, MagicMock

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.category import Category
from core.image_converter import ImageConverter, office_to_frames


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
    @patch("core.image_converter.tqdm")
    @patch("core.image_converter.os")
    @patch("core.image_converter.docx", new_callable=MagicMock)
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

        doc_path_set = ("base", "filename", "docx")

        with patch("builtins.open", mock_open()) as mock_file:
            office_to_frames(
                doc_path_set, "png", "/output", False, file_handler, event_logger
            )

        # Assertions
        mock_docx.Document.assert_called_once_with("/path/to/file.docx")
        mock_os.makedirs.assert_called_once_with("/output/filename", exist_ok=True)
        mock_file.assert_called_once()
        file_handler.post_process.assert_called_once()
        event_logger.error.assert_not_called()

    @patch("core.image_converter.tqdm")
    @patch("core.image_converter.os")
    @patch("core.image_converter.pptx")
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

        doc_path_set = ("base", "filename", "pptx")

        with patch("builtins.open", mock_open()) as mock_file:
            office_to_frames(
                doc_path_set, "png", "/output", False, file_handler, event_logger
            )

        # Assertions
        mock_pptx.Presentation.assert_called_once_with("/path/to/file.docx")
        mock_os.makedirs.assert_called_once_with("/output/filename", exist_ok=True)
        mock_file.assert_called_once()
        file_handler.post_process.assert_called_once()

    @patch("core.image_converter.tqdm")
    @patch("core.image_converter.os")
    @patch("core.image_converter.docx", new_callable=MagicMock)
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

        doc_path_set = ("base", "filename", "docx")
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

        @patch("core.image_converter.VideoFileClip")
        @patch("core.image_converter.Image.open")
        @patch("core.image_converter.os")
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

        @patch("core.image_converter.VideoFileClip")
        @patch("core.image_converter.os")
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

        @patch("core.image_converter.VideoFileClip")
        @patch("core.image_converter.os")
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

        @patch("core.image_converter.VideoFileClip")
        @patch("core.image_converter.os")
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

        @patch("core.image_converter.VideoFileClip")
        @patch("core.image_converter.os")
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
