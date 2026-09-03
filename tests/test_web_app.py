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
        w._job_owners.clear()
        w._job_records.clear()
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
    monkeypatch.setitem(
        w.app.config, "CONVERTED_FILES_DEST", str(tmp_path / "converted")
    )
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
    # CSRF-validated upload spawning background job and returning its id for progress polling
    tok = _csrf_for(client)
    with mock.patch.object(w, "send_to_backend") as mock_backend:
        resp = client.post(
            "/convert",
            data={
                "files": [(io.BytesIO(b"pngdata"), "photo.png")],
                "conversionType": "jpeg",
                "csrf_token": tok,
            },
            content_type="multipart/form-data",
        )
    assert resp.status_code == 202
    job_id = resp.get_json()["job_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", job_id)
    _wait_for_call(mock_backend)
    args, _ = mock_backend.call_args
    assert args[2] == "jpeg"  # target format
    assert args[7] is False  # no merge
    assert args[8] is False  # no concat
    assert args[9] is None  # no specified resolution


def test_job_is_not_accessible_from_another_session(client, tmp_storage):
    # job_id is bound to the session that created it, and cannot be accessed from another session
    tok = _csrf_for(client)
    with mock.patch.object(w, "send_to_backend"):
        response = client.post(
            "/convert",
            data={
                "files": [(io.BytesIO(b"pngdata"), "photo.png")],
                "conversionType": "jpeg",
                "csrf_token": tok,
            },
            content_type="multipart/form-data",
        )
    job_id = response.get_json()["job_id"]

    other_client = w.app.test_client()
    assert other_client.get(f"/progress/{job_id}").status_code == 404
    assert other_client.get(f"/download/{job_id}").status_code == 404


def test_upload_file_count_is_bounded(client, tmp_storage):
    # Reject requests with too many files, and does not create any job storage
    tok = _csrf_for(client)
    files = [
        (io.BytesIO(b"pngdata"), f"photo-{index}.png")
        for index in range(w.app.config["MAX_UPLOAD_FILES"] + 1)
    ]

    response = client.post(
        "/convert",
        data={"files": files, "conversionType": "jpeg", "csrf_token": tok},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert not list(tmp_storage.glob("uploads_*"))
    assert not list(tmp_storage.glob("converted_*"))


def test_upload_file_size_is_bounded(client, tmp_storage, monkeypatch):
    # Reject requests with too large files, doen't create job storage
    tok = _csrf_for(client)
    monkeypatch.setitem(w.app.config, "MAX_UPLOAD_FILE_SIZE", 4)

    response = client.post(
        "/convert",
        data={
            "files": [(io.BytesIO(b"12345"), "photo.png")],
            "conversionType": "jpeg",
            "csrf_token": tok,
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 413
    assert not list(tmp_storage.glob("uploads_*"))
    assert not list(tmp_storage.glob("converted_*"))


def test_request_size_is_bounded_before_job_storage(client, tmp_storage, monkeypatch):
    # Reject requests with too large total request size, doesn't create job storage
    tok = _csrf_for(client)
    monkeypatch.setitem(w.app.config, "MAX_CONTENT_LENGTH", 4)

    response = client.post(
        "/convert",
        data={
            "files": [(io.BytesIO(b"12345"), "photo.png")],
            "conversionType": "jpeg",
            "csrf_token": tok,
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 413
    assert not list(tmp_storage.glob("uploads_*"))
    assert not list(tmp_storage.glob("converted_*"))


def test_conversion_queue_rejects_before_creating_job_storage(
    client, tmp_storage, monkeypatch
):
    # Reject request before creating job storage on full conversion queue
    tok = _csrf_for(client)
    full_queue = mock.Mock()
    full_queue.acquire.return_value = False
    monkeypatch.setattr(w, "_job_slots", full_queue)

    response = client.post(
        "/convert",
        data={
            "files": [(io.BytesIO(b"pngdata"), "photo.png")],
            "conversionType": "jpeg",
            "csrf_token": tok,
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 429
    assert not list(tmp_storage.glob("uploads_*"))
    assert not list(tmp_storage.glob("converted_*"))
    full_queue.acquire.assert_called_once_with(blocking=False)
    full_queue.release.assert_not_called()


def test_completed_job_storage_is_removed_after_retention(
    client, tmp_storage, monkeypatch
):
    # Completed job storage removed after retention period
    tok = _csrf_for(client)
    with mock.patch.object(w, "send_to_backend"):
        response = client.post(
            "/convert",
            data={
                "files": [(io.BytesIO(b"pngdata"), "photo.png")],
                "conversionType": "jpeg",
                "csrf_token": tok,
            },
            content_type="multipart/form-data",
        )
    job_id = response.get_json()["job_id"]
    record = w._get_job_record(job_id)
    assert record is not None
    record.update(status="done", completed_at=0)

    monkeypatch.setitem(w.app.config, "JOB_RETENTION_SECONDS", 1)
    w._cleanup_expired_jobs()

    assert not (tmp_storage / f"uploads_{job_id}").exists()
    assert not (tmp_storage / f"converted_{job_id}").exists()
    assert w._get_job_record(job_id) is None


def test_job_id_collision_does_not_merge_storage(client, tmp_storage, monkeypatch):
    # If generated job_id collides with an existing upload/converted directory,
    # new job gets different id and does not merge with existing data
    fixed_id = "a" * 32
    colliding_upload_dir = tmp_storage / "uploads_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    colliding_output_dir = tmp_storage / "converted_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    colliding_upload_dir.mkdir()
    colliding_output_dir.mkdir()
    (colliding_upload_dir / "existing.png").write_bytes(b"existing")

    token = _csrf_for(client)
    generated_ids = iter([fixed_id, "b" * 32])
    monkeypatch.setattr(w.secrets, "token_hex", lambda _: next(generated_ids))
    with mock.patch.object(w, "send_to_backend"):
        response = client.post(
            "/convert",
            data={
                "files": [(io.BytesIO(b"new"), "new.png")],
                "conversionType": "jpeg",
                "csrf_token": token,
            },
            content_type="multipart/form-data",
        )

    assert response.get_json()["job_id"] == "b" * 32
    assert (colliding_upload_dir / "existing.png").read_bytes() == b"existing"
    assert (tmp_storage / "uploads_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb").is_dir()
