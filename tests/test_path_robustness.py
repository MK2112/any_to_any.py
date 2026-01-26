import os
import pytest
from pathlib import Path
from core.controller import Controller
from utils.category import Category


from unittest.mock import MagicMock


@pytest.fixture
def controller():
    c = Controller()
    # Avoiding real ffmpeg calls on empty files
    c.audio_converter.to_audio = MagicMock()
    c.movie_converter.to_movie = MagicMock()
    c.movie_converter.to_codec = MagicMock()
    return c


def test_path_with_spaces_reconstruction(controller, tmp_path):
    # Testing logic in Controller.run; reconstructs paths from list of args
    # logic treats first arg as starting point.
    # Subsequent args are joined to previous if concatenated path exists.
    spaced_dir_name = "folder with spaces"
    spaced_dir = tmp_path / spaced_dir_name
    spaced_dir.mkdir()
    (spaced_dir / "test.mp3").touch()

    # Absolute path to ensure os.path.exists works as expected
    parts = str(spaced_dir).split()  # e.g. ["/tmp/folder", "with", "spaces"]
    # input_paths = [parts[0]] -> "/tmp/folder" (doesn't exist)
    # arg = "with" -> joined = "/tmp/folder with" (doesn't exist)
    # logic goes to 'else' -> input_paths[-1] = "/tmp/folder with"
    # next arg = "spaces" -> joined = "/tmp/folder with spaces" (EXISTS!)
    # logic goes to 'elif os.path.exists(joined) and not os.path.exists(previous)'
    # where previous is "/tmp/folder with"
    out_dir = tmp_path / "out"
    controller.run(
        input_path_args=parts,
        format="wav",
        output=str(out_dir),
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

    # Directory with spaces should be correctly reconstructed
    assert controller.audio_converter.to_audio.called
    assert os.path.exists(str(out_dir))


def test_recursive_path_scanning(controller, tmp_path):
    deep_dir = tmp_path / "a" / "b" / "c"
    deep_dir.mkdir(parents=True)
    (deep_dir / "file1.mp3").touch()
    (tmp_path / "file2.wav").touch()
    file_paths = {cat: [] for cat in controller._supported_formats}
    # Recursive logic used in Controller.run
    for root, _, files in os.walk(str(tmp_path)):
        file_paths = controller.file_handler.get_file_paths(
            root, file_paths, controller._supported_formats
        )
    assert len(file_paths[Category.AUDIO]) == 2
    filenames = [f[1] for f in file_paths[Category.AUDIO]]
    assert "file1" in filenames
    assert "file2" in filenames


def test_special_characters_in_paths(controller, tmp_path):
    # Handling of paths with special characters
    special_name = "fileäöü!@#$%^&()_+.mp3"
    special_file = tmp_path / special_name
    special_file.touch()
    file_paths = controller.file_handler.get_file_paths(
        str(tmp_path), {}, controller._supported_formats
    )
    assert len(file_paths[Category.AUDIO]) == 1
    assert file_paths[Category.AUDIO][0][1] == "fileäöü!@#$%^&()_+"
    assert file_paths[Category.AUDIO][0][2] == "mp3"


def test_output_directory_creation(controller, tmp_path):
    # Controller creates the output directory if it doesn't exist
    out_dir = tmp_path / "new_output_dir"
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "test.mp3").touch()
    assert not out_dir.exists()
    controller.run(
        input_path_args=[str(input_dir)],
        format="wav",
        output=str(out_dir),
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

    assert out_dir.exists()
    assert out_dir.is_dir()


def test_file_handler_dissection(controller):
    # Assert FileHandler's ability to split paths correctly
    file_info = ("/tmp/test/", "file.some.ext", "mp3")
    joined = controller.file_handler.join_back(file_info)
    assert joined.endswith("file.some.ext.mp3")
