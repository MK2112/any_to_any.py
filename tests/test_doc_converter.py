import os
import fitz
import docx
import pptx
import shutil
import pytest
import mammoth
import tempfile
import subprocess
import numpy as np

from PIL import Image
from utils.category import Category
from core.doc_converter import DocumentConverter
from tests.test_fixtures import setup_file_handler_mock
from unittest.mock import Mock, patch, mock_open, MagicMock, call


@pytest.fixture
def mock_file_handler():
    # Create a mock file handler
    handler = Mock()
    handler.join_back.return_value = "/mock/path/file.ext"
    handler.post_process.return_value = None
    handler.has_visuals.return_value = True
    setup_file_handler_mock(handler)
    return handler


@pytest.fixture
def mock_prog_logger():
    # Create a mock progress logger
    return Mock()


@pytest.fixture
def mock_event_logger():
    # Create a mock event logger
    logger = Mock()
    logger.info.return_value = None
    return logger


@pytest.fixture
def document_converter(mock_file_handler, mock_prog_logger, mock_event_logger):
    # Create a DocumentConverter instance with mocked dependencies
    return DocumentConverter(
        file_handler=mock_file_handler,
        prog_logger=mock_prog_logger,
        event_logger=mock_event_logger,
        locale="English",
    )


@pytest.fixture
def temp_output_dir():
    # Create a temporary directory for test outputs
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_file_paths():
    # Create sample file paths for testing
    return {
        Category.DOCUMENT: [
            ("/path", "test_doc", "docx"),
            ("/path", "test_pdf", "pdf"),
            ("/path", "test_srt", "srt"),
            ("/path", "test_pptx", "pptx"),
        ],
        Category.IMAGE: [
            ("/path", "test_image", "jpg"),
            ("/path", "test_gif", "gif"),
            ("/path", "test_png", "png"),
        ],
        Category.MOVIE: [
            ("/path", "test_movie", "mp4"),
            ("/path", "test_video", "avi"),
        ],
    }


class TestDocumentConverterInit:
    # Test DocumentConverter initialization

    def test_init_with_default_locale(
        self, mock_file_handler, mock_prog_logger, mock_event_logger
    ):
        converter = DocumentConverter(
            file_handler=mock_file_handler,
            prog_logger=mock_prog_logger,
            event_logger=mock_event_logger,
        )
        assert converter.locale == "English"

    def test_init_with_custom_locale(
        self, mock_file_handler, mock_prog_logger, mock_event_logger
    ):
        converter = DocumentConverter(
            file_handler=mock_file_handler,
            prog_logger=mock_prog_logger,
            event_logger=mock_event_logger,
            locale="Spanish",
        )
        assert converter.locale == "Spanish"


class TestDocumentConverterToMarkdown:

    @patch("core.doc_converter.markdownify")
    def test_to_markdown_docx_conversion(
        self, mock_markdownify, document_converter, temp_output_dir, sample_file_paths
    ):
        # Test DOCX to Markdown conversion
        # Setup
        docx_path = os.path.join(temp_output_dir, "test_doc.docx")
        doc = docx.Document()
        doc.add_paragraph("Test content")
        doc.save(docx_path)

        # Mock markdownify to return a specific markdown string
        mock_markdownify.return_value = "# Test content"

        # Mock file handler to return the test docx path
        document_converter.file_handler.join_back.return_value = docx_path

        # Call the method
        document_converter.to_markdown(
            output=temp_output_dir,
            file_paths={Category.DOCUMENT: [("path", "test_doc", "docx")]},
            format="md",
            delete=False,
        )

        # Verify markdownify was called
        mock_markdownify.assert_called_once()

        # Verify the output file was created
        output_path = os.path.join(temp_output_dir, "test_doc.md")
        assert os.path.exists(output_path)
        with open(output_path, "r") as f:
            content = f.read()
            assert content == "# Test content"

        # Verify post_process was called
        document_converter.file_handler.post_process.assert_called_once()

    @patch("mammoth.convert_to_html")
    @patch("os.makedirs")
    def test_to_markdown_with_images(
        self, mock_makedirs, mock_mammoth, document_converter, temp_output_dir
    ):
        # Setup mock for mammoth with image handling
        mock_image = Mock()
        mock_image.content_type = "image/png"
        mock_image.open.return_value.__enter__ = Mock()
        mock_image.open.return_value.__exit__ = Mock(return_value=None)
        mock_image.open.return_value.__enter__.return_value.read.return_value = (
            b"image_data"
        )

        mock_document = Mock()
        mock_document.value = "<p>Content with image</p>"
        mock_mammoth.return_value = mock_document

        docx_files = {Category.DOCUMENT: [("/path", "test_doc", "docx")]}

        with (
            patch("builtins.open", mock_open()),
            patch("markdownify.markdownify", return_value="markdown"),
        ):
            document_converter.to_markdown(temp_output_dir, docx_files, "md", False)

        mock_makedirs.assert_called()
        mock_mammoth.assert_called_once()


class TestDocumentConverterToPdf:

    @patch("core.doc_converter.fitz.open")
    @patch("core.doc_converter.fitz.Pixmap")
    def test_to_pdf_image_conversion(
        self,
        mock_pixmap,
        mock_fitz_open,
        document_converter,
        temp_output_dir,
        sample_file_paths,
    ):
        # Test image to PDF conversion
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_pix = MagicMock(width=100, height=100)
        mock_pixmap.return_value = mock_pix
        mock_doc.new_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        # Mock file handler
        document_converter.file_handler.join_back.return_value = os.path.join(
            "path", "test_image.jpg"
        )

        # Call the method with a proper file_paths structure
        document_converter.to_pdf(
            output=temp_output_dir,
            file_paths={
                Category.IMAGE: [("path", "test_image", "jpg")],
                Category.MOVIE: [],
                Category.DOCUMENT: [],
            },
            format="pdf",
            delete=False,
        )

        # Verify the PDF was created
        mock_doc.save.assert_called_once()
        mock_doc.close.assert_called()

    @patch("core.doc_converter.gif_to_frames")
    @patch("core.doc_converter.fitz.open")
    @patch("os.listdir")
    @patch("os.path.join")
    @patch("core.doc_converter.fitz.Pixmap")
    @patch("shutil.rmtree")
    def test_to_pdf_gif_conversion(
        self,
        mock_rmtree,
        mock_pixmap,
        mock_join,
        mock_listdir,
        mock_fitz_open,
        mock_gif_to_frames,
        document_converter,
        temp_output_dir,
    ):
        # Test GIF to PDF conversion
        # Setup
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_pix = MagicMock(width=100, height=100)
        mock_pixmap.return_value = mock_pix
        mock_doc.new_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc
        mock_listdir.return_value = ["frame1.png", "frame2.png"]
        mock_join.side_effect = lambda *args: "/".join(args)

        # Mock gif_to_frames to create the expected directory structure
        def mock_gif_to_frames_impl(output, file_paths, file_handler):
            gif_dir = os.path.join(output, file_paths[Category.IMAGE][0][1])
            os.makedirs(gif_dir, exist_ok=True)
            with open(os.path.join(gif_dir, "frame1.png"), "wb") as f:
                f.write(b"fake image data")
            with open(os.path.join(gif_dir, "frame2.png"), "wb") as f:
                f.write(b"fake image data")

        mock_gif_to_frames.side_effect = mock_gif_to_frames_impl

        # Mock file handler
        document_converter.file_handler.join_back.return_value = os.path.join(
            "path", "test_gif.gif"
        )

        # Call the method with a proper file_paths structure
        document_converter.to_pdf(
            output=temp_output_dir,
            file_paths={
                Category.IMAGE: [["path", "test_gif", "gif"]],
                Category.MOVIE: [],
                Category.DOCUMENT: [],
            },
            format="pdf",
            delete=False,
        )

        # Verify the PDF was created and cleanup was performed
        mock_doc.save.assert_called_once()
        mock_rmtree.assert_called()

    @patch("PIL.Image.fromarray")
    @patch("os.remove")
    @patch("core.doc_converter.VideoFileClip")
    @patch("core.doc_converter.fitz.open")
    @patch("core.doc_converter.fitz.Pixmap")
    @patch("os.path.join")
    def test_to_pdf_movie_conversion(
        self,
        mock_join,
        mock_pixmap,
        mock_fitz_open,
        mock_video_clip,
        mock_remove,
        mock_image_fromarray,
        document_converter,
        temp_output_dir,
    ):
        # Setup mocks
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_pix = MagicMock(width=100, height=100)
        mock_pixmap.return_value = mock_pix
        mock_doc.new_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        # Mock video clip
        mock_video = MagicMock()
        mock_video.fps = 30
        mock_video.duration = 2.0
        # Create a dummy frame array
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_video.iter_frames.return_value = [frame, frame]  # Two frames
        mock_video_clip.return_value.__enter__.return_value = mock_video
        # Mock PIL Image
        mock_img = MagicMock()
        mock_image_fromarray.return_value = mock_img

        # Mock file handler and path joining
        document_converter.file_handler.join_back.return_value = os.path.join(
            "path", "test_movie.mp4"
        )
        mock_join.side_effect = lambda *args: "/".join(args)

        # Call the method with a proper file_paths structure
        document_converter.to_pdf(
            output=temp_output_dir,
            file_paths={
                Category.MOVIE: [["path", "test_movie", "mp4"]],
                Category.IMAGE: [],
                Category.DOCUMENT: [],
            },
            format="pdf",
            delete=False,
        )

        # Verify the PDF was created
        mock_doc.save.assert_called_once()
        mock_video_clip.assert_called_once()


class TestDocumentConverterToSubtitles:
    # Test the to_subtitles conversion method

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.path.getsize")
    @patch("utils.language_support.get_translation")
    def test_to_subtitles_success(
        self,
        mock_get_translation,
        mock_getsize,
        mock_exists,
        mock_subprocess,
        document_converter,
        temp_output_dir,
    ):
        # Setup mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 100  # Non-empty file
        mock_get_translation.return_value = "Extracting subtitles"
        mock_subprocess.return_value = Mock()

        movie_files = {
            Category.MOVIE: [("/path", "test_movie", "mp4")],
            Category.IMAGE: [],
            Category.DOCUMENT: [],
        }

        document_converter.to_subtitles(temp_output_dir, movie_files, "srt", False)

        mock_subprocess.assert_called()
        document_converter.file_handler.post_process.assert_called()

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.path.getsize")
    @patch("utils.language_support.get_translation")
    def test_to_subtitles_fallback_method(
        self,
        mock_get_translation,
        mock_getsize,
        mock_exists,
        mock_subprocess,
        document_converter,
        temp_output_dir,
    ):
        # Setup mocks for first attempt failure, second attempt success
        mock_exists.side_effect = [False, True]  # First fails, second succeeds
        mock_getsize.side_effect = [0, 100]  # First empty, second has content
        mock_get_translation.return_value = "Extracting subtitles"
        mock_subprocess.return_value = Mock()

        movie_files = {
            Category.MOVIE: [("/path", "test_movie", "mp4")],
            Category.IMAGE: [],
            Category.DOCUMENT: [],
        }

        document_converter.to_subtitles(temp_output_dir, movie_files, "srt", False)
        assert mock_subprocess.call_count == 2  # Both attempts called


class TestDocumentConverterEdgeCases:
    # Test edge cases and error conditions

    def test_empty_file_paths(self, document_converter, temp_output_dir):
        # Test behavior with empty file paths
        empty_paths = {Category.DOCUMENT: [], Category.IMAGE: [], Category.MOVIE: []}

        # Should not raise exceptions
        document_converter.to_markdown(temp_output_dir, empty_paths, "md", False)
        document_converter.to_pdf(temp_output_dir, empty_paths, "pdf", False)
        document_converter.to_subtitles(temp_output_dir, empty_paths, "srt", False)
        document_converter.to_office(temp_output_dir, empty_paths, "docx", False)

    @patch("fitz.open")
    def test_pdf_skip_existing_pdf(
        self, mock_fitz_open, document_converter, temp_output_dir
    ):
        # Test PDF conversion skipping pdf files (already pdfs)
        pdf_files = {
            Category.DOCUMENT: [("/path", "test", "pdf")],
            Category.IMAGE: [],
            Category.MOVIE: [],
        }
        with patch("core.image_converter.gif_to_frames"):
            document_converter.to_pdf(temp_output_dir, pdf_files, "pdf", False)
        # Should not process PDF files when converting to PDF
        mock_fitz_open.assert_not_called()


class TestDocumentConverterPdfSplitting:
    def test_split_pdf_with_real_file(self, document_converter, temp_output_dir):
        # Test PDF splitting with a real PDF file
        # Create a simple PDF with 5 pages
        pdf_path = os.path.join(temp_output_dir, "test.pdf")
        doc = fitz.open()

        # Add 5 pages with page numbers
        for i in range(5):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page {i + 1}")
        doc.save(pdf_path)
        doc.close()

        # Test splitting into two parts: pages 1-2 and 3-5
        doc_path_set = (temp_output_dir, "test", "pdf")
        document_converter.file_handler.join_back.return_value = pdf_path

        # Split the PDF
        document_converter.split_pdf(
            output=temp_output_dir,
            doc_path_set=doc_path_set,
            page_ranges="1-2,3-5",
            delete=False,
            format="pdf",
        )

        # Verify the output files were created with the correct naming pattern
        part1_path = os.path.join(temp_output_dir, "test_split_1_1-2.pdf")
        part2_path = os.path.join(temp_output_dir, "test_split_2_3-5.pdf")

        assert os.path.exists(part1_path)
        assert os.path.exists(part2_path)

        # Verify the page counts are correct
        part1 = fitz.open(part1_path)
        part2 = fitz.open(part2_path)

        assert len(part1) == 2  # First part has 2 pages
        assert len(part2) == 3  # Second part has 3 pages

        # Clean up
        part1.close()
        part2.close()

        # Verify the content of the first page of each part
        part1 = fitz.open(part1_path)
        part2 = fitz.open(part2_path)

        assert "Page 1" in part1[0].get_text()
        assert "Page 3" in part2[0].get_text()

        part1.close()
        part2.close()


class TestDocumentConverterIntegration:
    # Integration tests that test multiple components together
    @patch("core.image_converter.gif_to_frames")
    @patch("fitz.open")
    @patch("mammoth.convert_to_html")
    @patch("weasyprint.HTML")
    def test_docx_to_pdf_integration(
        self,
        mock_weasyprint,
        mock_mammoth,
        mock_fitz_open,
        mock_gif_to_frames,
        document_converter,
        temp_output_dir,
    ):
        # Test DOCX to PDF conversion integration
        mock_document = Mock()
        mock_document.value = "<p>Test content</p>"
        mock_mammoth.return_value = mock_document

        mock_html = Mock()
        mock_weasyprint.return_value = mock_html

        docx_files = {
            Category.DOCUMENT: [("/path", "test_doc", "docx")],
            Category.IMAGE: [],
            Category.MOVIE: [],
        }

        with patch("builtins.open", mock_open()):
            document_converter.to_pdf(temp_output_dir, docx_files, "pdf", False)

        mock_mammoth.assert_called_once()
        document_converter.file_handler.post_process.assert_called()

@pytest.mark.parametrize(
    "page_ranges,total,expected",
    [
        (None, 10, None),
        ("", 5, None),
        ("all", 7, None),
        ("rest", 7, None),
        ("3", 10, [(3, 3)]),
        ("1-3", 10, [(1, 3)]),
        ("2-5,7-8", 10, [(2, 5), (7, 8)]),
        ("2-5;7-8", 10, [(2, 5), (7, 8)]),
        ("12-end", 20, [(12, 20)]),
        ("2-end,4-6", 10, [(2, 10), (4, 6)]),
        ("3-4,rest", 6, [(3, 4), (5, 6)]),
        ("2-4,2-4", 8, [(2, 4)]),
        ("999", 5, None),
        ("a-b", 5, None),
    ],
)
def test_parse_page_ranges_various(document_converter, page_ranges, total, expected):
    res = document_converter._parse_page_ranges(page_ranges, total)
    assert res == expected


def test_parse_page_ranges_rest_after_range(document_converter):
    # 'rest' after a specific range should pick up after highest end
    res = document_converter._parse_page_ranges("1-2,rest", 5)
    assert res == [(1, 2), (3, 5)]
