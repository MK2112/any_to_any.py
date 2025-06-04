import sys
import subprocess
import os
import pytest
from tests.test_fixtures import converter_instance

def test_cli_help_output(tmp_path):
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'any_to_any.py'))
    result = subprocess.run([sys.executable, script_path, "-h"], capture_output=True, text=True)
    assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()

def test_cli_invalid_format(tmp_path):
    result = subprocess.run([sys.executable, "any_to_any.py", "-i", str(tmp_path), "-f", "xyz"], cwd=str(tmp_path.parent), capture_output=True, text=True)
    assert "unsupported format" in result.stdout.lower() or "unsupported format" in result.stderr.lower() or result.returncode != 0

def test_blank_start_no_files_in_cli_output(converter_instance, caplog):
    with caplog.at_level("INFO"):
        # Jesus Christ, centralize this; maybe make a central factory for this
        converter_instance.run([], None, None, None, None, False, False, False, False, False, False, "en_US")
    assert "No convertible media files" in caplog.text
