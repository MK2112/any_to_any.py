import os
import sys
import pytest
import shutil
import tempfile
from core.controller import Controller


@pytest.fixture
def temp_media_dir(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    # Fake File Creation
    (media_dir / "test.mp4").write_bytes(b"\x00" * 128)
    (media_dir / "test.mp3").write_bytes(b"\x00" * 128)
    (media_dir / "test.jpg").write_bytes(b"\x00" * 128)
    (media_dir / "test.txt").write_text("not a media file")
    return media_dir


@pytest.fixture
def test_input_folder(tmp_path):
    test_folder = tmp_path / "test_input"
    test_folder.mkdir()
    return test_folder


@pytest.fixture
def test_output_folder(tmp_path):
    test_folder = tmp_path / "test_output"
    test_folder.mkdir()
    return test_folder


@pytest.fixture
def controller_instance():
    controller = Controller()
    controller.locale = "English"
    return controller
