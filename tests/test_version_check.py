from unittest.mock import patch, Mock
from gui.qt_app import check_for_update


class TestCheckForUpdate:
    def test_update_available_when_remote_is_newer(self, monkeypatch):
        monkeypatch.setattr("gui.qt_app.VERSION", "1.0.0")
        mock_response = Mock()
        mock_response.json.return_value = {"tag_name": "v1.1.1"}
        mock_response.raise_for_status.return_value = None
        with patch("gui.qt_app.requests.get", return_value=mock_response):
            result = check_for_update()
        assert result == "1.1.1"

    def test_no_update_when_versions_match(self, monkeypatch):
        monkeypatch.setattr("gui.qt_app.VERSION", "1.1.1")
        mock_response = Mock()
        mock_response.json.return_value = {"tag_name": "v1.1.1"}
        mock_response.raise_for_status.return_value = None
        with patch("gui.qt_app.requests.get", return_value=mock_response):
            result = check_for_update()
        assert result is None
