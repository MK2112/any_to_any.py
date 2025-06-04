import pytest
from utils.category import Category
from tests.test_fixtures import converter_instance, test_input_folder

def test_supported_formats(converter_instance):
    assert isinstance(converter_instance.supported_formats, list)
    assert len(converter_instance.supported_formats) > 0

def test_audio_bitrate(converter_instance):
    # Kind of nonsensical, I know, but it is a low-level structural test anyway
    assert converter_instance._audio_bitrate('mp3', 'high') == '320k'
    assert converter_instance._audio_bitrate('flac', 'medium') == '320k'
    assert converter_instance._audio_bitrate('ogg', 'low') == '128k'
    assert converter_instance._audio_bitrate('mp3', 'medium') == '192k'
    assert converter_instance._audio_bitrate('invalid_format', 'medium') == '192k'

def test_get_file_paths_valid_input_files(converter_instance, tmp_path):
    movie_path = tmp_path / "test_movie.mp4"
    image_path = tmp_path / "test_image.jpg"
    movie_path.touch()
    image_path.touch()
    file_paths = converter_instance._get_file_paths(input=str(tmp_path))
    assert Category.IMAGE in file_paths
    assert Category.MOVIE in file_paths
    assert len(file_paths[Category.IMAGE]) == 1
    assert len(file_paths[Category.MOVIE]) == 1

def test_join_back_method(converter_instance, test_input_folder):
    file_path_set = ((str(test_input_folder) + "/"), 'test_file', 'mp4')
    assert converter_instance._join_back(file_path_set) == str(test_input_folder / 'test_file.mp4')
