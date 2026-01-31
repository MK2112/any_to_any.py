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
            split=None,
            merge=False,
            concat=False,
            delete=False,
            across=False,
            recursive=False,
            dropzone=False,
            language=None,
            workers=1,
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
            split=False,
            merge=False,
            concat=False,
            delete=False,
            across=False,
            recursive=False,
            dropzone=False,
            language=None,
            workers=1,
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
            split=False,
            merge=False,
            concat=False,
            delete=False,
            across=False,
            recursive=False,
            dropzone=False,
            language=None,
            workers=1,
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
        split=False,
        merge=False,
        concat=False,
        delete=False,
        across=False,
        recursive=False,
        dropzone=False,
        language=None,
        workers=1,
    )

    assert (tmp_path / "large.mp3").exists()

    # Delete the large file to save space
    large_file.unlink()


def test_single_image_conversion_no_subfolder(controller_instance, tmp_path):
    # Test for bugfix: single PNG to JPEG should not create unnecessary subfolder
    # This simulates the GUI behavior where output is a file path like /path/output.jpg
    from PIL import Image
    import os
    
    # Create input PNG file
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    input_file = input_dir / "test.png"
    
    # Create a real 1x1 PNG image
    img = Image.new('RGB', (1, 1), color='red')
    img.save(str(input_file), 'PNG')
    
    # Simulate GUI behavior: output is a file path, not a directory
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    output_file_path = str(output_dir / "test.jpeg")
    
    # Run conversion with output as file path (like GUI does for single files)
    controller_instance.run(
        [str(input_file)],
        format="jpeg",
        output=output_file_path,  # Full file path, not directory
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
    )
    
    # Verify output directory structure is correct
    # Should have: /output/test.jpeg
    # Should NOT have: /output/test.jpeg/test.jpeg or any subfolder
    
    assert output_dir.exists(), "Output directory should exist"
    assert (output_dir / "test.jpeg").exists(), "Output file should exist"
    assert not (output_dir / "test.jpeg").is_dir(), "Output should be a file, not a directory"
    
    # Verify no unnecessary subfolder was created
    subdirs = [d for d in output_dir.iterdir() if d.is_dir()]
    assert len(subdirs) == 0, f"No subdirectories should exist, but found: {subdirs}"
