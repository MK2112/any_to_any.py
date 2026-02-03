import pytest
import logging

from unittest import mock
from utils.category import Category
from tests.test_fixtures import controller_instance


class TestSingleFormatBehavior:
    def test_single_format_string_conversion(self, controller_instance, tmp_path):
        # Test that single format string is handled correctly (backward compatibility)
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False
        formats_processed = []

        def capture_process(*args, **kwargs):
            formats_processed.append(controller_instance.target_format)
            # Don't actually process to avoid file dependencies

        controller_instance.process_file_paths = capture_process

        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get_files:
            mock_get_files.return_value = {
                Category.AUDIO: [("/tmp", "test", "mp3")],
                Category.MOVIE: [],
                Category.IMAGE: [],
                Category.DOCUMENT: [],
            }

            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format="mp4",
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

        assert len(formats_processed) == 1
        assert formats_processed[0] == "mp4"

    def test_single_format_none(self, controller_instance, tmp_path):
        # Test that None format is handled correctly
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        formats_processed = []

        def capture_process(*args, **kwargs):
            formats_processed.append(controller_instance.target_format)

        controller_instance.process_file_paths = capture_process

        # Mock file_handler.get_file_paths to return mock file paths
        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get_files:
            mock_get_files.return_value = {
                Category.AUDIO: [
                    ("/tmp", "test", "mp3")
                ],  # Add dummy entry to avoid "no files" exit
                Category.MOVIE: [],
                Category.IMAGE: [],
                Category.DOCUMENT: [],
            }

            # Run with None format
            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format=None,
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

        # Should not process any format
        assert len(formats_processed) == 0


class TestMultiFormatBehavior:
    def _make_mock_file_paths(self):
        # Helper to create mock file paths structure with at least one file to avoid no-files-found error
        return {
            Category.AUDIO: [
                ("/tmp", "test", "mp3")
            ],  # dummy entry avoids "no files" exit
            Category.MOVIE: [],
            Category.IMAGE: [],
            Category.DOCUMENT: [],
        }

    def test_multi_format_comma_separated(self, controller_instance, tmp_path):
        # Test that comma-separated formats are processed sequentially
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        formats_processed = []

        def capture_process(*args, **kwargs):
            formats_processed.append(controller_instance.target_format)

        controller_instance.process_file_paths = capture_process

        # Mock file_handler.get_file_paths to return empty file paths
        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get_files:
            mock_get_files.return_value = self._make_mock_file_paths()
            # Run with comma-separated formats
            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format="mp4,mp3,jpeg",
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

        # Should process all three formats in order
        assert len(formats_processed) == 3
        assert formats_processed[0] == "mp4"
        assert formats_processed[1] == "mp3"
        assert formats_processed[2] == "jpeg"

    def test_multi_format_with_spaces(self, controller_instance, tmp_path):
        # Test that spaces around format names are trimmed
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        formats_processed = []

        def capture_process(*args, **kwargs):
            formats_processed.append(controller_instance.target_format)

        controller_instance.process_file_paths = capture_process

        # Mock file_handler.get_file_paths to return empty file paths
        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get_files:
            mock_get_files.return_value = self._make_mock_file_paths()
            # Run with spaces around format names
            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format=" mp4 , mp3 , jpeg ",
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

        # Should trim spaces and process in order
        assert len(formats_processed) == 3
        assert formats_processed[0] == "mp4"
        assert formats_processed[1] == "mp3"
        assert formats_processed[2] == "jpeg"

    def test_multi_format_case_insensitive(self, controller_instance, tmp_path):
        # Test that format names are converted to lowercase
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        formats_processed = []

        def capture_process(*args, **kwargs):
            formats_processed.append(controller_instance.target_format)

        controller_instance.process_file_paths = capture_process

        # Mock file_handler.get_file_paths to return empty file paths
        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get_files:
            mock_get_files.return_value = self._make_mock_file_paths()

            # Run with mixed case format names
            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format="MP4,Mp3,JPEG",
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

        # Should convert to lowercase
        assert len(formats_processed) == 3
        assert formats_processed[0] == "mp4"
        assert formats_processed[1] == "mp3"
        assert formats_processed[2] == "jpeg"

    def test_multi_format_across_flag(self, controller_instance, tmp_path):
        # Test multi-format conversion with across flag
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        formats_processed = []

        def capture_process(*args, **kwargs):
            formats_processed.append(controller_instance.target_format)

        controller_instance.process_file_paths = capture_process

        # Mock file_handler.get_file_paths to return empty file paths
        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get_files:
            mock_get_files.return_value = self._make_mock_file_paths()

            # Run with across flag and multiple formats
            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format="mp4,mp3",
                output=str(tmp_path),
                framerate=None,
                quality=None,
                split=None,
                merge=False,
                concat=False,
                delete=False,
                across=True,
                recursive=False,
                dropzone=False,
                language=None,
                workers=1,
            )

        # Should process both formats
        assert len(formats_processed) == 2
        assert formats_processed == ["mp4", "mp3"]

    def test_multi_format_list_input(self, controller_instance, tmp_path):
        # Test that format argument can also be passed as a list
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        formats_processed = []

        def capture_process(*args, **kwargs):
            formats_processed.append(controller_instance.target_format)

        controller_instance.process_file_paths = capture_process

        # Mock file_handler.get_file_paths to return empty file paths
        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get_files:
            mock_get_files.return_value = self._make_mock_file_paths()

            # Run with format as list (as from CLI parsing)
            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format=["mp4", "mp3", "jpeg"],
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

        # Should process all formats from list
        assert len(formats_processed) == 3
        assert formats_processed == ["mp4", "mp3", "jpeg"]

    def test_multi_format_empty_list(self, controller_instance, tmp_path):
        # Test that empty format list is handled correctly
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        formats_processed = []

        def capture_process(*args, **kwargs):
            formats_processed.append(controller_instance.target_format)

        controller_instance.process_file_paths = capture_process

        # Mock file_handler.get_file_paths to return empty file paths
        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get_files:
            mock_get_files.return_value = self._make_mock_file_paths()

            # Run with empty list
            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format=[],
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

        # Should not process any format
        assert len(formats_processed) == 0

    def test_multi_format_single_item_list(self, controller_instance, tmp_path):
        # Test single format in list (edge case)
        controller_instance.output = str(tmp_path)
        controller_instance.recursive = False
        controller_instance.locale = "en_US"
        controller_instance.delete = False

        formats_processed = []

        def capture_process(*args, **kwargs):
            formats_processed.append(controller_instance.target_format)

        controller_instance.process_file_paths = capture_process

        # Mock file_handler.get_file_paths to return empty file paths
        with mock.patch.object(
            controller_instance.file_handler, "get_file_paths"
        ) as mock_get_files:
            mock_get_files.return_value = self._make_mock_file_paths()

            # Run with single format in list
            controller_instance.run(
                input_path_args=[str(tmp_path)],
                format=["mp4"],
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

        # Should process single format
        assert len(formats_processed) == 1
        assert formats_processed[0] == "mp4"
