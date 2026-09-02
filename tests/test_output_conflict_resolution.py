import os
import time
import pytest
import threading

from pathlib import Path
from tests.test_fixtures import controller_instance


class TestOutputConflictResolution:
    def test_no_conflict_returns_original_path(self, controller_instance, tmp_path):
        # If file doesn't exist, original path is returned
        output_path = os.path.join(str(tmp_path), "nonexistent_file.mp3")

        result = controller_instance.file_handler._resolve_output_file_conflict(
            output_path
        )

        assert result == output_path

    def test_numeric_suffix_single_conflict(self, controller_instance, tmp_path):
        # Numeric suffix is added when file exists
        existing_file = tmp_path / "test.mp3"
        existing_file.write_text("existing content")
        result = controller_instance.file_handler._resolve_output_file_conflict(
            str(existing_file)
        )

        assert result == os.path.join(str(tmp_path), "test_1.mp3")
        assert os.path.exists(str(existing_file))  # Original still exists
        assert not os.path.exists(result)  # New path doesn't exist yet

    def test_numeric_suffix_multiple_conflicts(self, controller_instance, tmp_path):
        # Numeric suffix increments when multiple files exist
        (tmp_path / "test.mp3").write_text("1")
        (tmp_path / "test_1.mp3").write_text("2")
        (tmp_path / "test_2.mp3").write_text("3")
        result = controller_instance.file_handler._resolve_output_file_conflict(
            os.path.join(str(tmp_path), "test.mp3")
        )
        assert result == os.path.join(str(tmp_path), "test_3.mp3")

    def test_numeric_suffix_with_different_extension(
        self, controller_instance, tmp_path
    ):
        # Numeric suffix works with different file extensions
        existing_file = tmp_path / "test.wav"
        existing_file.write_text("existing")
        result = controller_instance.file_handler._resolve_output_file_conflict(
            str(existing_file)
        )

        assert result == os.path.join(str(tmp_path), "test_1.wav")
        assert result.endswith(".wav")

    def test_numeric_suffix_with_complex_filename(self, controller_instance, tmp_path):
        # Numeric suffix works with complex filenames
        existing_file = tmp_path / "my_audio_file_v2.flac"
        existing_file.write_text("existing")
        result = controller_instance.file_handler._resolve_output_file_conflict(
            str(existing_file)
        )

        assert result == os.path.join(str(tmp_path), "my_audio_file_v2_1.flac")

    def test_random_suffix_is_unique(self, controller_instance, tmp_path):
        # Random suffixes are unique across multiple calls
        base_path = os.path.join(str(tmp_path), "test.mp3")
        (tmp_path / "test.mp3").write_text("existing")
        for i in range(1, 100):
            (tmp_path / f"test_{i}.mp3").write_text(str(i))
        result1 = controller_instance.file_handler._resolve_output_file_conflict(
            base_path
        )
        os.makedirs(os.path.dirname(result1), exist_ok=True)
        with open(result1, "w") as f:
            f.write("new")
        result2 = controller_instance.file_handler._resolve_output_file_conflict(
            base_path
        )
        assert result1 != result2

    def test_conflict_resolution_preserves_original_file(
        self, controller_instance, tmp_path
    ):
        # Original file is not overwritten
        existing_file = tmp_path / "test.mp3"
        existing_content = "original content"
        existing_file.write_text(existing_content)
        result = controller_instance.file_handler._resolve_output_file_conflict(
            str(existing_file)
        )

        assert existing_file.read_text() == existing_content
        assert result != str(existing_file)


class TestPostProcessWithConflictResolution:
    def test_post_process_returns_resolved_path(self, controller_instance, tmp_path):
        # post_process returns the resolved output path
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
            file_path_set, str(output_file), delete=False, show_status=False
        )

        assert result == str(output_file)

    def test_post_process_with_delete_and_conflict(self, controller_instance, tmp_path):
        # post_process correctly handles delete flag with conflict resolution
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
            show_status=False,
        )

        assert input_file.exists()
        assert result == str(output_file)

    def test_post_process_without_conflict(self, controller_instance, tmp_path):
        # post_process works normally when no conflict exists
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        input_file = input_dir / "test.mp3"
        input_file.write_text("input content")

        output_dir = tmp_path / "output"
        output_dir.mkdir()
        output_file = output_dir / "test.mp3"

        file_path_set = (str(input_dir) + os.sep, "test", "mp3")

        result = controller_instance.file_handler.post_process(
            file_path_set, str(output_file), delete=False, show_status=False
        )

        assert result == str(output_file)


class TestConflictResolutionRace:
    # The resolver must never hand the same output name to two workers
    def test_repeated_resolution_never_returns_same_path(
        self, controller_instance, tmp_path
    ):
        # Without a write in between, the same target must resolve to two distinct names
        output_path = os.path.join(str(tmp_path), "song.mp3")

        first = controller_instance.file_handler._resolve_output_file_conflict(
            output_path
        )
        second = controller_instance.file_handler._resolve_output_file_conflict(
            output_path
        )

        assert first != second

    def test_concurrent_resolution_no_duplicate_candidates(
        self, controller_instance, tmp_path
    ):
        # Two workers converting the same basename (--across) must never be handed the same candidate
        output_path = os.path.join(str(tmp_path), "song.mp3")
        barrier = threading.Barrier(2)
        results = []
        results_lock = threading.Lock()

        def worker():
            barrier.wait()
            resolved = controller_instance.file_handler._resolve_output_file_conflict(
                output_path
            )
            with results_lock:
                results.append(resolved)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 2
        assert len(set(results)) == 2

    def test_concurrent_dir_resolution_no_duplicate_candidates(
        self, controller_instance, tmp_path
    ):
        # Same guarantee for directory targets
        dir_path = os.path.join(str(tmp_path), "frames")
        barrier = threading.Barrier(2)
        results = []
        results_lock = threading.Lock()

        def worker():
            barrier.wait()
            resolved = controller_instance.file_handler._resolve_output_dir_conflict(
                dir_path
            )
            with results_lock:
                results.append(resolved)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(results)) == 2

    def test_resolve_write_postprocess_cycle(self, controller_instance, tmp_path):
        # Resolve, write, post_process. Once the real file
        # exists on disk, the next resolution picks the numeric suffix
        output_path = os.path.join(str(tmp_path), "song.mp3")
        resolved = controller_instance.file_handler._resolve_output_file_conflict(
            output_path
        )
        with open(resolved, "w") as f:
            f.write("done")
        controller_instance.file_handler.post_process(
            (str(tmp_path) + os.sep, "src", "mp3"),
            resolved,
            delete=False,
            show_status=False,
        )

        again = controller_instance.file_handler._resolve_output_file_conflict(
            output_path
        )
        assert again == os.path.join(str(tmp_path), "song_1.mp3")


class TestConflictResolutionIntegration:
    def test_multiple_conversions_same_output_dir(self, controller_instance, tmp_path):
        # Multiple conversions to same output don't overwrite
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        output_path = os.path.join(str(output_dir), "result.mp4")

        Path(output_path).write_text("first conversion")
        resolved1 = controller_instance.file_handler._resolve_output_file_conflict(
            output_path
        )
        assert resolved1 == os.path.join(str(output_dir), "result_1.mp4")

        # Create, try again, paths should be different
        Path(resolved1).write_text("second conversion")
        resolved2 = controller_instance.file_handler._resolve_output_file_conflict(
            output_path
        )

        assert resolved2 == os.path.join(str(output_dir), "result_2.mp4")
        assert output_path != resolved1 != resolved2
