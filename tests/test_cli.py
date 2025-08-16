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
