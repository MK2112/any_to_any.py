import io
import os
import re
import sys
import subprocess
import time
import threading
import zipfile
from concurrent.futures import Future
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
        w._job_owners.clear()
        w._job_records.clear()
    yield
    with w.progress_lock:
        w.shared_progress_dict.clear()
        w._last_progress_cache.clear()
        w._rate_limit.clear()


def test_web_paths_anchored_to_repo_directory():
    base = os.path.dirname(os.path.abspath(w.__file__))
    assert w.app.template_folder == os.path.join(base, "templates")
    assert w.app.config["UPLOADED_FILES_DEST"] == os.path.join(base, "uploads")
    assert w.app.config["CONVERTED_FILES_DEST"] == os.path.join(base, "converted")


@pytest.fixture
def client(reset_web_globals):
    return w.app.test_client()


@pytest.fixture
def tmp_storage(tmp_path, monkeypatch):
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


def test_convert_forwards_metadata_mode(client, tmp_storage):
    tok = _csrf_for(client)
    with mock.patch.object(w, "send_to_backend") as mock_backend:
        resp = client.post(
            "/convert",
            data={
                "files": [(io.BytesIO(b"pngdata"), "photo.png")],
                "conversionType": "jpeg",
                "metadataMode": "strip",
                "csrf_token": tok,
            },
            content_type="multipart/form-data",
        )
    assert resp.status_code == 202
    _wait_for_call(mock_backend)
    args, _ = mock_backend.call_args
    assert args[10] == "strip"


def test_invalid_metadata_mode_is_rejected(client, tmp_storage):
    tok = _csrf_for(client)
    response = client.post(
        "/convert",
        data={
            "files": [(io.BytesIO(b"pngdata"), "photo.png")],
            "conversionType": "jpeg",
            "metadataMode": "bogus",
            "csrf_token": tok,
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert not list(tmp_storage.glob("uploads_*"))
    assert not list(tmp_storage.glob("converted_*"))


def test_zip_excludes_metadata_sidecars(tmp_path):
    source = tmp_path / "converted_job"
    (source / ".metadata").mkdir(parents=True)
    (source / "track.mp3").write_bytes(b"audio")
    (source / ".metadata" / "track.mp3.hash.metadata.json").write_text("{}")

    zip_path = tmp_path / "download.zip"
    w._zip_without_metadata(str(source), str(zip_path))

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    assert "converted_job/track.mp3" in names
    assert not any(".metadata" in name for name in names)


def test_send_to_backend_applies_metadata_mode(tmp_path):
    controller = mock.MagicMock()
    controller.prog_logger.job_id = None
    controller.prog_logger.shared_progress_dict = None

    expected = {
        "none": (False, False),
        "preserve": (True, False),
        "strip": (False, True),
    }
    for index, (mode, flags) in enumerate(expected.items()):
        input_dir = tmp_path / f"input-{index}"
        input_dir.mkdir()
        w.send_to_backend(
            controller,
            [str(input_dir)],
            "mp3",
            str(tmp_path / f"output-{index}"),
            None,
            "high",
            None,
            False,
            False,
            None,
            mode,
        )
        kwargs = controller.run.call_args.kwargs
        assert (kwargs["preserve_meta"], kwargs["strip_meta"]) == flags


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


@pytest.mark.parametrize("endpoint", ["/convert", "/merge", "/concat"])
@pytest.mark.parametrize("names", [("a b.png", "a_b.png"), ("same.png", "same.png"),
                                   ("dir1/same.png", "dir1_same.png"),
                                   ("Photo.png", "photo.png")])
def test_colliding_upload_names_rejected_before_storage(client, tmp_storage, endpoint, names):
    tok = _csrf_for(client)
    with mock.patch.object(w, "send_to_backend") as backend:
        response = client.post(
            endpoint,
            data={"files": [(io.BytesIO(b"first"), names[0]),
                            (io.BytesIO(b"second"), names[1])],
                  "conversionType": "jpeg", "csrf_token": tok},
            content_type="multipart/form-data",
        )
    assert response.status_code == 400
    assert b"collide" in response.data
    assert not list(tmp_storage.glob("uploads_*"))
    assert not list(tmp_storage.glob("converted_*"))
    backend.assert_not_called()


def test_merge_preserves_distinct_matching_basenames(client, tmp_storage):
    tok = _csrf_for(client)
    with mock.patch.object(w, "send_to_backend") as backend:
        response = client.post(
            "/merge",
            data={"files": [(io.BytesIO(b"video"), "clip.mp4"),
                            (io.BytesIO(b"audio"), "clip.mp3")],
                  "conversionType": "mp4", "csrf_token": tok},
            content_type="multipart/form-data",
        )
        _wait_for_call(backend)
    assert response.status_code == 202
    upload_dir = backend.call_args.args[1][0]
    assert open(os.path.join(upload_dir, "clip.mp4"), "rb").read() == b"video"
    assert open(os.path.join(upload_dir, "clip.mp3"), "rb").read() == b"audio"


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


def test_fatal_exit_reaches_error_state_instead_of_polling_forever(client, tmp_storage):
    # Job must reach a terminal state or we infinitely GET /progress
    tok = _csrf_for(client)
    response = client.post(
        "/convert",
        data={
            "files": [(io.BytesIO(b"plain text"), "notes.txt")],
            "conversionType": "jpeg",
            "csrf_token": tok,
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202
    job_id = response.get_json()["job_id"]

    deadline = time.time() + 10
    while time.time() < deadline:
        data = client.get(f"/progress/{job_id}").get_json()
        if data["status"] in {"done", "error"}:
            break
        time.sleep(0.02)

    assert data["status"] == "error"
    assert data["error"]
    record = w._get_job_record(job_id)
    assert record["status"] == "error"
    assert record["completed_at"] > 0


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
    # Only the job-id draws are pinned; CSRF rotation may draw further tokens
    generated_ids = iter([fixed_id, "b" * 32])
    real_token_hex = w.secrets.token_hex

    def pinned_token_hex(_bytes):
        return next(generated_ids, None) or real_token_hex(_bytes)

    monkeypatch.setattr(w.secrets, "token_hex", pinned_token_hex)
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


def _convert_post(client, tok):
    # Small helper posting one image conversion with a CSRF token
    return client.post(
        "/convert",
        data={
            "files": [(io.BytesIO(b"pngdata"), "photo.png")],
            "conversionType": "jpeg",
            "csrf_token": tok,
        },
        content_type="multipart/form-data",
    )


def test_csrf_token_is_bound_to_the_session_not_the_ip(client, tmp_storage):
    # Two clients share the same remote address (as NAT neighbours would), yet
    # a token issued to one session must not validate from the other
    tok = _csrf_for(client)
    with mock.patch.object(w, "send_to_backend"):
        response = _convert_post(client, tok)
    assert response.status_code == 202

    other_client = w.app.test_client()
    uploads_before = sorted(p.name for p in tmp_storage.glob("uploads_*"))
    assert (
        other_client.post(
            "/convert",
            data={
                "files": [(io.BytesIO(b"pngdata"), "photo.png")],
                "conversionType": "jpeg",
                "csrf_token": tok,
            },
            content_type="multipart/form-data",
        ).status_code
        == 403
    )
    # A rejected request must not create any job storage
    assert sorted(p.name for p in tmp_storage.glob("uploads_*")) == uploads_before


def test_successful_submission_keeps_token_valid_for_parallel_tabs(client, tmp_storage):
    first_tok = _csrf_for(client)
    with mock.patch.object(w, "send_to_backend"):
        response = _convert_post(client, first_tok)
    assert response.status_code == 202
    returned = response.get_json()["csrf_token"]
    assert returned == first_tok
    with mock.patch.object(w, "send_to_backend"):
        response = _convert_post(client, first_tok)
    assert response.status_code == 202
    assert response.get_json()["csrf_token"] == first_tok


def test_csrf_rejects_malformed_payloads_without_500(client):
    tok = _csrf_for(client)
    assert client.post("/language", json=[]).status_code == 403
    assert client.post("/language", json=["not", "a", "dict"]).status_code == 403
    assert (
        client.post(
            "/language", json={"language": "de_DE", "csrf_token": ["bad"]}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/language", json={"language": "de_DE", "csrf_token": {"bad": "token"}}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/language", json={"language": "de_DE", "csrf_token": tok}
        ).status_code
        == 200
    )


def test_set_language_requires_a_valid_csrf_token(client):
    # A session-mutating POST without a token is rejected
    assert client.post("/language", json={"language": "de_DE"}).status_code == 403

    tok = _csrf_for(client)
    response = client.post("/language", json={"language": "de_DE", "csrf_token": tok})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["language"] == "German"

    # The choice is persisted in the session and served back on the next page
    assert 'lang="de"' in client.get("/").get_data(as_text=True)


def test_cancel_queued_job_auth_csrf_cleanup_and_slot(client, tmp_storage, monkeypatch):
    future = Future()
    executor = mock.Mock()
    executor.submit.return_value = future
    monkeypatch.setattr(w, "_job_executor", executor)
    slots = mock.Mock()
    slots.acquire.return_value = True
    monkeypatch.setattr(w, "_job_slots", slots)
    token = _csrf_for(client)
    response = _convert_post(client, token)
    job_id = response.get_json()["job_id"]
    other = w.app.test_client()
    other_token = _csrf_for(other)
    assert client.post(f"/cancel/{job_id}").status_code == 403
    assert other.post(f"/cancel/{job_id}", headers={"X-CSRF-Token": other_token}).status_code == 404
    assert not future.cancelled()
    result = client.post(f"/cancel/{job_id}", headers={"X-CSRF-Token": token})
    assert result.status_code == 200
    assert future.cancelled()
    assert client.get(f"/progress/{job_id}").get_json()["status"] == "cancelled"
    assert client.post(f"/cancel/{job_id}", headers={"X-CSRF-Token": token}).status_code == 200
    assert slots.release.call_count == 1
    assert (tmp_storage / f"uploads_{job_id}").is_dir()
    assert client.get(f"/download/{job_id}").status_code == 409
    monkeypatch.setitem(w.app.config, "JOB_RETENTION_SECONDS", 0)
    w._cleanup_expired_jobs()
    assert not (tmp_storage / f"uploads_{job_id}").exists()
    assert not (tmp_storage / f"converted_{job_id}").exists()


def test_cancel_running_job_waits_for_worker(client, tmp_storage, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    original = w.create_controller
    def make_controller(*args, **kwargs):
        controller = original(*args, **kwargs)
        if kwargs.get("job_id"):
            def run(**kwargs):
                started.set()
                assert release.wait(5)
                controller.file_handler.check_cancelled()
                finished.set()
            controller.run = run
        return controller
    monkeypatch.setattr(w, "create_controller", make_controller)
    token = _csrf_for(client)
    response = _convert_post(client, token)
    job_id = response.get_json()["job_id"]
    try:
        assert started.wait(5)
        assert client.post(f"/cancel/{job_id}", headers={"X-CSRF-Token": token}).status_code == 202
        assert client.get(f"/progress/{job_id}").get_json()["status"] == "cancelling"
        assert (tmp_storage / f"uploads_{job_id}" / "photo.png").exists()
        release.set()
        deadline = time.time() + 5
        while time.time() < deadline:
            if client.get(f"/progress/{job_id}").get_json()["status"] == "cancelled":
                break
            time.sleep(0.02)
        assert client.get(f"/progress/{job_id}").get_json()["status"] == "cancelled"
        assert not finished.is_set()
        assert (tmp_storage / f"uploads_{job_id}" / "photo.png").exists()
    finally:
        release.set()


def test_cancel_web_job_terminates_its_ffmpeg(client, tmp_storage, monkeypatch):
    ffmpeg = tmp_storage / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    try:
        os.symlink(sys.executable, ffmpeg)
    except OSError:
        import shutil
        shutil.copy2(sys.executable, ffmpeg)
    started = threading.Event()
    processes = []
    original = w.create_controller

    def make_controller(*args, **kwargs):
        controller = original(*args, **kwargs)
        if kwargs.get("job_id"):
            def run(**kwargs):
                process = subprocess.Popen([str(ffmpeg), "-c", "import time; time.sleep(30)"])
                processes.append(process)
                started.set()
                process.wait(timeout=10)
            controller.run = run
        return controller

    monkeypatch.setattr(w, "create_controller", make_controller)
    token = _csrf_for(client)
    job_id = _convert_post(client, token).get_json()["job_id"]
    try:
        assert started.wait(5)
        assert client.post(f"/cancel/{job_id}", headers={"X-CSRF-Token": token}).status_code == 202
        deadline = time.time() + 5
        while time.time() < deadline and client.get(f"/progress/{job_id}").get_json()["status"] != "cancelled":
            time.sleep(0.02)
        assert processes[0].poll() is not None
        assert client.get(f"/progress/{job_id}").get_json()["status"] == "cancelled"
    finally:
        if processes and processes[0].poll() is None:
            processes[0].kill()
            processes[0].wait()


def test_cancel_completed_job_returns_conflict(client, tmp_storage):
    token = _csrf_for(client)
    with mock.patch.object(w, "send_to_backend"):
        job_id = _convert_post(client, token).get_json()["job_id"]
    w._set_job_status(job_id, "done", time.time())
    assert client.post(f"/cancel/{job_id}", headers={"X-CSRF-Token": token}).status_code == 409
    assert client.get(f"/progress/{job_id}").get_json()["status"] == "done"


def test_open_browser_quietly_discards_browser_output(monkeypatch):
    # Handle Chromium-based browsers sometimes vomiting handoff/zygote noise into stdout/stderr
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return mock.Mock()

    monkeypatch.setattr(w.subprocess, "Popen", fake_popen)
    w._open_browser_quietly("http://127.0.0.1:5000")

    assert captured["cmd"][-1] == "http://127.0.0.1:5000"
    assert captured["cmd"][1] == "-c"
    assert "webbrowser.open" in captured["cmd"][2]
    assert captured["kwargs"]["stdin"] is w.subprocess.DEVNULL
    assert captured["kwargs"]["stdout"] is w.subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] is w.subprocess.DEVNULL
    assert captured["kwargs"]["start_new_session"] is True
