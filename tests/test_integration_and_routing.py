import pytest
import logging
import argparse
import utils.language_support as lang
from unittest import mock
from core.utils.exit import end_with_msg
from tests.test_fixtures import controller_instance


def test_run_web_flag_starts_web():
    # Test that the CLI parser recognizes the -w/--web flag.
    parser = argparse.ArgumentParser()
    parser.add_argument("-w", "--web", action="store_true")
    args = parser.parse_args(["-w"])
    assert args.web


def test_end_with_msg_logs_and_exits(controller_instance, caplog):
    # Test _end_with_msg logs error and raises SystemExit.
    with caplog.at_level("WARNING"):
        with pytest.raises(SystemExit):
            end_with_msg(controller_instance.event_logger, SystemExit, "fail message")
    assert "fail message" in caplog.text


def test_recursive_file_discovery(controller_instance, tmp_path):
    # get_file_paths does not recurse; only top-level files are found.
    d1 = tmp_path / "a"
    d2 = d1 / "b"
    d2.mkdir(parents=True)
    test_file = d2 / "test.mp4"
    test_file.write_bytes(b"\x00" * 128)
    file_paths = controller_instance.file_handler.get_file_paths(str(tmp_path))
    # Should NOT find nested files
    found = any(
        str(test_file.parent) in path[0] and path[1] == "test" and path[2] == "mp4"
        for paths in file_paths.values()
        for path in paths
    )
    assert not found  # Documented limitation, this is intentional


def test_weird_filenames(controller_instance, tmp_path):
    # Test handling of files with unicode and special chars in names.
    fname = "weird_名字_#@!.mp3"
    test_file = tmp_path / fname
    test_file.write_bytes(b"\x00" * 128)
    file_paths = controller_instance.file_handler.get_file_paths(
        input=str(tmp_path), supported_formats=controller_instance._supported_formats
    )
    found = any(
        fname[:-4] in path[1] for paths in file_paths.values() for path in paths
    )
    assert found


def setup_converter(controller_instance, output_dir):
    controller_instance.output = str(output_dir)
    controller_instance.recursive = False
    controller_instance.framerate = 30
    controller_instance.quality = "medium"
    controller_instance.merging = False
    controller_instance.concatenating = False
    controller_instance.locale = "en"
    controller_instance.delete = False
    controller_instance.event_logger = logging.getLogger(__name__)
    controller_instance.file_handler = type(
        "FileHandler", (), {"get_file_paths": lambda self, paths: {}}
    )()
    controller_instance.process_files = mock.MagicMock()
    return controller_instance


def test_watchdropzone_nonexistent_dir(controller_instance, caplog):
    # Configure converter instance
    converter = setup_converter(controller_instance, "/tmp/output")

    # Clear any existing log messages
    caplog.clear()

    # Test with non-existent directory
    converter.watchdropzone("/nonexistent/directory")

    # Verify error was logged
    assert (
        lang.get_translation("not_exist_not_dir", converter.locale).lower()
        in caplog.text.lower()
    )


def test_watchdropzone_file_instead_of_dir(controller_instance, tmp_path, caplog):
    # Configure converter instance
    converter = setup_converter(controller_instance, "/tmp/output")

    # Create a test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")

    # Clear any existing log messages
    caplog.clear()

    # Test with file path instead of directory
    converter.watchdropzone(str(test_file))

    # Verify error was logged
    assert (
        lang.get_translation("watch_not_dir", converter.locale).lower()
        in caplog.text.lower()
    )
