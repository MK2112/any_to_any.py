import hmac
import hashlib
import io
import json
import os
import sys
import time
import zipfile

import pytest

import web_to_any as w


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setitem(w.app.config, "UPLOADED_FILES_DEST", str(tmp_path / "uploads"))
    monkeypatch.setitem(w.app.config, "CONVERTED_FILES_DEST", str(tmp_path / "converted"))
    monkeypatch.setitem(w.app.config, "API_KEYS", {"test-key"})
    with w.progress_lock:
        w.shared_progress_dict.clear()
        w._last_progress_cache.clear()
    with w._job_lock:
        w._job_records.clear()
        w._job_owners.clear()
    yield w.app.test_client(), tmp_path
    with w._job_lock:
        w._job_records.clear()
        w._job_owners.clear()
    with w.progress_lock:
        w.shared_progress_dict.clear()


def test_api_disabled_without_keys(api_client, monkeypatch):
    client, _ = api_client
    monkeypatch.setitem(w.app.config, "API_KEYS", set())
    assert client.post("/api/jobs").status_code == 503


def test_api_requires_key(api_client):
    client, _ = api_client
    assert client.post("/api/jobs").status_code == 401
    assert client.get("/api/jobs/" + "a" * 32).status_code == 401


def test_api_submit_status_and_signed_download(api_client, monkeypatch):
    client, _ = api_client
    monkeypatch.setattr(w, "send_to_backend", lambda *args, **kwargs: None)
    headers = {"X-API-Key": "test-key"}

    response = client.post(
        "/api/jobs",
        headers=headers,
        data={
            "files": [(io.BytesIO(b"pngdata"), "photo.png")],
            "conversionType": "jpeg",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202, response.get_data(as_text=True)
    data = response.get_json()
    job_id = data["job_id"]
    assert data["status_url"] == f"/api/jobs/{job_id}"

    status = client.get(f"/api/jobs/{job_id}", headers=headers)
    assert status.status_code == 200
    assert status.get_json()["job_id"] == job_id

    # A tampered token is rejected.
    assert client.get(data["download_url"] + "tampered").status_code == 403

    # Mark the job complete and provide output, then use the signed link.
    with w._job_lock:
        record = w._job_records[job_id]
        record["status"] = "done"
        with open(os.path.join(record["converted_dir"], "photo.jpeg"), "wb") as fh:
            fh.write(b"jpegdata")
    download = client.get(data["download_url"])
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
        assert any(name.endswith("photo.jpeg") for name in archive.namelist())


def test_api_bearer_key_and_expired_token(api_client):
    client, _ = api_client
    assert (
        client.post("/api/jobs", headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )
    # The bearer key is accepted (the request fails later only for missing files).
    assert (
        client.post("/api/jobs", headers={"Authorization": "Bearer test-key"}).status_code
        == 400
    )
    job_id = "a" * 32
    expired = w._sign_download_token(job_id, int(time.time()) - 1)
    assert client.get(f"/api/jobs/{job_id}/download?token={expired}").status_code == 403


def test_webhook_payload_is_signed(api_client, monkeypatch):
    _, _ = api_client
    job_id = "b" * 32
    with w._job_lock:
        w._job_records[job_id] = {
            "webhook_url": "https://example.com/hook",
            "status": "done",
            "error": None,
        }

    captured = {}

    class FakeRequests:
        @staticmethod
        def post(url, data=None, headers=None, timeout=None):
            captured.update(url=url, data=data, headers=headers, timeout=timeout)

    monkeypatch.setitem(sys.modules, "requests", FakeRequests)
    w._send_webhook(job_id)

    expected = hmac.new(
        w.app.config["API_SECRET"], captured["data"], hashlib.sha256
    ).hexdigest()
    assert captured["headers"]["X-Any2Any-Signature"] == f"sha256={expected}"
    assert json.loads(captured["data"])["status"] == "done"


def test_api_cancel_queued_job_reaches_terminal_state(api_client, monkeypatch):
    client, _ = api_client
    headers = {"X-API-Key": "test-key"}
    from concurrent.futures import Future

    pending = []

    def submit(*args, **kwargs):
        future = Future()
        pending.append(future)
        return future

    monkeypatch.setattr(w._job_executor, "submit", submit)

    captured = {}

    class FakeRequests:
        @staticmethod
        def post(url, data=None, headers=None, timeout=None):
            captured.update(url=url, data=data, headers=headers, timeout=timeout)

    monkeypatch.setitem(sys.modules, "requests", FakeRequests)

    response = client.post(
        "/api/jobs",
        headers=headers,
        data={
            "files": [(io.BytesIO(b"pngdata"), "photo.png")],
            "conversionType": "jpeg",
            "webhook_url": "https://example.com/hook",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202, response.get_data(as_text=True)
    job_id = response.get_json()["job_id"]
    assert not pending[0].done()  # the job really was queued, not running

    cancel = client.post(f"/api/jobs/{job_id}/cancel", headers=headers)
    assert cancel.status_code == 202
    with w._job_lock:
        record = dict(w._job_records[job_id])
    assert record["status"] == "cancelled"
    assert record["completed_at"] > 0  # eligible for retention cleanup

    status = client.get(f"/api/jobs/{job_id}", headers=headers)
    assert status.get_json()["status"] == "cancelled"

    payload = json.loads(captured["data"])
    assert payload["event"] == "job.cancelled"
    assert payload["status"] == "cancelled"


def test_api_secret_is_bytes(api_client):
    # hmac.new() requires bytes; a string SECRET_KEY must be normalized.
    assert isinstance(w.app.config["API_SECRET"], bytes)


def test_openapi_spec_and_docs(api_client):
    client, _ = api_client
    spec = client.get("/api/openapi.json")
    assert spec.status_code == 200
    assert "/api/jobs" in spec.get_json()["paths"]
    assert "/api/jobs/{job_id}/download" in spec.get_json()["paths"]
    assert client.get("/api/docs").status_code == 200
