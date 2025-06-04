import pytest
from utils.category import Category
from tests.test_fixtures import converter_instance, test_input_folder, test_output_folder

def test_merging_method(converter_instance, test_input_folder, test_output_folder):
    movie_path = test_input_folder / "movie_name.mp4"
    audio_path = test_input_folder / "movie_name.mp3"
    movie_path.touch()
    audio_path.touch()
    with pytest.raises(OSError):
        converter_instance.merge({
            Category.MOVIE: [((str(movie_path.parent) + "/"), 'movie_name', 'mp4')],
            Category.AUDIO: [((str(audio_path.parent) + "/"), 'movie_name', 'mp3')]
        })

def test_concatenating_method(converter_instance, test_input_folder, test_output_folder):
    movie1_path = test_input_folder / "movie1.mp4"
    movie2_path = test_input_folder / "movie2.mp4"
    movie1_path.touch()
    movie2_path.touch()
    with pytest.raises(OSError):
        converter_instance.concat({
            Category.AUDIO: [],
            Category.MOVIE: [((str(movie1_path.parent) + "/"), 'movie1', 'mp4'), ((str(movie2_path.parent) + "/"), 'movie2', 'mp4')]
        }, format="mp4")
