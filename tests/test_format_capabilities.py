from types import SimpleNamespace

from utils.category import Category
from core.utils.format_capabilities import (
    FFmpegCapabilities,
    collect_format_capabilities,
    parse_ffmpeg_encoders,
    parse_ffmpeg_muxers,
    probe_ffmpeg,
    render_format_capabilities,
)


def _supported_formats():
    return {
        Category.AUDIO: {
            "mp3": "libmp3lame",
            "flac": "flac",
        },
        Category.IMAGE: {
            "png": object(),
            "heic": object(),
        },
        Category.MOVIE: {
            "mp4": ["libx264", frozenset()],
        },
        Category.DOCUMENT: {
            "md": object(),
            "pdf": object(),
            "docx": object(),
            "pptx": object(),
            "srt": object(),
        },
        Category.MOVIE_CODECS: {
            "h264": ["libx264", "mp4", frozenset()],
            "h264_nvenc": ["h264_nvenc", "mp4", frozenset()],
        },
        Category.PROTOCOLS: {
            "hls": ["hls", "mkv", frozenset()],
            "dash": ["dash", "mkv", frozenset()],
        },
    }


def _modules(include_weasyprint=False):
    modules = {
        "pymupdf",
        "docx",
        "pptx",
        "mammoth",
        "markdownify",
        "reportlab",
    }
    if include_weasyprint:
        modules.add("weasyprint")
    return frozenset(modules)


def _capabilities_by_name(capabilities):
    return {capability.name: capability for capability in capabilities}


def test_parse_ffmpeg_encoder_and_muxer_output():
    encoder_output = """Encoders:
 V..... = Video
 A..... = Audio
 V....D libx264              libx264 H.264 / AVC
 A..... aac                  AAC (Advanced Audio Coding)
 S..... srt                  SubRip subtitle
"""
    muxer_output = """File formats:
 D. = Demuxing supported
 .E = Muxing supported
 --
  E mp4              MP4 (MPEG-4 Part 14)
  E matroska         Matroska
"""

    assert parse_ffmpeg_encoders(encoder_output) == frozenset(
        {"libx264", "aac", "srt"}
    )
    assert parse_ffmpeg_muxers(muxer_output) == frozenset({"mp4", "matroska"})


def test_probe_ffmpeg_missing_executable(monkeypatch):
    monkeypatch.setattr(
        "core.utils.format_capabilities.shutil.which", lambda name: None
    )

    capabilities = probe_ffmpeg()

    assert capabilities.available is False
    assert capabilities.error == "ffmpeg executable not found"


def test_probe_ffmpeg_reads_encoders_and_muxers(monkeypatch):
    outputs = {
        "-encoders": " V....D libx264   H.264\n A..... aac       AAC\n",
        "-muxers": "  E mp4           MP4\n  E hls           HLS\n",
    }

    def fake_run(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=outputs[command[2]],
            stderr="",
        )

    monkeypatch.setattr(
        "core.utils.format_capabilities.shutil.which",
        lambda name: "/usr/bin/ffmpeg",
    )
    monkeypatch.setattr(
        "core.utils.format_capabilities.subprocess.run", fake_run
    )

    capabilities = probe_ffmpeg()

    assert capabilities.available is True
    assert capabilities.encoders == frozenset({"libx264", "aac"})
    assert capabilities.muxers == frozenset({"mp4", "hls"})


def test_capabilities_mark_missing_encoder_dependency_and_muxer():
    ffmpeg = FFmpegCapabilities(
        True,
        encoders=frozenset({"libmp3lame", "libx264", "srt", "aac"}),
        muxers=frozenset({"hls"}),
    )

    capabilities = _capabilities_by_name(
        collect_format_capabilities(
            _supported_formats(),
            ffmpeg=ffmpeg,
            pillow_save_formats=frozenset({"PNG"}),
            pillow_heif_available=False,
            document_modules=_modules(),
            system_platform="Linux",
        )
    )

    assert capabilities["mp3"].available is True
    assert capabilities["flac"].reason == "missing encoder: flac"
    assert capabilities["png"].available is True
    assert capabilities["heic"].reason == (
        "missing optional dependency: pillow-heif"
    )
    assert capabilities["mp4"].available is True
    assert capabilities["h264_nvenc"].reason == (
        "missing encoder: h264_nvenc"
    )
    assert capabilities["hls"].available is True
    assert capabilities["dash"].reason == "missing muxer: dash"
    assert capabilities["pdf"].available is True
    assert "weasyprint" in capabilities["pdf"].note
    assert "reportlab fallback" in capabilities["pdf"].note
    assert capabilities["srt"].available is True


def test_capabilities_report_missing_document_dependencies():
    ffmpeg = FFmpegCapabilities(
        True,
        encoders=frozenset({"srt"}),
        muxers=frozenset(),
    )

    capabilities = _capabilities_by_name(
        collect_format_capabilities(
            _supported_formats(),
            ffmpeg=ffmpeg,
            pillow_save_formats=frozenset({"PNG", "HEIF"}),
            pillow_heif_available=True,
            document_modules=frozenset({"pymupdf", "reportlab"}),
            system_platform="Linux",
        )
    )

    assert capabilities["pdf"].available is True
    assert capabilities["md"].reason == (
        "missing dependency: mammoth, markdownify, python-docx, python-pptx"
    )
    assert capabilities["docx"].reason == "missing dependency: python-docx"
    assert capabilities["pptx"].reason == "missing dependency: python-pptx"


def test_capabilities_mark_ffmpeg_targets_unavailable_without_ffmpeg():
    ffmpeg = FFmpegCapabilities(False, error="ffmpeg executable not found")

    capabilities = _capabilities_by_name(
        collect_format_capabilities(
            _supported_formats(),
            ffmpeg=ffmpeg,
            pillow_save_formats=frozenset({"PNG", "HEIF"}),
            pillow_heif_available=True,
            document_modules=_modules(),
            system_platform="Linux",
        )
    )

    for name in ("mp3", "mp4", "h264", "hls", "dash", "srt"):
        assert capabilities[name].available is False
        assert capabilities[name].reason == "ffmpeg executable not found"


def test_pdf_notes_windows_weasyprint_restriction():
    ffmpeg = FFmpegCapabilities(
        True,
        encoders=frozenset({"srt"}),
        muxers=frozenset(),
    )

    capabilities = _capabilities_by_name(
        collect_format_capabilities(
            _supported_formats(),
            ffmpeg=ffmpeg,
            pillow_save_formats=frozenset({"PNG", "HEIF"}),
            pillow_heif_available=True,
            document_modules=_modules(include_weasyprint=True),
            system_platform="Windows",
        )
    )

    assert capabilities["pdf"].available is True
    assert "platform restriction" in capabilities["pdf"].note
    assert "weasyprint" in capabilities["pdf"].note


def test_render_capabilities_lists_statuses_and_reasons():
    ffmpeg = FFmpegCapabilities(
        True,
        encoders=frozenset({"libmp3lame", "libx264", "srt", "aac"}),
        muxers=frozenset({"hls"}),
    )
    capabilities = collect_format_capabilities(
        _supported_formats(),
        ffmpeg=ffmpeg,
        pillow_save_formats=frozenset({"PNG"}),
        pillow_heif_available=False,
        document_modules=_modules(),
        system_platform="Linux",
    )

    report = render_format_capabilities(capabilities)

    assert "Audio (" in report
    assert "mp3          available" in report
    assert "flac         unavailable - missing encoder: flac" in report
    assert (
        "heic         unavailable - missing optional dependency: pillow-heif"
        in report
    )
    assert "missing encoder: h264_nvenc" in report
    assert "Target format capabilities on this system:" in report
    assert "targets available on this system." in report


def test_heif_targets_require_pillow_heif_even_with_pillow_writer():
    ffmpeg = FFmpegCapabilities(True, encoders=frozenset(), muxers=frozenset())
    supported = {
        Category.IMAGE: {
            "avif": object(),
        }
    }

    capabilities = _capabilities_by_name(
        collect_format_capabilities(
            supported,
            ffmpeg=ffmpeg,
            pillow_save_formats=frozenset({"AVIF"}),
            pillow_heif_available=False,
            document_modules=frozenset(),
            system_platform="Linux",
        )
    )

    assert capabilities["avif"].available is False
    assert capabilities["avif"].reason == (
        "missing optional dependency: pillow-heif"
    )
