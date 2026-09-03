import os
import shutil
import subprocess
import wave
import pytest

from datetime import datetime
from unittest import mock
from unittest.mock import Mock, patch, MagicMock
from core.controller import Controller
from core.utils.metadata_handler import MetadataHandler


AUDIO_CONTAINERS = ["mp3", "wav", "flac", "ogg", "m4a", "wma"]
_AUDIO_CODECS = {
    "mp3": ["libmp3lame"],
    "flac": ["flac"],
    "m4a": ["aac"],
    "ogg": ["libvorbis", "vorbis"],
    "wma": ["wmav2"],
}

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not available"
)


def _make_audio_file(directory, file_ext, name="tone"):
    # Generate a small real audio file of the requested container with ffmpeg
    src = directory / "source.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 800)

    out = directory / f"{name}.{file_ext}"
    if file_ext == "wav":
        out.write_bytes(src.read_bytes())
        return out

    for codec in _AUDIO_CODECS[file_ext]:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(src),
                "-c:a",
                codec,
                str(out),
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            return out
    pytest.skip(f"ffmpeg cannot encode {file_ext}")


def _read_applied_tags(file_path, file_ext):
    common_frames = {"title": "TIT2", "artist": "TPE1", "album": "TALB", "date": "TDRC"}
    if file_ext in ("mp3", "wav"):
        if file_ext == "mp3":
            from mutagen.mp3 import MP3 as Loader
        else:
            from mutagen.wave import WAVE as Loader
        id3 = Loader(file_path).tags
        out = {}
        for name, frame_id in common_frames.items():
            frame = id3.get(frame_id)
            if frame:
                out[name] = str(frame.text[0])
        for frame in id3.getall("TXXX"):
            out[frame.desc] = str(frame.text[0])
        return out

    if file_ext in ("flac", "ogg"):
        if file_ext == "flac":
            from mutagen.flac import FLAC as Loader
        else:
            from mutagen.oggvorbis import OggVorbis as Loader
        tags = Loader(file_path)
        out = {}
        for key in tags.keys():
            values = tags[key]
            out[key.lower()] = str(values[0] if isinstance(values, list) else values)
        return out

    if file_ext == "m4a":
        from mutagen.mp4 import MP4

        common_atoms = {
            "title": "\xa9nam",
            "artist": "\xa9ART",
            "album": "\xa9alb",
            "date": "\xa9day",
        }
        mp4 = MP4(file_path)
        out = {}
        for name, atom in common_atoms.items():
            if atom in mp4:
                out[name] = str(mp4[atom][0])
        for key, values in mp4.items():
            if key.startswith("----:"):
                name = key.rsplit(":", 1)[-1]
                payload = values[0]
                out[name] = (
                    bytes(payload).decode("utf-8")
                    if isinstance(payload, bytes)
                    else str(payload)
                )
        return out

    from mutagen.asf import ASF

    common_attrs = {
        "title": "Title",
        "artist": "Author",
        "album": "WM/AlbumTitle",
        "date": "WM/Year",
    }
    asf = ASF(file_path)
    out = {}
    for name, attr in common_attrs.items():
        if attr in asf:
            out[name] = str(asf[attr][0])
    for key in asf.keys():
        if key not in common_attrs.values():
            out[key] = str(asf[key][0])
    return out


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
        with patch.object(metadata_handler, "extract_audio_metadata") as mock_extract:
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
        with patch.object(metadata_handler, "extract_image_metadata") as mock_extract:
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
        with patch.object(
            metadata_handler, "extract_document_metadata"
        ) as mock_extract:
            mock_extract.return_value = {
                "format": "document",
                "extracted_at": datetime.now().isoformat(),
                "tags": {"pages": 10, "author": "Test Author"},
            }
            result = metadata_handler.extract_metadata(
                str(mock_document_file), "document"
            )
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
            "input.mp3", test_metadata, "output.wav"
        )

        assert result is not None
        assert os.path.exists(result)
        assert "output.metadata.json" in result

    def test_save_metadata_without_directory(self, metadata_handler):
        # Test saving metadata without setting directory
        test_metadata = {"format": "audio", "tags": {}}
        result = metadata_handler.save_metadata(
            "input.mp3", test_metadata, "output.wav"
        )
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
            "input.mp3", test_metadata, "output.wav"
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
        result = metadata_handler.apply_metadata_to_file(
            str(unsupported_file), metadata
        )
        assert result is False

    def test_apply_metadata_nonexistent_file(self, metadata_handler):
        # Test applying metadata to nonexistent file
        metadata = {"format": "audio", "tags": {}}
        result = metadata_handler.apply_metadata_to_file(
            "/nonexistent/file.mp3", metadata
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
            },
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

    @requires_ffmpeg
    @pytest.mark.parametrize("file_ext", AUDIO_CONTAINERS)
    def test_apply_metadata_writes_native_backend_tags(
        self, metadata_handler, tmp_path, file_ext
    ):
        # Common tags must land on each container under its native backend
        # (ID3 frames, Vorbis comments, MP4 atoms, ASF attributes) and custom
        # tags must be written as well.
        audio_file = _make_audio_file(tmp_path, file_ext, "tagged")
        metadata = {
            "format": "audio",
            "tags": {
                "title": "Night Train",
                "artist": "Django Reinhardt",
                "album": "Hot Club de France",
                "date": "1934",
            },
            "custom_tags": {"project": "archive-42"},
        }

        result = metadata_handler.apply_metadata_to_file(str(audio_file), metadata)
        assert result is True

        written = _read_applied_tags(str(audio_file), file_ext)
        expected = {
            "title": "Night Train",
            "artist": "Django Reinhardt",
            "album": "Hot Club de France",
            "date": "1934",
            "project": "archive-42",
        }
        for name, value in expected.items():
            assert written.get(name) == value, (file_ext, name, written)

    @requires_ffmpeg
    @pytest.mark.parametrize("file_ext", AUDIO_CONTAINERS)
    def test_apply_metadata_skips_technical_tag_values(
        self, metadata_handler, tmp_path, file_ext
    ):
        # Technical extraction values (duration/fps/nchannels) are not tags and
        # must not be written to the file under any name.
        audio_file = _make_audio_file(tmp_path, file_ext, "tech")
        metadata = {
            "format": "audio",
            "tags": {
                "title": "Only Title",
                "duration": 180.5,
                "fps": 48000,
                "nchannels": 2,
            },
        }

        result = metadata_handler.apply_metadata_to_file(str(audio_file), metadata)
        assert result is True

        written = _read_applied_tags(str(audio_file), file_ext)
        assert written.get("title") == "Only Title"
        assert "duration" not in written
        assert "fps" not in written
        assert "nchannels" not in written

    @requires_ffmpeg
    def test_apply_mp3_tags_readable_through_easyid3(self, metadata_handler, tmp_path):
        # Regression: mp3 tags were previously written as raw ID3 frame ids
        # through EasyID3, which rejects them, so nothing was ever applied.
        from mutagen.easyid3 import EasyID3

        audio_file = _make_audio_file(tmp_path, "mp3", "easy")
        metadata = {
            "format": "audio",
            "tags": {"title": "Petit Fleur", "artist": "Sidney Bechet"},
        }

        result = metadata_handler.apply_metadata_to_file(str(audio_file), metadata)
        assert result is True

        easy = EasyID3(str(audio_file))
        assert easy["title"] == ["Petit Fleur"]
        assert easy["artist"] == ["Sidney Bechet"]

    @requires_ffmpeg
    def test_apply_metadata_without_tags_is_noop(self, metadata_handler, tmp_path):
        # No taggable content means the file must be left untouched
        audio_file = _make_audio_file(tmp_path, "flac", "plain")
        before = audio_file.read_bytes()
        metadata = {"format": "audio", "tags": {"duration": 0.1}, "custom_tags": {}}

        result = metadata_handler.apply_metadata_to_file(str(audio_file), metadata)
        assert result is False
        assert audio_file.read_bytes() == before

    @requires_ffmpeg
    def test_apply_custom_tags_only(self, metadata_handler, tmp_path):
        # A user-provided tag alone (no extracted tags) must reach the file
        audio_file = _make_audio_file(tmp_path, "ogg", "custom_only")
        metadata = {
            "format": "audio",
            "tags": {},
            "custom_tags": {"project": "archive-42"},
        }

        result = metadata_handler.apply_metadata_to_file(str(audio_file), metadata)
        assert result is True

        written = _read_applied_tags(str(audio_file), "ogg")
        assert written.get("project") == "archive-42"


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
        assert hasattr(controller_instance, "metadata_handler")
        assert isinstance(controller_instance.metadata_handler, MetadataHandler)

    def test_controller_metadata_flags_initialization(self, controller_instance):
        # Test that controller initializes metadata flags
        assert hasattr(controller_instance, "preserve_meta")
        assert hasattr(controller_instance, "custom_tags")
        assert hasattr(controller_instance, "strip_meta")
        assert controller_instance.preserve_meta is False
        assert controller_instance.custom_tags == {}
        assert controller_instance.strip_meta is False

    def test_controller_handle_metadata_method(self, controller_instance):
        # Test that controller has metadata handling method
        assert hasattr(controller_instance, "_handle_metadata")
        assert callable(controller_instance._handle_metadata)

    def test_handle_metadata_returns_early_when_no_flags(
        self, controller_instance, tmp_path
    ):
        controller_instance.preserve_meta = False
        controller_instance.custom_tags = {}
        controller_instance.strip_meta = False
        result = controller_instance._handle_metadata(
            str(tmp_path / "input.mp3"),
            str(tmp_path / "output.mp3"),
            "audio",
        )
        assert result is None

    def test_handle_metadata_strip_meta_calls_handler(
        self, controller_instance, tmp_path
    ):
        controller_instance.preserve_meta = False
        controller_instance.custom_tags = {}
        controller_instance.strip_meta = True
        with mock.patch.object(
            controller_instance.metadata_handler, "strip_metadata"
        ) as mock_strip:
            controller_instance._handle_metadata(
                str(tmp_path / "input.mp3"),
                str(tmp_path / "output.mp3"),
                "audio",
            )
            mock_strip.assert_called_once_with(str(tmp_path / "output.mp3"), "audio")

    def test_handle_metadata_preserve_calls_extract_and_save(
        self, controller_instance, tmp_path
    ):
        controller_instance.preserve_meta = True
        controller_instance.strip_meta = False
        controller_instance.custom_tags = {}
        with (
            mock.patch.object(
                controller_instance.metadata_handler, "extract_metadata"
            ) as mock_extract,
            mock.patch.object(
                controller_instance.metadata_handler, "save_metadata"
            ) as mock_save,
            mock.patch.object(
                controller_instance.metadata_handler, "apply_metadata_to_file"
            ) as mock_apply,
        ):
            mock_extract.return_value = {"format": "audio", "tags": {}}
            controller_instance._handle_metadata(
                str(tmp_path / "input.mp3"),
                str(tmp_path / "output.mp3"),
                "audio",
            )
            mock_extract.assert_called_once_with(str(tmp_path / "input.mp3"), "audio")
            mock_save.assert_called_once()
            mock_apply.assert_called_once()


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

    def test_save_and_load_metadata_with_special_chars(
        self, metadata_handler, temp_metadata_dir
    ):
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
            "input.mp3", special_metadata, "output.wav"
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


class TestImageMetadataStripping:
    # Stripping metadata must keep file format and data intact
    @staticmethod
    def _with_exif():
        from PIL import Image

        exif = Image.Exif()
        exif[0x010F] = b"secret make"  # Make tag
        return exif

    @staticmethod
    def _inject_gif_metadata_blocks(data: bytes) -> bytes:
        pos = data.index(b"\x2c")
        comment = b"\x21\xfe" + bytes([5]) + b"hello" + b"\x00"
        xmp = b"\x21\xff" + bytes([11]) + b"XMP DataXMP" + b"\x00"
        return data[:pos] + comment + xmp + data[pos:]

    def test_strip_png_keeps_container_and_alpha(self, metadata_handler, tmp_path):
        # A .png must remain a real PNG after removal of metadata
        from PIL import Image

        png_file = tmp_path / "photo.png"
        Image.new("RGBA", (6, 6), (10, 20, 30, 100)).save(
            png_file, exif=self._with_exif()
        )

        result = metadata_handler.strip_metadata(str(png_file), "image")
        assert result is True

        with Image.open(png_file) as stripped:
            assert stripped.format == "PNG"
            assert stripped.mode == "RGBA"
            assert "exif" not in stripped.info
            assert stripped.getpixel((0, 0)) == (10, 20, 30, 100)

    def test_strip_jpeg_drops_exif(self, metadata_handler, tmp_path):
        from PIL import Image

        jpg_file = tmp_path / "photo.jpg"
        Image.new("RGB", (6, 6), "red").save(jpg_file, "JPEG", exif=self._with_exif())

        result = metadata_handler.strip_metadata(str(jpg_file), "image")
        assert result is True

        with Image.open(jpg_file) as stripped:
            assert stripped.format == "JPEG"
            assert "exif" not in stripped.info

    def test_strip_webp_preserves_pixels_and_alpha(self, metadata_handler, tmp_path):
        from PIL import Image

        webp_file = tmp_path / "photo.webp"
        Image.new("RGBA", (5, 5), (1, 2, 3, 200)).save(webp_file, lossless=True)

        result = metadata_handler.strip_metadata(str(webp_file), "image")
        assert result is True

        with Image.open(webp_file) as stripped:
            assert stripped.format == "WEBP"
            assert stripped.mode == "RGBA"
            assert stripped.getpixel((0, 0)) == (1, 2, 3, 200)

    def test_strip_animated_gif_removes_metadata_only(self, metadata_handler, tmp_path):
        # Stripping an animated GIF removes comments/XMP without affecting data or timing
        from PIL import Image

        gif_file = tmp_path / "anim.gif"
        gif_orig = tmp_path / "anim_orig.gif"
        frames = []
        frame0 = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
        for x in range(4, 8):
            for y in range(4, 8):
                frame0.putpixel((x, y), (255, 0, 0, 255))
        frames.append(frame0)
        frames.append(Image.new("RGBA", (12, 12), (0, 0, 255, 255)))
        frame2 = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
        for x in range(2, 5):
            for y in range(2, 5):
                frame2.putpixel((x, y), (0, 255, 0, 255))
        frames.append(frame2)
        frames[0].save(
            gif_orig,
            save_all=True,
            append_images=frames[1:],
            duration=[100, 200, 300],
            loop=0,
            disposal=[1, 2, 1],
            transparency=0,
        )
        original = gif_orig.read_bytes()
        gif_file.write_bytes(self._inject_gif_metadata_blocks(original))
        result = metadata_handler.strip_metadata(str(gif_file), "image")
        assert result is True
        assert gif_file.read_bytes() == original

        from PIL import ImageSequence

        with Image.open(gif_file) as stripped:
            assert stripped.n_frames == 3
            durations = [
                frame.info.get("duration") for frame in ImageSequence.Iterator(stripped)
            ]
            assert durations == [100, 200, 300]

    def test_strip_gif_without_metadata_leaves_file_untouched(
        self, metadata_handler, tmp_path
    ):
        from PIL import Image

        gif_file = tmp_path / "still.gif"
        Image.new("RGB", (4, 4), "blue").save(gif_file)
        before = gif_file.read_bytes()
        result = metadata_handler.strip_metadata(str(gif_file), "image")
        assert result is True
        assert gif_file.read_bytes() == before

    def test_strip_corrupt_image_fails_without_overwriting(
        self, metadata_handler, tmp_path
    ):
        png_file = tmp_path / "broken.png"
        png_file.write_bytes(b"not really a png")
        before = png_file.read_bytes()
        result = metadata_handler.strip_metadata(str(png_file), "image")
        assert result is False
        assert png_file.read_bytes() == before

    def test_strip_unknown_image_extension_fails_cleanly(
        self, metadata_handler, tmp_path
    ):
        odd_file = tmp_path / "photo.xyz"
        odd_file.write_bytes(b"whatever")
        before = odd_file.read_bytes()
        result = metadata_handler.strip_metadata(str(odd_file), "image")
        assert result is False
        assert odd_file.read_bytes() == before
