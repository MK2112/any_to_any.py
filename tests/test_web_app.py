import io
import re
import pytest
import web_to_any as w

from unittest import mock



@pytest.fixture(autouse=True)
def reset_web_globals():
    # Reset mutable module-level state (before and after each test)
    with w.progress_lock:
        w.shared_progress_dict.clear()
        w._last_progress_cache.clear()
        w._rate_limit.clear()
        w._csrf_tokens.clear()
    yield
    with w.progress_lock:
        w.shared_progress_dict.clear()
        w._last_progress_cache.clear()
        w._rate_limit.clear()
        w._csrf_tokens.clear()


@pytest.fixture
def client(reset_web_globals):
    return w.app.test_client()


@pytest.fixture
def tmp_storage(tmp_path, monkeypatch):
    # Point upload/converted destinations at scratch directory
    monkeypatch.setitem(w.app.config, "UPLOADED_FILES_DEST", str(tmp_path / "uploads"))
    monkeypatch.setitem(w.app.config, "CONVERTED_FILES_DEST", str(tmp_path / "converted"))
    return tmp_path


def _csrf_for(client):
    # Fetch CSRF token like a browser to observe how it evolves over time
    html = client.get("/").get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([a-f0-9]{64})"', html)
    assert match, "csrf hidden input not found in index page"
    return match.group(1)


def _wait_for_call(mock_obj, timeout=10.0):
    # Wait for background conversion thread to invoke the any_to_any backend
    import time as _time
    deadline = _time.time() + timeout
    while _time.time() < deadline and mock_obj.call_count == 0:
        _time.sleep(0.02)
    assert mock_obj.call_count == 1


def test_convert_returns_202_and_job_id(client, tmp_storage):
    # Test the pipeline of CSRF-validated upload spawning background job and returning its id for progress polling
    token = _csrf_for(client)
    with mock.patch.object(w, "send_to_backend") as mock_backend:
        resp = client.post(
            "/convert",
            data={
                "files": [(io.BytesIO(b"pngdata"), "photo.png")],
                "conversionType": "jpeg",
                "csrf_token": token,
            },
            content_type="multipart/form-data",
        )
    assert resp.status_code == 202
    job_id = resp.get_json()["job_id"]
    assert re.fullmatch(r"[0-9a-f]{8}", job_id)
    _wait_for_call(mock_backend)
    args, _ = mock_backend.call_args
    assert args[2] == "jpeg" # target format
    assert args[7] is False  # no merge
    assert args[8] is False  # no concat
    assert args[9] is None   # no specified resolution
