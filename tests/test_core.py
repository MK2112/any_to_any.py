import pytest
from utils.category import Category
from tests.test_fixtures import controller_instance, test_input_folder


def test_supported_formats(controller_instance):
    assert isinstance(controller_instance.supported_formats, list)
    assert len(controller_instance.supported_formats) > 0


def test_audio_bitrate(controller_instance):
    # Kind of nonsensical, I know, but it is a low-level structural test anyway
    assert controller_instance._audio_bitrate("mp3", "high") == "320k"
    assert controller_instance._audio_bitrate("flac", "medium") == "320k"
    assert controller_instance._audio_bitrate("ogg", "low") == "128k"
    assert controller_instance._audio_bitrate("mp3", "medium") == "192k"
    assert controller_instance._audio_bitrate("invalid_format", "medium") == "192k"


def test_get_file_paths_valid_input_files(controller_instance, tmp_path):
    movie_path = tmp_path / "test_movie.mp4"
    image_path = tmp_path / "test_image.jpg"
    movie_path.touch()
    image_path.touch()
    file_paths = controller_instance.file_handler.get_file_paths(
        input=str(tmp_path), supported_formats=controller_instance._supported_formats
    )

    assert isinstance(file_paths, dict)
    assert len(file_paths[Category.IMAGE]) == 1
    assert len(file_paths[Category.MOVIE]) == 1
    assert Category.IMAGE in file_paths
    assert Category.MOVIE in file_paths


def test_join_back_method(controller_instance, test_input_folder):
    file_path_set = ((str(test_input_folder) + "/"), "test_file", "mp4")
    assert controller_instance.file_handler.join_back(file_path_set) == str(
        test_input_folder / "test_file.mp4"
    )


def test_multi_input_no_output_does_not_crash(controller_instance, tmp_path):
    d1 = tmp_path / "dir1"
    d2 = tmp_path / "dir2"
    d1.mkdir()
    d2.mkdir()
    (d1 / "a.mp3").write_bytes(b"\x00" * 128)
    (d2 / "b.mp3").write_bytes(b"\x00" * 128)

    with pytest.raises(ValueError):
        controller_instance.run(
            input_path_args=[str(d1), str(d2)],
            format="wav",
            output=None,
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
