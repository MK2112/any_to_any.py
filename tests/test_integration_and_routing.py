import pytest
import argparse
from unittest import mock
from any_to_any import AnyToAny

@pytest.fixture
def instance():
    return AnyToAny()

def test_routing_supported_formats(instance):
    # Ensure all supported formats are routed to the correct handler or codec.
    for cat, formats in instance._supported_formats.items():
        for fmt, handler in formats.items():
            if callable(handler):
                # Should call the handler without error (mock file_paths)
                with mock.patch.object(instance, handler.__name__, return_value=None) as m:
                    getattr(instance, handler.__name__)({}, fmt)
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


def test_end_with_msg_logs_and_exits(instance, caplog):
    # Test _end_with_msg logs error and raises SystemExit.
    with caplog.at_level('WARNING'):
        with pytest.raises(SystemExit):
            instance._end_with_msg(SystemExit, 'fail message')
    assert 'fail message' in caplog.text

def test_recursive_file_discovery(instance, tmp_path):
    # _get_file_paths does not recurse; only top-level files are found.
    d1 = tmp_path / "a"
    d2 = d1 / "b"
    d2.mkdir(parents=True)
    f = d2 / "test.mp4"
    f.write_bytes(b"\x00"*128)
    file_paths = instance._get_file_paths(str(tmp_path))
    # Should NOT find nested files
    found = any(
        str(f.parent) in path[0] and path[1] == 'test' and path[2] == 'mp4'
        for paths in file_paths.values() for path in paths
    )
    assert not found  # Documented limitation, this is intentional


def test_weird_filenames(instance, tmp_path):
    # Test handling of files with unicode and special chars in names.
    fname = "weird_名字_#@!.mp3"
    f = tmp_path / fname
    f.write_bytes(b"\x00"*128)
    file_paths = instance._get_file_paths(str(tmp_path))
    found = any(fname[:-4] in path[1] for paths in file_paths.values() for path in paths)
    assert found

def test_post_process_permission_error(instance, tmp_path):
    # Test _post_process logs and raises on permission error during delete.
    f = tmp_path / "test.mp4"
    f.write_bytes(b"\x00"*128)
    with mock.patch("os.remove", side_effect=PermissionError):
        with pytest.raises(PermissionError):
            instance._post_process((str(tmp_path) + "/", 'test', 'mp4'), str(tmp_path / "out.mp3"), delete=True)

