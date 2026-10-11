import sys
import subprocess
import os
import pytest
from tests.test_fixtures import controller_instance


def test_cli_help_output(tmp_path):
    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "any_to_any.py")
    )
    result = subprocess.run(
        [sys.executable, script_path, "-h"], capture_output=True, text=True
    )
    assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()


def test_cli_invalid_format(tmp_path):
    result = subprocess.run(
        [sys.executable, "any_to_any.py", "-i", str(tmp_path), "-f", "xyz"],
        cwd=str(tmp_path.parent),
        capture_output=True,
        text=True,
    )
    assert (
        "unsupported format" in result.stdout.lower()
        or "unsupported format" in result.stderr.lower()
        or result.returncode != 0
    )


def test_blank_start_no_files_in_cli_output(controller_instance, caplog):
    with caplog.at_level("INFO"):
        # Jesus Christ, centralize this; maybe make a central factory for this
        controller_instance.run(
            [],
            None,
            None,
            None,
            None,
            None,
            False,
            False,
            False,
            False,
            False,
            False,
            "en_US",
            1,
        )
    assert "No convertible media files" in caplog.text


def test_cli_workers_flag_recognized(tmp_path):
    # Run CLI with --workers on an empty directory; should exit cleanly
    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "any_to_any.py")
    )
    result = subprocess.run(
        [sys.executable, script_path, "-i", str(tmp_path), "--workers", "2"],
        capture_output=True,
        text=True,
    )
    # Ensure argparse accepts the flag (no "unrecognized arguments"),
    # return code may be 0 or 1 depending on no-media condition and locale.
    combined = (result.stdout + "\n" + result.stderr).lower()
    assert "unrecognized arguments" not in combined
    assert result.returncode in (0, 1)


def _script_path():
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "any_to_any.py")
    )


@pytest.mark.parametrize("bad_workers", ["0", "-5"])
def test_cli_workers_below_range_rejected(tmp_path, bad_workers):
    # --workers below 1 must fail fast with an argparse error (exit 2)
    result = subprocess.run(
        [sys.executable, _script_path(), "-i", str(tmp_path), "--workers", bad_workers],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--workers" in (result.stdout + result.stderr)


def test_cli_workers_huge_rejected(tmp_path):
    # Far above cpu_count - 1 must fail
    huge = (os.cpu_count() or 1) * 1000 + 100
    result = subprocess.run(
        [
            sys.executable,
            _script_path(),
            "-i",
            str(tmp_path),
            "--workers",
            str(huge),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--workers" in (result.stdout + result.stderr)


@pytest.mark.parametrize("bad_fps", ["0", "-5"])
def test_cli_framerate_not_positive_rejected(tmp_path, bad_fps):
    # Negative/zero framerates must fail fast
    result = subprocess.run(
        [
            sys.executable,
            _script_path(),
            "-i",
            str(tmp_path),
            "-f",
            "mp4",
            "--framerate",
            bad_fps,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--framerate" in (result.stdout + result.stderr)


def test_cli_trailing_comma_format_no_empty_target(tmp_path):
    # "-f mp3," must behave like "-f mp3"
    result = subprocess.run(
        [sys.executable, _script_path(), "-i", str(tmp_path), "-f", "mp3,"],
        capture_output=True,
        text=True,
    )
    combined = (result.stdout + "\n" + result.stderr).lower()
    assert "unrecognized arguments" not in combined
    assert result.returncode in (0, 1)
