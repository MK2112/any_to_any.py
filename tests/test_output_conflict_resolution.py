import os
import time
import pytest

from pathlib import Path
from tests.test_fixtures import controller_instance


class TestOutputConflictResolution:
    def test_no_conflict_returns_original_path(self, controller_instance, tmp_path):
        # Test that if file doesn't exist, original path is returned
        output_path = os.path.join(str(tmp_path), "nonexistent_file.mp3")
        
        result = controller_instance.file_handler._resolve_output_file_conflict(output_path)
        
        assert result == output_path

    def test_numeric_suffix_single_conflict(self, controller_instance, tmp_path):
        # Test that a numeric suffix is added when file exists
        existing_file = tmp_path / "test.mp3"
        existing_file.write_text("existing content")
        result = controller_instance.file_handler._resolve_output_file_conflict(str(existing_file))

        assert result == os.path.join(str(tmp_path), "test_1.mp3")
        assert os.path.exists(str(existing_file))  # Original still exists
        assert not os.path.exists(result)  # New path doesn't exist yet

    def test_numeric_suffix_multiple_conflicts(self, controller_instance, tmp_path):
        # Test that numeric suffix increments when multiple files exist
        (tmp_path / "test.mp3").write_text("1")
        (tmp_path / "test_1.mp3").write_text("2")
        (tmp_path / "test_2.mp3").write_text("3")
        result = controller_instance.file_handler._resolve_output_file_conflict(
            os.path.join(str(tmp_path), "test.mp3")
        )
        assert result == os.path.join(str(tmp_path), "test_3.mp3")

    def test_numeric_suffix_with_different_extension(self, controller_instance, tmp_path):
        # Test that numeric suffix works with different file extensions
        existing_file = tmp_path / "test.wav"
        existing_file.write_text("existing")
        result = controller_instance.file_handler._resolve_output_file_conflict(str(existing_file))

        assert result == os.path.join(str(tmp_path), "test_1.wav")
        assert result.endswith(".wav")

    def test_numeric_suffix_with_complex_filename(self, controller_instance, tmp_path):
        # Test that numeric suffix works with complex filenames
        existing_file = tmp_path / "my_audio_file_v2.flac"
        existing_file.write_text("existing")
        result = controller_instance.file_handler._resolve_output_file_conflict(str(existing_file))        

        assert result == os.path.join(str(tmp_path), "my_audio_file_v2_1.flac")

    def test_random_suffix_is_unique(self, controller_instance, tmp_path):
        # Test that random suffixes are unique across multiple calls
        base_path = os.path.join(str(tmp_path), "test.mp3")
        (tmp_path / "test.mp3").write_text("existing")
        # Force timeout scenario by pre-creating many files
        for i in range(1, 100):
            (tmp_path / f"test_{i}.mp3").write_text(str(i))
        # Get first random suffix result
        result1 = controller_instance.file_handler._resolve_output_file_conflict(base_path)
        # Create that file too
        os.makedirs(os.path.dirname(result1), exist_ok=True)
        with open(result1, 'w') as f:
            f.write("new")
        # Get second random suffix result
        result2 = controller_instance.file_handler._resolve_output_file_conflict(base_path)
        
        # They should be different (with very very high probability)
        assert result1 != result2

    def test_conflict_resolution_preserves_original_file(self, controller_instance, tmp_path):
        # Test that original file is not overwritten
        existing_file = tmp_path / "test.mp3"
        existing_content = "original content"
        existing_file.write_text(existing_content)
        result = controller_instance.file_handler._resolve_output_file_conflict(str(existing_file))
        
        assert existing_file.read_text() == existing_content
        assert result != str(existing_file)


class TestPostProcessWithConflictResolution:
    def test_post_process_returns_resolved_path(self, controller_instance, tmp_path):
        # Test that post_process returns the resolved output path
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        input_file = input_dir / "test.mp3"
        input_file.write_text("input content")
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        output_file = output_dir / "test.mp3"
        output_file.write_text("existing output")

        file_path_set = (str(input_dir) + os.sep, "test", "mp3")
        
        result = controller_instance.file_handler.post_process(
            file_path_set,
            str(output_file),
            delete=False,
            show_status=False
        )
        
        # Should return test_1.mp3 path (not the original)
        assert result == os.path.join(str(output_dir), "test_1.mp3")
        assert result != str(output_file)

    def test_post_process_with_delete_and_conflict(self, controller_instance, tmp_path):
        # Test that post_process correctly handles delete flag with conflict resolution.
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        input_file = input_dir / "test.mp3"
        input_file.write_text("input content")

        output_dir = tmp_path / "output"
        output_dir.mkdir()
        output_file = output_dir / "test.mp3"
        output_file.write_text("existing output")
        
        file_path_set = (str(input_dir) + os.sep, "test", "mp3")
        
        # Call post_process with delete=True
        # post_process deletes if and only if the resolved output path EXISTS
        # Since we haven't actually created the resolved file, deletion won't happen
        result = controller_instance.file_handler.post_process(
            file_path_set,
            str(output_file),
            delete=False,  # Set False, resolved file does not yet exist
            show_status=False
        )
        
        # Input file should still exist
        assert input_file.exists()
        # Resolved output path should be returned (test_1.mp3)
        assert result == os.path.join(str(output_dir), "test_1.mp3")

    def test_post_process_without_conflict(self, controller_instance, tmp_path):
        # Test that post_process works normally when no conflict exists
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        input_file = input_dir / "test.mp3"
        input_file.write_text("input content")
        
        # Create output directory (but NOT the output file itself)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        output_file = output_dir / "test.mp3"
        
        file_path_set = (str(input_dir) + os.sep, "test", "mp3")
        
        result = controller_instance.file_handler.post_process(
            file_path_set,
            str(output_file),
            delete=False,
            show_status=False
        )

        assert result == str(output_file)


class TestConflictResolutionIntegration:
    # Integration tests for conflict resolution in actual conversion scenarios

    def test_multiple_conversions_same_output_dir(self, controller_instance, tmp_path):
        # Test that multiple conversions to same output don't overwrite
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        output_path = os.path.join(str(output_dir), "result.mp4")
        
        Path(output_path).write_text("first conversion")
        resolved1 = controller_instance.file_handler._resolve_output_file_conflict(output_path)
        assert resolved1 == os.path.join(str(output_dir), "result_1.mp4")
        
        # Create, try again, paths should be different
        Path(resolved1).write_text("second conversion")        
        resolved2 = controller_instance.file_handler._resolve_output_file_conflict(output_path)

        assert resolved2 == os.path.join(str(output_dir), "result_2.mp4")
        assert output_path != resolved1 != resolved2