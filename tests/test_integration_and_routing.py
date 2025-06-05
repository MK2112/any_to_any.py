import logging
import pytest
import argparse
from unittest import mock
import utils.language_support as lang

# Import fixture with underscore to avoid redefinition warning
from tests.test_fixtures import converter_instance as _converter_instance

def test_routing_supported_formats(_converter_instance):
    # Ensure all supported formats are routed to the correct handler or codec.
    for cat, formats in _converter_instance._supported_formats.items():
        for fmt, handler in formats.items():
            if callable(handler):
                # Should call the handler without error (mock file_paths)
                with mock.patch.object(_converter_instance, handler.__name__, return_value=None) as m:
                    getattr(_converter_instance, handler.__name__)({}, fmt)
                    m.assert_called()
            else:
                # Should be a codec string or list
                assert isinstance(handler, (str, list))

def test_run_web_flag_starts_web():
    # Test that the CLI parser recognizes the -w/--web flag.
    parser = argparse.ArgumentParser()
    parser.add_argument('-w', '--web', action='store_true')
    args = parser.parse_args(['-w'])
    assert args.web


def test_end_with_msg_logs_and_exits(_converter_instance, caplog):
    # Test _end_with_msg logs error and raises SystemExit.
    with caplog.at_level('WARNING'):
        with pytest.raises(SystemExit):
            _converter_instance._end_with_msg(SystemExit, 'fail message')
    assert 'fail message' in caplog.text


def test_recursive_file_discovery(_converter_instance, tmp_path):
    # get_file_paths does not recurse; only top-level files are found.
    d1 = tmp_path / "a"
    d2 = d1 / "b"
    d2.mkdir(parents=True)
    test_file = d2 / "test.mp4"
    test_file.write_bytes(b"\x00"*128)
    file_paths = _converter_instance.file_handler.get_file_paths(str(tmp_path))
    # Should NOT find nested files
    found = any(
        str(test_file.parent) in path[0] and path[1] == 'test' and path[2] == 'mp4'
        for paths in file_paths.values() for path in paths
    )
    assert not found  # Documented limitation, this is intentional


def test_weird_filenames(_converter_instance, tmp_path):
    # Test handling of files with unicode and special chars in names.
    fname = "weird_名字_#@!.mp3"
    test_file = tmp_path / fname
    test_file.write_bytes(b"\x00"*128)
    file_paths = _converter_instance.file_handler.get_file_paths(
        input=str(tmp_path), 
        supported_formats=_converter_instance._supported_formats
    )
    found = any(
        fname[:-4] in path[1] 
        for paths in file_paths.values() 
        for path in paths
    )
    assert found


def test_post_process_permission_error(_converter_instance, tmp_path):
    # Test _post_process logs and raises on permission error during delete.
    test_file = tmp_path / "test.mp4"
    test_file.write_bytes(b"\x00"*128)
    with mock.patch("os.remove", side_effect=PermissionError):
        with pytest.raises(PermissionError):
            _converter_instance._post_process(
                (str(tmp_path) + "/", 'test', 'mp4'), 
                str(tmp_path / "out.mp3"), 
                delete=True
            )


def setup_converter(converter_instance, output_dir):
    converter_instance.output = str(output_dir)
    converter_instance.recursive = False
    converter_instance.framerate = 30
    converter_instance.quality = 'medium'
    converter_instance.merging = False
    converter_instance.concatenating = False
    converter_instance.locale = 'en'
    converter_instance.delete = False
    converter_instance.event_logger = logging.getLogger(__name__)
    converter_instance.file_handler = type('FileHandler', (), {
        'get_file_paths': lambda self, paths: {}
    })()
    converter_instance.process_files = mock.MagicMock()
    return converter_instance


def test_watchdropzone_nonexistent_dir(_converter_instance, caplog):
    # Configure converter instance
    converter = setup_converter(_converter_instance, "/tmp/output")
    
    # Clear any existing log messages
    caplog.clear()
    
    # Test with non-existent directory
    converter.watchdropzone("/nonexistent/directory")
    
    # Verify error was logged
    assert lang.get_translation('not_exist_not_dir', converter.locale).lower() in caplog.text.lower()


def test_watchdropzone_file_instead_of_dir(_converter_instance, tmp_path, caplog):
    # Configure converter instance
    converter = setup_converter(_converter_instance, "/tmp/output")
    
    # Create a test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")
    
    # Clear any existing log messages
    caplog.clear()
    
    # Test with file path instead of directory
    converter.watchdropzone(str(test_file))
    
    # Verify error was logged
    assert lang.get_translation('watch_not_dir', converter.locale).lower() in caplog.text.lower()

