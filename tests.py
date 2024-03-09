import PIL
import pytest
from unittest.mock import patch
from any_to_any import AnyToAny

@pytest.fixture
def test_input_folder(tmp_path):
    test_folder = tmp_path / "test_input"
    test_folder.mkdir()
    return test_folder

@pytest.fixture
def test_output_folder(tmp_path):
    test_folder = tmp_path / "test_output"
    test_folder.mkdir()
    return test_folder

@pytest.fixture
def any_to_any_instance():
    return AnyToAny()

def test_supported_formats(any_to_any_instance):
    assert isinstance(any_to_any_instance.supported_formats, list)
    assert len(any_to_any_instance.supported_formats) > 0

def test_audio_bitrate(any_to_any_instance):
    assert any_to_any_instance._audio_bitrate('mp3', 'high') == '320k'
    assert any_to_any_instance._audio_bitrate('flac', 'medium') == '320k'
    assert any_to_any_instance._audio_bitrate('ogg', 'low') == '128k'
    assert any_to_any_instance._audio_bitrate('mp3', 'medium') == '192k'
    assert any_to_any_instance._audio_bitrate('invalid_format', 'medium') == '192k'

def test_get_file_paths_valid_input_files(any_to_any_instance, tmp_path):
    movie_path = tmp_path / "test_movie.mp4"
    image_path = tmp_path / "test_image.jpg"
    movie_path.touch()
    image_path.touch()

    with patch("builtins.print") as mock_print:
        file_paths = any_to_any_instance._get_file_paths(input=str(tmp_path))

    assert 'image' in file_paths
    assert 'movie' in file_paths
    assert len(file_paths['image']) == 1
    assert len(file_paths['movie']) == 1

def test_join_back_method(any_to_any_instance, test_input_folder):
    file_path_set = ((str(test_input_folder) + "/"), 'test_file', 'mp4')
    print(any_to_any_instance._join_back(file_path_set))
    print(str(test_input_folder / 'test_file.mp4'))
    assert any_to_any_instance._join_back(file_path_set) == str(test_input_folder / 'test_file.mp4')

def test_merging_method(any_to_any_instance, test_input_folder, test_output_folder):
    # Test merging movies with audio
    movie_path = test_input_folder / "movie_name.mp4"
    audio_path = test_input_folder / "movie_name.mp3"
    movie_path.touch()
    audio_path.touch()
    
    with pytest.raises(OSError):
        any_to_any_instance.merging({'movie': [((str(movie_path.parent) + "/"), 'movie_name', 'mp4')], 'audio': [((str(audio_path.parent) + "/"), 'movie_name', 'mp3')]})

def test_concatenating_method(any_to_any_instance, test_input_folder, test_output_folder):
    # Test concatenating movies
    movie1_path = test_input_folder / "movie1.mp4"
    movie2_path = test_input_folder / "movie2.mp4"
    movie1_path.touch()
    movie2_path.touch()

    with pytest.raises(OSError):
        any_to_any_instance.concatenating({'audio': [], 'movie': [((str(movie1_path.parent) + "/"), 'movie1', 'mp4'), ((str(movie2_path.parent) + "/"), 'movie2', 'mp4')]})

def test_run_method(any_to_any_instance, test_input_folder, test_output_folder):
    # Test with invalid input format
    with pytest.raises(FileNotFoundError):
        any_to_any_instance.run(inputs=['-invalid'], format='mp4', output=str(test_output_folder), framerate=None, quality=None, merge=False, concat=False, delete=False)

    # Test with valid input
    image_path = test_input_folder / "test_image.jpg"
    image_path.touch()

    with pytest.raises(PIL.UnidentifiedImageError):
        any_to_any_instance.run(inputs=[str(test_input_folder)], format='png', output=str(test_output_folder), framerate=None, quality=None, merge=False, concat=False, delete=False)

def test_get_file_paths_invalid_directory(any_to_any_instance):
    with pytest.raises(FileNotFoundError):
        any_to_any_instance._get_file_paths(input="nonexistent_directory")

def test_to_audio_invalid_format(any_to_any_instance, tmp_path):
    invalid_file = tmp_path / "invalid_file.mp3"
    invalid_file.touch()

    with pytest.raises(OSError):
        any_to_any_instance.to_audio(file_paths={'audio': [((str(tmp_path) + "/"), 'invalid_file', 'mp3')]}, format='invalid_format', codec='libmp3lame')

def test_blank_start_no_files_in_cli_output(any_to_any_instance, capsys):
    with pytest.raises(SystemExit):
        any_to_any_instance.run(inputs=None, format=None, output=None, framerate=None, quality=None, merge=False, concat=False, delete=False)
    captured = capsys.readouterr()
    assert "No convertible media files" in captured.out