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


def test_multi_input_no_output_does_not_crash(controller_instance, tmp_path):
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
            across=False,
            recursive=False,
            dropzone=False,
            language=None,
            workers=1,
        )


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
