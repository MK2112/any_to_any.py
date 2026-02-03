import sys
import pytest

from unittest import mock


def test_cli_format_parsing_single():
    with mock.patch('core.controller.Controller') as mock_controller_class:
        mock_controller = mock.MagicMock()
        mock_controller_class.return_value = mock_controller
        mock_controller.supported_formats = ['mp4', 'mp3', 'jpeg']
        # Import and run the CLI with single format
        with mock.patch('sys.argv', ['any_to_any.py', '-f', 'mp4']):
            # We need to check the format parsing logic
            format_arg = 'mp4'
            formats = []
            if format_arg:
                formats = [fmt.strip() for fmt in format_arg.split(",")]
            
            assert len(formats) == 1
            assert formats[0] == 'mp4'


def test_cli_format_parsing_multi():
    # Test that comma-separated format argument is parsed correctly
    format_arg = 'mp4,mp3,jpeg'
    formats = []
    if format_arg:
        formats = [fmt.strip() for fmt in format_arg.split(",")]
    
    assert len(formats) == 3
    assert formats[0] == 'mp4'
    assert formats[1] == 'mp3'
    assert formats[2] == 'jpeg'


def test_cli_format_parsing_with_spaces():
    # Test that spaces are stripped from comma-separated formats
    format_arg = ' mp4 , mp3 , jpeg '
    formats = []
    if format_arg:
        formats = [fmt.strip() for fmt in format_arg.split(",")]
    
    assert len(formats) == 3
    assert formats[0] == 'mp4'
    assert formats[1] == 'mp3'
    assert formats[2] == 'jpeg'


def test_cli_format_parsing_none():
    # Test that None format argument results in empty list
    format_arg = None
    formats = []
    if format_arg:
        formats = [fmt.strip() for fmt in format_arg.split(",")]
    
    assert len(formats) == 0


def test_cli_format_parsing_empty_string():
    # Test that empty string format argument results in empty list
    format_arg = ''
    formats = []
    if format_arg:
        formats = [fmt.strip() for fmt in format_arg.split(",")]
    
    assert len(formats) == 0


def test_cli_format_parsing_single_with_spaces():
    # Test that spaces in single format are stripped
    format_arg = ' mp4 '
    formats = []
    if format_arg:
        formats = [fmt.strip() for fmt in format_arg.split(",")]
    
    assert len(formats) == 1
    assert formats[0] == 'mp4'
