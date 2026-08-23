from unittest.mock import patch, Mock
from utils.version_check import check_for_update


class TestCheckForUpdate:
    def test_update_available_when_remote_is_newer(self, monkeypatch):
        monkeypatch.setattr("utils.version_check.VERSION", "1.0.0")
        mock_response = Mock()
        mock_response.json.return_value = {"tag_name": "v1.1.1"}
        mock_response.raise_for_status.return_value = None
        with patch("utils.version_check.requests.get", return_value=mock_response):
            result = check_for_update()
        assert result == "1.1.1"

    def test_no_update_when_versions_match(self, monkeypatch):
        monkeypatch.setattr("utils.version_check.VERSION", "1.1.1")
        mock_response = Mock()
        mock_response.json.return_value = {"tag_name": "v1.1.1"}
        mock_response.raise_for_status.return_value = None
        with patch("utils.version_check.requests.get", return_value=mock_response):
            result = check_for_update()
        assert result is None

    def test_no_update_when_remote_is_older(self, monkeypatch):
        monkeypatch.setattr("utils.version_check.VERSION", "1.1.2")
        mock_response = Mock()
        mock_response.json.return_value = {"tag_name": "v1.1.1"}
        mock_response.raise_for_status.return_value = None
        with patch("utils.version_check.requests.get", return_value=mock_response):
            result = check_for_update()
        assert result is None

    def test_no_update_on_network_error(self, monkeypatch):
        import requests

        monkeypatch.setattr(
            "utils.version_check.requests.get",
            Mock(side_effect=requests.ConnectionError("offline")),
        )
        assert check_for_update() is None

    def test_no_update_on_http_error(self, monkeypatch):
        import requests

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("500")
        monkeypatch.setattr("utils.version_check.requests.get", Mock(return_value=mock_response))
        assert check_for_update() is None

    def test_no_update_on_empty_tag(self, monkeypatch):
        mock_response = Mock()
        mock_response.json.return_value = {"tag_name": ""}
        mock_response.raise_for_status.return_value = None
        with patch("utils.version_check.requests.get", return_value=mock_response):
            assert check_for_update() is None

    def test_no_update_on_malformed_tag(self, monkeypatch):
        mock_response = Mock()
        mock_response.json.return_value = {"tag_name": "not-a-version"}
        mock_response.raise_for_status.return_value = None
        with patch("utils.version_check.requests.get", return_value=mock_response):
            assert check_for_update() is None

    def test_no_update_on_missing_tag_key(self, monkeypatch):
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        with patch("utils.version_check.requests.get", return_value=mock_response):
            assert check_for_update() is None
