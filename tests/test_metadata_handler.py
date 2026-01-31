import os
import pytest

from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from core.controller import Controller
from core.utils.metadata_handler import MetadataHandler


@pytest.fixture
def metadata_handler():
    # Create a MetadataHandler instance with mock logger
    logger = Mock()
    handler = MetadataHandler(logger, locale="English")
    return handler


@pytest.fixture
def temp_metadata_dir(tmp_path):
    # Create temporary directory for metadata storage
    metadata_dir = tmp_path / "metadata_output"
    metadata_dir.mkdir()
    return metadata_dir


@pytest.fixture
def mock_audio_file(tmp_path):
    # Create mock audio file
    audio_file = tmp_path / "test_audio.mp3"
    audio_file.write_bytes(b"fake_audio_data")
    return audio_file


@pytest.fixture
def mock_image_file(tmp_path):
    # Create mock image file
    image_file = tmp_path / "test_image.jpg"
    image_file.write_bytes(b"fake_image_data")
    return image_file


@pytest.fixture
def mock_document_file(tmp_path):
    # Create mock document file
    doc_file = tmp_path / "test_document.pdf"
    doc_file.write_bytes(b"fake_pdf_data")
    return doc_file


@pytest.fixture
def controller_instance():
    """Create a Controller instance for testing."""
    controller = Controller()
    controller.locale = "English"
    return controller


class TestMetadataHandlerInitialization:
    def test_initialization(self, metadata_handler):
        assert metadata_handler is not None
        assert metadata_handler.locale == "English"
        assert metadata_handler.metadata_dir is None

    def test_set_metadata_dir(self, metadata_handler, temp_metadata_dir):
        # Test setting metadata directory
        metadata_handler.set_metadata_dir(str(temp_metadata_dir))
        expected_path = os.path.join(str(temp_metadata_dir), ".metadata")
        assert metadata_handler.metadata_dir == expected_path
        assert os.path.exists(metadata_handler.metadata_dir)

    def test_set_metadata_dir_creates_directory(self, metadata_handler, tmp_path):
        # Test that set_metadata_dir creates directory if it doesn't exist
        new_dir = tmp_path / "new_metadata"
        metadata_handler.set_metadata_dir(str(new_dir))
        assert os.path.exists(str(new_dir))


class TestCustomTagParsing:
    def test_parse_custom_tags_empty(self, metadata_handler):
        # Test parsing empty tag list
        result = metadata_handler.parse_custom_tags([])
        assert result == {}

    def test_parse_custom_tags_single(self, metadata_handler):
        # Test parsing single tag
        result = metadata_handler.parse_custom_tags(["key:value"])
        assert result == {"key": "value"}

    def test_parse_custom_tags_multiple(self, metadata_handler):
        # Test parsing multiple tags
        tags = ["project:archive", "year:2024", "status:complete"]
        result = metadata_handler.parse_custom_tags(tags)
        assert result == {
            "project": "archive",
            "year": "2024",
            "status": "complete",
        }

    def test_parse_custom_tags_with_colons(self, metadata_handler):
        # Test parsing tags with colons in values
        tags = ["timestamp:2024-01-31T10:30:45"]
        result = metadata_handler.parse_custom_tags(tags)
        assert result == {"timestamp": "2024-01-31T10:30:45"}

    def test_parse_custom_tags_invalid_format(self, metadata_handler):
        # Test parsing tags without colon (should be skipped)
        tags = ["valid:tag", "invalid_tag", "another:valid"]
        result = metadata_handler.parse_custom_tags(tags)
        assert "valid" in result
        assert "another" in result
        assert len(result) == 2


class TestMetadataExtraction:
    def test_extract_metadata_audio(self, metadata_handler, mock_audio_file):
        # Test audio metadata extraction
        with patch.object(metadata_handler, 'extract_audio_metadata') as mock_extract:
            mock_extract.return_value = {
                "format": "audio",
                "extracted_at": datetime.now().isoformat(),
                "tags": {"duration": 180.5, "fps": 48000},
            }
            result = metadata_handler.extract_metadata(str(mock_audio_file), "audio")
            assert result["format"] == "audio"
            assert "tags" in result
            mock_extract.assert_called_once_with(str(mock_audio_file))

    def test_extract_metadata_image(self, metadata_handler, mock_image_file):
        # Test image metadata extraction
        with patch.object(metadata_handler, 'extract_image_metadata') as mock_extract:
            mock_extract.return_value = {
                "format": "image",
                "extracted_at": datetime.now().isoformat(),
                "tags": {"width": 1920, "height": 1080},
            }
            result = metadata_handler.extract_metadata(str(mock_image_file), "image")
            assert result["format"] == "image"
            assert "tags" in result
            mock_extract.assert_called_once_with(str(mock_image_file))

    def test_extract_metadata_document(self, metadata_handler, mock_document_file):
        # Test document metadata extraction
        with patch.object(metadata_handler, 'extract_document_metadata') as mock_extract:
            mock_extract.return_value = {
                "format": "document",
                "extracted_at": datetime.now().isoformat(),
                "tags": {"pages": 10, "author": "Test Author"},
            }
            result = metadata_handler.extract_metadata(str(mock_document_file), "document")
            assert result["format"] == "document"
            assert "tags" in result
            mock_extract.assert_called_once_with(str(mock_document_file))

    def test_extract_metadata_unknown_type(self, metadata_handler, mock_audio_file):
        # Test extraction of unknown file type
        result = metadata_handler.extract_metadata(str(mock_audio_file), "unknown")
        assert result["format"] == "unknown"
        assert result["tags"] == {}


class TestMetadataStorage:
    def test_save_metadata(self, metadata_handler, temp_metadata_dir):
        # Test saving metadata to JSON file
        metadata_handler.set_metadata_dir(str(temp_metadata_dir))
        
        test_metadata = {
            "format": "audio",
            "extracted_at": datetime.now().isoformat(),
            "tags": {"title": "Test Song", "artist": "Test Artist"},
        }
        
        result = metadata_handler.save_metadata(
            "input.mp3",
            test_metadata,
            "output.wav"
        )
        
        assert result is not None
        assert os.path.exists(result)
        assert "output.metadata.json" in result

    def test_save_metadata_without_directory(self, metadata_handler):
        # Test saving metadata without setting directory
        test_metadata = {"format": "audio", "tags": {}}
        result = metadata_handler.save_metadata("input.mp3", test_metadata, "output.wav")
        assert result is None

    def test_load_metadata(self, metadata_handler, temp_metadata_dir):
        # Test loading metadata from JSON file
        metadata_handler.set_metadata_dir(str(temp_metadata_dir))
        
        test_metadata = {
            "format": "audio",
            "extracted_at": datetime.now().isoformat(),
            "tags": {"title": "Test", "duration": 120},
        }
        save_path = metadata_handler.save_metadata(
            "input.mp3",
            test_metadata,
            "output.wav"
        )
        loaded = metadata_handler.load_metadata(save_path)
        assert loaded["format"] == "audio"
        assert loaded["tags"]["title"] == "Test"
        assert loaded["tags"]["duration"] == 120

    def test_load_metadata_nonexistent(self, metadata_handler):
        # Test loading nonexistent metadata file
        result = metadata_handler.load_metadata("/nonexistent/path.json")
        assert result == {}


class TestCustomTagAddition:
    # Test adding custom tags to metadata
    def test_add_custom_tags(self, metadata_handler):
        # Test adding custom tags to metadata
        base_metadata = {
            "format": "audio",
            "tags": {"duration": 180},
        }
        custom_tags = {"project": "archive", "year": "2024"}
        result = metadata_handler.add_custom_tags(base_metadata, custom_tags)
        assert "custom_tags" in result
        assert result["custom_tags"]["project"] == "archive"
        assert result["custom_tags"]["year"] == "2024"

    def test_add_custom_tags_multiple_calls(self, metadata_handler):
        # Test that multiple custom tag additions merge properly
        metadata = {"format": "audio", "tags": {}}
        metadata = metadata_handler.add_custom_tags(metadata, {"tag1": "value1"})
        metadata = metadata_handler.add_custom_tags(metadata, {"tag2": "value2"})
        assert metadata["custom_tags"]["tag1"] == "value1"
        assert metadata["custom_tags"]["tag2"] == "value2"


class TestMetadataApplication:
    # Test applying metadata back to files

    def test_apply_metadata_to_unsupported_format(self, metadata_handler, tmp_path):
        # Test applying metadata to unsupported format
        unsupported_file = tmp_path / "output.txt"
        unsupported_file.touch()
        metadata = {
            "format": "document",
            "tags": {"title": "Test"},
        }
        result = metadata_handler.apply_metadata_to_file(str(unsupported_file), metadata)
        assert result is False

    def test_apply_metadata_nonexistent_file(self, metadata_handler):
        # Test applying metadata to nonexistent file
        metadata = {"format": "audio", "tags": {}}
        result = metadata_handler.apply_metadata_to_file(
            "/nonexistent/file.mp3",
            metadata
        )
        assert result is False

    def test_apply_metadata_to_audio_mock(self, metadata_handler, tmp_path):
        # Test applying ID3 tags to audio file (mocked)
        audio_file = tmp_path / "test.mp3"
        audio_file.touch()
        
        metadata = {
            "format": "audio",
            "tags": {
                "title": "Test Song",
                "artist": "Test Artist",
                "album": "Test Album",
            }
        }
        
        # Test that method handles the file without raising exception
        # Actual behavior depends on mutagen availability
        try:
            result = metadata_handler.apply_metadata_to_file(str(audio_file), metadata)
            # Should return boolean without raising
            assert isinstance(result, bool)
        except ImportError:
            # Acceptable if mutagen not installed
            pass


class TestMetadataStripping:
    def test_strip_metadata_nonexistent_file(self, metadata_handler):
        # Test stripping metadata from nonexistent file
        result = metadata_handler.strip_metadata("/nonexistent/file.mp3", "audio")
        assert result is False

    def test_strip_metadata_unsupported_type(self, metadata_handler, tmp_path):
        # Test stripping metadata from unsupported type
        doc_file = tmp_path / "document.txt"
        doc_file.touch()
        
        result = metadata_handler.strip_metadata(str(doc_file), "document")
        assert result is False


class TestIntegrationWithController:
    def test_controller_has_metadata_handler(self, controller_instance):
        # Test that controller initializes metadata handler
        assert hasattr(controller_instance, 'metadata_handler')
        assert isinstance(controller_instance.metadata_handler, MetadataHandler)

    def test_controller_metadata_flags_initialization(self, controller_instance):
        # Test that controller initializes metadata flags
        assert hasattr(controller_instance, 'preserve_meta')
        assert hasattr(controller_instance, 'custom_tags')
        assert hasattr(controller_instance, 'strip_meta')
        assert controller_instance.preserve_meta is False
        assert controller_instance.custom_tags == {}
        assert controller_instance.strip_meta is False

    def test_controller_handle_metadata_method(self, controller_instance):
        # Test that controller has metadata handling method
        assert hasattr(controller_instance, '_handle_metadata')
        assert callable(controller_instance._handle_metadata)


class TestMetadataHandlerEdgeCases:
    def test_parse_custom_tags_with_empty_strings(self, metadata_handler):
        # Test parsing with empty strings
        tags = ["key:", ":value", "valid:tag"]
        result = metadata_handler.parse_custom_tags(tags)
        # Should handle gracefully, may include empty values
        assert "valid" in result

    def test_metadata_extraction_with_corrupted_file(self, metadata_handler, tmp_path):
        # Test metadata extraction from corrupted file
        corrupted_file = tmp_path / "corrupted.mp3"
        corrupted_file.write_bytes(b"corrupted_data")
        # Should not raise exception, returns empty metadata
        result = metadata_handler.extract_metadata(str(corrupted_file), "audio")
        assert result["format"] == "audio"

    def test_metadata_handler_with_unicode_tags(self, metadata_handler):
        # Test handling of unicode characters in tags
        tags = ["title:日本語テスト", "artist:Künstler", "comment:Ñoño"]
        result = metadata_handler.parse_custom_tags(tags)
        assert result["title"] == "日本語テスト"
        assert result["artist"] == "Künstler"
        assert result["comment"] == "Ñoño"

    def test_save_and_load_metadata_with_special_chars(self, metadata_handler, temp_metadata_dir):
        # Test saving and loading metadata with special characters
        metadata_handler.set_metadata_dir(str(temp_metadata_dir))
        special_metadata = {
            "format": "audio",
            "tags": {
                "title": "日本語テスト",
                "artist": "Künstler",
                "special": "!@#$%^&*()",
            },
        }
        
        save_path = metadata_handler.save_metadata(
            "input.mp3",
            special_metadata,
            "output.wav"
        )
        
        loaded = metadata_handler.load_metadata(save_path)
        assert loaded["tags"]["title"] == "日本語テスト"
        assert loaded["tags"]["artist"] == "Künstler"


class TestMetadataHandlerFileOperations:
    def test_metadata_directory_permissions(self, metadata_handler, tmp_path):
        # Test that metadata directory has proper permissions
        metadata_dir = tmp_path / "metadata"
        metadata_handler.set_metadata_dir(str(metadata_dir))
        # Should be readable and writable
        assert os.access(str(metadata_dir), os.R_OK)
        assert os.access(str(metadata_dir), os.W_OK)

    def test_multiple_files_same_directory(self, metadata_handler, temp_metadata_dir):
        # Test saving metadata for multiple files in same directory
        metadata_handler.set_metadata_dir(str(temp_metadata_dir))
        files = [("input1.mp3", "output1.wav"), ("input2.mp3", "output2.wav")]
        for input_file, output_file in files:
            metadata = {
                "format": "audio",
                "tags": {"title": input_file},
            }
            metadata_handler.save_metadata(input_file, metadata, output_file)
        # Both files should be saved in .metadata subdirectory
        metadata_subdir = temp_metadata_dir / ".metadata"
        metadata_files = list(metadata_subdir.glob("*.metadata.json"))
        assert len(metadata_files) == 2

    def test_overwrite_existing_metadata(self, metadata_handler, temp_metadata_dir):
        # Test overwriting existing metadata file
        metadata_handler.set_metadata_dir(str(temp_metadata_dir))
        metadata1 = {"format": "audio", "tags": {"version": 1}}
        metadata2 = {"format": "audio", "tags": {"version": 2}}
        path1 = metadata_handler.save_metadata("input.mp3", metadata1, "output.wav")
        path2 = metadata_handler.save_metadata("input.mp3", metadata2, "output.wav")
        
        # Should be same path
        assert path1 == path2
        
        # Load and verify it's the new version
        loaded = metadata_handler.load_metadata(path2)
        assert loaded["tags"]["version"] == 2
