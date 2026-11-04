import importlib.util
import platform
import re
import shutil
import subprocess
import sys

from dataclasses import dataclass

from PIL import Image
from utils.category import Category


_FFMPEG_PROBE_TIMEOUT = 20
_FFMPEG_ENCODER_RE = re.compile(r"^\s*[VAS][FSXBD.]{5}\s+(\S+)")
_FFMPEG_MUXER_RE = re.compile(r"^\s*[D ]?E\s+(\S+)(?:\s|$)")

_DOCUMENT_MODULES = (
    "pymupdf",
    "docx",
    "pptx",
    "mammoth",
    "markdownify",
    "reportlab",
    "weasyprint",
)

_DOCUMENT_REQUIREMENTS = {
    "md": ("mammoth", "markdownify", "docx", "pptx", "pymupdf"),
    "pdf": ("pymupdf",),
    "docx": ("docx", "pymupdf"),
    "pptx": ("pptx", "pymupdf"),
    "srt": (),
}

_DEPENDENCY_NAMES = {
    "pymupdf": "PyMuPDF",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "mammoth": "mammoth",
    "markdownify": "markdownify",
    "reportlab": "reportlab",
    "weasyprint": "weasyprint",
}

_CATEGORY_LABELS = {
    Category.AUDIO: "Audio",
    Category.IMAGE: "Image",
    Category.MOVIE: "Video",
    Category.DOCUMENT: "Document",
    Category.MOVIE_CODECS: "Video codecs",
    Category.PROTOCOLS: "Protocols",
}


@dataclass(frozen=True)
class FFmpegCapabilities:
    available: bool
    encoders: frozenset = frozenset()
    muxers: frozenset = frozenset()
    error: str = None


@dataclass(frozen=True)
class FormatCapability:
    name: str
    category: Category
    available: bool
    reason: str = None
    note: str = None

    @property
    def status(self) -> str:
        return "available" if self.available else "unavailable"


def parse_ffmpeg_encoders(output: str) -> frozenset:
    encoders = set()
    for line in output.splitlines():
        match = _FFMPEG_ENCODER_RE.match(line)
        if match is not None and match.group(1) != "=":
            encoders.add(match.group(1))
    return frozenset(encoders)


def parse_ffmpeg_muxers(output: str) -> frozenset:
    return frozenset(
        match.group(1)
        for line in output.splitlines()
        if (match := _FFMPEG_MUXER_RE.match(line))
    )


def probe_ffmpeg() -> FFmpegCapabilities:
    executable = shutil.which("ffmpeg")
    if executable is None:
        return FFmpegCapabilities(False, error="ffmpeg executable not found")

    def _probe(flag: str):
        try:
            completed = subprocess.run(
                [executable, "-hide_banner", flag],
                capture_output=True,
                text=True,
                timeout=_FFMPEG_PROBE_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return None, f"could not run ffmpeg {flag.lstrip('-')}: {exc}"
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "").strip().splitlines()
            detail = f": {details[-1]}" if details else ""
            return None, f"ffmpeg {flag.lstrip('-')} probe failed{detail}"
        return "\n".join(
            part for part in (completed.stdout, completed.stderr) if part
        ), None

    encoder_output, error = _probe("-encoders")
    if error is not None:
        return FFmpegCapabilities(False, error=error)

    muxer_output, error = _probe("-muxers")
    if error is not None:
        return FFmpegCapabilities(False, error=error)

    return FFmpegCapabilities(
        True,
        encoders=parse_ffmpeg_encoders(encoder_output),
        muxers=parse_ffmpeg_muxers(muxer_output),
    )


def _module_available(name: str) -> bool:
    if name in sys.modules:
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
        return False


def _installed_document_modules() -> frozenset:
    modules = {
        name for name in _DOCUMENT_MODULES if _module_available(name)
    }
    try:
        from core.converter import doc_converter

        if doc_converter.HTML is None:
            modules.discard("weasyprint")
    except Exception:
        modules.discard("weasyprint")
    return frozenset(modules)


def _image_writer_bundle():
    from core.converter import image_converter

    Image.init()
    return (
        image_converter._save_format,
        frozenset(Image.SAVE),
        image_converter.pillow_heif is not None,
    )


def _encoder_capability(codec: str, ffmpeg: FFmpegCapabilities):
    if not ffmpeg.available:
        return False, ffmpeg.error or "ffmpeg executable not found"
    if codec not in ffmpeg.encoders:
        return False, f"missing encoder: {codec}"
    return True, None


def _image_capability(
    name: str,
    save_format,
    save_formats: frozenset,
    pillow_heif_available: bool,
):
    target = save_format(name)
    if name in ("heic", "heif", "avif"):
        if not pillow_heif_available:
            return False, "missing optional dependency: pillow-heif"
        if target not in save_formats:
            return False, f"missing Pillow encoder: {target}"
        return True, None
    if target in save_formats:
        return True, None
    return False, f"missing Pillow encoder: {target}"


def _document_capability(
    name: str,
    modules: frozenset,
    ffmpeg: FFmpegCapabilities,
    system_platform: str,
):
    if name == "srt":
        available, reason = _encoder_capability("srt", ffmpeg)
        return available, reason, None

    missing = [
        module for module in _DOCUMENT_REQUIREMENTS.get(name, ())
        if module not in modules
    ]
    if missing:
        missing_names = ", ".join(
            _DEPENDENCY_NAMES.get(module, module) for module in missing
        )
        return False, f"missing dependency: {missing_names}", None

    note = None
    if name == "pdf" and (
        "weasyprint" not in modules or system_platform == "Windows"
    ):
        if "reportlab" not in modules:
            return (
                False,
                "missing optional dependency: weasyprint "
                "(reportlab fallback is also unavailable)",
                None,
            )
        if system_platform == "Windows":
            note = (
                "platform restriction: weasyprint is unavailable on Windows; "
                "DOCX sources use reportlab fallback"
            )
        else:
            note = (
                "missing optional dependency: weasyprint; "
                "DOCX sources use reportlab fallback"
            )
    return True, None, note


def _protocol_capability(name: str, protocol, ffmpeg: FFmpegCapabilities):
    if not ffmpeg.available:
        return False, ffmpeg.error or "ffmpeg executable not found"
    muxer = str(protocol[0])
    if muxer not in ffmpeg.muxers:
        return False, f"missing muxer: {muxer}"
    for codec in ("libx264", "aac"):
        if codec not in ffmpeg.encoders:
            return False, f"missing encoder: {codec}"
    return True, None


def collect_format_capabilities(
    supported_formats: dict,
    *,
    ffmpeg: FFmpegCapabilities = None,
    pillow_save_formats: frozenset = None,
    pillow_heif_available: bool = None,
    document_modules: frozenset = None,
    system_platform: str = None,
) -> list:
    ffmpeg = probe_ffmpeg() if ffmpeg is None else ffmpeg
    document_modules = (
        _installed_document_modules()
        if document_modules is None
        else document_modules
    )
    system_platform = platform.system() if system_platform is None else system_platform

    if pillow_save_formats is None or pillow_heif_available is None:
        save_format, detected_formats, detected_heif = _image_writer_bundle()
        save_formats = (
            detected_formats if pillow_save_formats is None else pillow_save_formats
        )
        heif_available = (
            detected_heif if pillow_heif_available is None else pillow_heif_available
        )
    else:
        from core.converter.image_converter import _save_format

        save_format = _save_format
        save_formats = pillow_save_formats
        heif_available = pillow_heif_available

    capabilities = []
    for category in Category:
        for name, info in supported_formats.get(category, {}).items():
            reason = None
            note = None
            if category == Category.AUDIO:
                available, reason = _encoder_capability(info, ffmpeg)
            elif category == Category.IMAGE:
                available, reason = _image_capability(
                    name, save_format, save_formats, heif_available
                )
            elif category in (Category.MOVIE, Category.MOVIE_CODECS):
                available, reason = _encoder_capability(info[0], ffmpeg)
            elif category == Category.DOCUMENT:
                available, reason, note = _document_capability(
                    name, document_modules, ffmpeg, system_platform
                )
            elif category == Category.PROTOCOLS:
                available, reason = _protocol_capability(name, info, ffmpeg)
            else:
                available, reason = True, None

            capabilities.append(
                FormatCapability(
                    name=name,
                    category=category,
                    available=available,
                    reason=reason,
                    note=note,
                )
            )
    return capabilities


def render_format_capabilities(capabilities: list) -> str:
    lines = ["Target format capabilities on this system:", ""]
    by_category = {category: [] for category in Category}
    for capability in capabilities:
        by_category.setdefault(capability.category, []).append(capability)

    for category in Category:
        category_capabilities = by_category.get(category, [])
        if not category_capabilities:
            continue
        available_count = sum(
            1 for capability in category_capabilities if capability.available
        )
        lines.append(
            f"{_CATEGORY_LABELS.get(category, category.value)} "
            f"({available_count}/{len(category_capabilities)} available):"
        )
        for capability in category_capabilities:
            details = [
                detail
                for detail in (capability.reason, capability.note)
                if detail
            ]
            suffix = f" - {'; '.join(details)}" if details else ""
            lines.append(
                f"  {capability.name:<12} {capability.status}{suffix}"
            )
        lines.append("")

    available_count = sum(1 for capability in capabilities if capability.available)
    lines.append(
        f"{available_count}/{len(capabilities)} targets available on this system."
    )
    return "\n".join(lines)
