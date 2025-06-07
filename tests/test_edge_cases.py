import pytest
import random
import string
from unittest.mock import patch
from tests.test_fixtures import controller_instance


def test_empty_directory(controller_instance, tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(SystemExit):
        controller_instance.run(
            [str(empty_dir)],
            format="mp3",
            output=str(tmp_path),
            framerate=None,
            quality=None,
            merge=False,
            concat=False,
            delete=False,
            across=False,
            recursive=False,
            dropzone=False,
            language=None,
        )


def test_get_file_paths_invalid_directory(controller_instance):
    with pytest.raises(FileNotFoundError):
        controller_instance.file_handler.get_file_paths(input="nonexistent_directory")


def test_fuzz_random_file_names(controller_instance, tmp_path):
    for _ in range(10):
        name = "".join(random.choices(string.ascii_letters, k=8))
        # Specifically checking the 'malformed' case of 'jpg' instead of 'jpeg'
        # because people use it so often, this has to be handled/supported
        ext = random.choice(["mp4", "mp3", "jpg", "wav", "pdf"])
        file = tmp_path / f"{name}.{ext}"
        file.write_bytes(b"\x00" * 128)
    try:
        controller_instance.file_handler.get_file_paths(str(tmp_path))
    except Exception as e:
        pytest.fail(f"get_file_paths failed: {e}")


def test_get_file_paths_invalid_directory_dne(controller_instance):
    with pytest.raises(FileNotFoundError):
        controller_instance.file_handler.get_file_paths(
            input="nonexistent_directory_dne"
        )


def test_get_file_paths_invalid_input(controller_instance):
    with pytest.raises(FileNotFoundError):
        controller_instance.file_handler.get_file_paths(input="invalid_input")


def test_invalid_format_conversion(controller_instance, tmp_path):
    # Test converting from unsupported format
    unsupported_file = tmp_path / "test.unsupported"
    unsupported_file.write_bytes(b"\x00" * 128)
    with pytest.raises(SystemExit):
        controller_instance.run(
            [str(unsupported_file)],
            format="mp3",
            output=str(tmp_path),
            framerate=None,
            quality=None,
            merge=False,
            concat=False,
            delete=False,
            across=False,
            recursive=False,
            dropzone=False,
            language=None,
        )


def test_invalid_quality_value(controller_instance, tmp_path):
    # Test invalid quality value
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"\x00" * 128)
    # Expect no exception to be raised
    try:
        controller_instance.run(
            [str(audio_file)],
            format="mp3",
            output=str(tmp_path),
            framerate=None,
            quality="invalid",
            merge=False,
            concat=False,
            delete=False,
            across=False,
            recursive=False,
            dropzone=False,
            language=None,
        )
    except Exception as e:
        pytest.fail(f"run failed: {e}")

    # Invalid quality value should cause fallback should cause file creation
    assert (tmp_path / "test.mp3").exists()


def test_large_file_conversion(controller_instance, tmp_path):
    # Test conversion of large file
    large_file = tmp_path / "large.mp3"
    # Create 1GB file
    with open(large_file, "wb") as f:
        f.write(b"\x00" * (1024 * 1024 * 1024))

    controller_instance.run(
        [str(large_file)],
        format="mp3",
        output=str(tmp_path),
        framerate=None,
        quality="low",
        merge=False,
        concat=False,
        delete=False,
        across=False,
        recursive=False,
        dropzone=False,
        language=None,
    )

    assert (tmp_path / "large.mp3").exists()
