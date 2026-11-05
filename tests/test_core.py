import os
import logging
import pytest
from utils.category import Category
from tests.test_fixtures import controller_instance, test_input_folder


def test_supported_formats(controller_instance):
    assert isinstance(controller_instance.supported_formats, list)
    assert len(controller_instance.supported_formats) > 0


def test_audio_bitrate(controller_instance):
    # Kind of nonsensical, I know, but it is a low-level structural test anyway
    assert controller_instance._audio_bitrate("mp3", "high") == "320k"
    assert controller_instance._audio_bitrate("flac", "medium") == "320k"
    assert controller_instance._audio_bitrate("ogg", "low") == "128k"
    assert controller_instance._audio_bitrate("mp3", "medium") == "192k"
    assert controller_instance._audio_bitrate("invalid_format", "medium") == "192k"


def test_get_file_paths_valid_input_files(controller_instance, tmp_path):
    movie_path = tmp_path / "test_movie.mp4"
    image_path = tmp_path / "test_image.jpg"
    movie_path.touch()
    image_path.touch()
    file_paths = controller_instance.file_handler.get_file_paths(
        input=str(tmp_path), supported_formats=controller_instance._supported_formats
    )

    assert isinstance(file_paths, dict)
    assert len(file_paths[Category.IMAGE]) == 1
    assert len(file_paths[Category.MOVIE]) == 1
    assert Category.IMAGE in file_paths
    assert Category.MOVIE in file_paths


def test_get_file_paths_skips_directories_named_like_media(
    controller_instance, tmp_path
):
    (tmp_path / "folder.mp3").mkdir()
    (tmp_path / "real.mp3").write_bytes(b"\x00" * 128)
    file_paths = controller_instance.file_handler.get_file_paths(
        input=str(tmp_path), supported_formats=controller_instance._supported_formats
    )
    assert [path[1] for path in file_paths[Category.AUDIO]] == ["real"]


def test_join_back_method(controller_instance, test_input_folder):
    file_path_set = ((str(test_input_folder) + "/"), "test_file", "mp4")
    assert controller_instance.file_handler.join_back(file_path_set) == str(
        test_input_folder / "test_file.mp4"
    )


def test_join_back_recovers_capitalized_extension(controller_instance, tmp_path):
    source = tmp_path / "Recovery - High Alert DEMO.MP3"
    source.write_bytes(b"\x00" * 128)
    file_paths = controller_instance.file_handler.get_file_paths(
        input=str(tmp_path), supported_formats=controller_instance._supported_formats
    )
    audio_set = file_paths[Category.AUDIO][0]
    assert audio_set[2] == "mp3"
    assert controller_instance.file_handler.join_back(audio_set) == str(source)


@pytest.mark.parametrize("across", [False, True])
def test_multi_input_no_output_does_not_crash(controller_instance, tmp_path, across):
    d1 = tmp_path / "dir1"
    d2 = tmp_path / "dir2"
    d1.mkdir()
    d2.mkdir()
    (d1 / "a.mp3").write_bytes(b"\x00" * 128)
    (d2 / "b.mp3").write_bytes(b"\x00" * 128)

    with pytest.raises(ValueError):
        controller_instance.run(
            input_path_args=[str(d1), str(d2)],
            format="wav",
            output=None,
            framerate=None,
            quality=None,
            split=None,
            merge=False,
            concat=False,
            delete=False,
            across=across,
            recursive=False,
            dropzone=False,
            language=None,
            workers=1,
        )


def test_run_releases_claims_after_failed_conversion(
    controller_instance, tmp_path, monkeypatch
):
    src = tmp_path / "clip.mp3"
    src.write_bytes(b"\x00" * 128)
    out = tmp_path / "out"
    out.mkdir()
    handler = controller_instance.file_handler
    claimed = {}

    def claim_then_fail(file_paths, formats):
        claimed["path"] = handler._resolve_output_file_conflict(str(out / "clip.mp3"))
        raise RuntimeError("boom")

    monkeypatch.setattr(controller_instance, "_dispatch_targets", claim_then_fail)

    with pytest.raises(RuntimeError):
        controller_instance.run(
            input_path_args=[str(src)],
            format=["mp3"],
            output=str(out),
            framerate=None,
            quality=None,
            split=None,
            merge=False,
            concat=False,
            delete=False,
            across=False,
            recursive=False,
            dropzone=False,
            language=None,
            workers=1,
        )

    assert handler._job_claims == set()
    assert handler._resolve_output_file_conflict(claimed["path"]) == claimed["path"]
    handler.release_job_claims()  # keep the global registry clean


def test_run_completes_when_one_file_fails(controller_instance, tmp_path, monkeypatch):
    src = tmp_path / "clip.mp3"
    src.write_bytes(b"\x00" * 128)
    out = tmp_path / "out"
    out.mkdir()
    handler = controller_instance.file_handler

    def dispatch_with_one_failure(file_paths, formats):
        good_output = out / "good.mp3"
        good_output.write_bytes(b"ok")
        handler._run_outputs.add(str(good_output))
        logging.getLogger("core").error("one file failed")

    monkeypatch.setattr(
        controller_instance, "_dispatch_targets", dispatch_with_one_failure
    )

    controller_instance.run(
        input_path_args=[str(src)],
        format=["mp3"],
        output=str(out),
        framerate=None,
        quality=None,
        split=None,
        merge=False,
        concat=False,
        delete=False,
        across=False,
        recursive=False,
        dropzone=False,
        language=None,
        workers=1,
    )

    assert handler.has_run_outputs()


def test_recursive_with_file_input_does_not_crash(
    controller_instance, tmp_path, monkeypatch
):
    src = tmp_path / "clip.mp3"
    src.write_bytes(b"\x00" * 128)
    dispatched = []
    monkeypatch.setattr(
        controller_instance,
        "_dispatch_targets",
        lambda file_paths, formats: dispatched.append(file_paths),
    )
    controller_instance.run(
        input_path_args=[str(src)],
        format=["wav"],
        output=str(tmp_path / "out"),
        framerate=None,
        quality=None,
        split=None,
        merge=False,
        concat=False,
        delete=False,
        across=False,
        recursive=True,
        dropzone=False,
        language=None,
        workers=1,
    )

    assert dispatched
    assert (str(tmp_path) + os.sep, "clip", "mp3") in dispatched[0][Category.AUDIO]


def test_recursive_run_closes_scandir_iterator(
    controller_instance, tmp_path, monkeypatch
):
    root = tmp_path / "src1"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "note.txt").write_text("not media")
    other = tmp_path / "src2"
    other.mkdir()
    (other / "note2.txt").write_text("not media")

    real_scandir = os.scandir
    created = []

    class RecordingScandir:
        def __init__(self, path):
            self.path = os.fspath(path)
            self._inner = real_scandir(path)
            self.closed = False
            created.append(self)

        def __iter__(self):
            return self

        def __next__(self):
            return next(self._inner)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.close()

        def close(self):
            self.closed = True
            self._inner.close()

    monkeypatch.setattr(os, "scandir", RecordingScandir)

    controller_instance.run(
        input_path_args=[str(root), str(other)],
        format=None,
        output=str(tmp_path / "out"),
        framerate=None,
        quality=None,
        split=None,
        merge=False,
        concat=False,
        delete=False,
        across=False,
        recursive=True,
        dropzone=False,
        language=None,
        workers=1,
    )

    for path in (str(root), str(other)):
        direct = next(s for s in created if s.path == path)
        assert direct.closed


def test_across_mode_does_not_warn_about_missing_media(
    controller_instance, tmp_path, caplog
):
    # Across mode converts all inputs in one go
    from PIL import Image

    dir1 = tmp_path / "dir1"
    dir2 = tmp_path / "dir2"
    out = tmp_path / "out"
    dir1.mkdir()
    dir2.mkdir()
    out.mkdir()
    Image.new("RGB", (4, 4), "red").save(dir1 / "first.png")
    Image.new("RGB", (4, 4), "blue").save(dir2 / "second.png")

    with caplog.at_level(logging.WARNING, logger="core.controller"):
        controller_instance.run(
            input_path_args=[str(dir1), str(dir2)],
            format="webp",
            output=str(out),
            framerate=None,
            quality=None,
            split=None,
            merge=False,
            concat=False,
            delete=False,
            across=True,
            recursive=False,
            dropzone=False,
            language=None,
            workers=1,
        )

    assert list(out.rglob("*.webp")), "no converted file was produced"
    assert "No convertible media files" not in caplog.text


def test_across_mode_still_warns_when_no_media_is_found(
    controller_instance, tmp_path, caplog
):
    dir1 = tmp_path / "dir1"
    dir2 = tmp_path / "dir2"
    out = tmp_path / "out"
    dir1.mkdir()
    dir2.mkdir()
    out.mkdir()

    with caplog.at_level(logging.WARNING, logger="core.controller"):
        controller_instance.run(
            input_path_args=[str(dir1), str(dir2)],
            format="webp",
            output=str(out),
            framerate=None,
            quality=None,
            split=None,
            merge=False,
            concat=False,
            delete=False,
            across=True,
            recursive=False,
            dropzone=False,
            language=None,
            workers=1,
        )

    assert "No convertible media files" in caplog.text


def test_across_recursive_keeps_files_of_every_input(controller_instance, tmp_path):
    from PIL import Image

    dir1 = tmp_path / "dir1"
    dir2 = tmp_path / "dir2"
    out = tmp_path / "out"
    (dir1 / "sub").mkdir(parents=True)
    (dir2 / "sub").mkdir(parents=True)
    out.mkdir()
    Image.new("RGB", (4, 4), "red").save(dir1 / "sub" / "first.png")
    Image.new("RGB", (4, 4), "blue").save(dir2 / "top.png")
    Image.new("RGB", (4, 4), "green").save(dir2 / "sub" / "second.png")

    controller_instance.run(
        input_path_args=[str(dir1), str(dir2)],
        format="webp",
        output=str(out),
        framerate=None,
        quality=None,
        split=None,
        merge=False,
        concat=False,
        delete=False,
        across=True,
        recursive=True,
        dropzone=False,
        language=None,
        workers=1,
    )

    produced = sorted(p.name for p in out.rglob("*.webp"))
    assert produced == ["first.webp", "second.webp", "top.webp"]


def test_recursive_scan_skips_generated_protocol_dirs(controller_instance, tmp_path):
    from unittest import mock
    from PIL import Image

    root = tmp_path / "media"
    (root / "sub").mkdir(parents=True)
    (root / "clip_hls" / "426x240").mkdir(parents=True)
    (root / "clip_hls" / "master.m3u8").write_text("#EXTM3U\n")
    (root / "clip_hls" / "426x240" / "426x240_000.ts").touch()
    (root / "clip_dash").mkdir()
    (root / "clip_dash" / "manifest.mpd").write_text("<MPD/>")
    (root / "clip_dash" / "init.mp4").touch()
    Image.new("RGB", (4, 4), "red").save(root / "sub" / "good.png")
    out = tmp_path / "out"
    out.mkdir()

    scanned_roots = []
    real_get_file_paths = controller_instance.file_handler.get_file_paths

    def spy(input_path, file_paths=None, supported_formats=None):
        scanned_roots.append(str(input_path))
        return real_get_file_paths(input_path, file_paths, supported_formats)

    with mock.patch.object(
        controller_instance.file_handler, "get_file_paths", side_effect=spy
    ):
        controller_instance.run(
            input_path_args=[str(root)],
            format="webp",
            output=str(out),
            framerate=None,
            quality=None,
            split=None,
            merge=False,
            concat=False,
            delete=False,
            across=False,
            recursive=True,
            dropzone=False,
            language=None,
            workers=1,
        )

    assert not any("_hls" in path or "_dash" in path for path in scanned_roots)
    assert (out / "good.webp").exists()


def test_run_does_not_count_another_jobs_errors(tmp_path):
    import threading

    from core.controller import Controller

    a_in = tmp_path / "a_in"
    b_in = tmp_path / "b_in"
    a_out = tmp_path / "a_out"
    b_out = tmp_path / "b_out"
    for path in (a_in, b_in, a_out, b_out):
        path.mkdir()
    (a_in / "a.mp3").touch()
    (b_in / "b.mp3").touch()

    a_controller = Controller(locale="English")
    b_controller = Controller(locale="English")
    a_ready = threading.Event()
    b_logged = threading.Event()

    def a_dispatch(file_paths, formats):
        a_ready.set()
        assert b_logged.wait(5), "job B never logged its error"

    def b_dispatch(file_paths, formats):
        assert a_ready.wait(5), "job A never started"
        logging.getLogger("core").error("job B failure")
        b_logged.set()
        good_output = b_out / "good.wav"
        good_output.write_bytes(b"ok")
        b_controller.file_handler._run_outputs.add(str(good_output))

    a_controller._dispatch_targets = a_dispatch
    b_controller._dispatch_targets = b_dispatch
    errors = {}

    def run_job(name, controller, input_dir, output_dir):
        try:
            controller.run(
                input_path_args=[str(input_dir)],
                format=["wav"],
                output=str(output_dir),
                framerate=None,
                quality=None,
                split=None,
                merge=False,
                concat=False,
                delete=False,
                across=False,
                recursive=False,
                dropzone=False,
                language=None,
                workers=1,
            )
        except BaseException as exc:
            errors[name] = exc

    threads = [
        threading.Thread(target=run_job, args=("a", a_controller, a_in, a_out)),
        threading.Thread(target=run_job, args=("b", b_controller, b_in, b_out)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert all(not thread.is_alive() for thread in threads)
    assert "a" not in errors, f"job A wrongly failed: {errors.get('a')}"
    assert "b" not in errors
    assert not a_controller.file_handler.has_run_outputs()
    assert b_controller.file_handler.has_run_outputs()


def test_run_counts_errors_logged_by_parallel_workers(controller_instance, tmp_path):
    from core.utils.file_handler import run_parallel

    src = tmp_path / "clip.mp3"
    src.write_bytes(b"\x00" * 128)
    out = tmp_path / "out"
    out.mkdir()

    def dispatch_with_worker_errors(file_paths, formats):
        run_parallel(
            [1, 2],
            lambda _: logging.getLogger("core").error("worker failure"),
            2,
        )

    controller_instance._dispatch_targets = dispatch_with_worker_errors

    with pytest.raises(SystemExit):
        controller_instance.run(
            input_path_args=[str(src)],
            format=["wav"],
            output=str(out),
            framerate=None,
            quality=None,
            split=None,
            merge=False,
            concat=False,
            delete=False,
            across=False,
            recursive=False,
            dropzone=False,
            language=None,
            workers=1,
        )
