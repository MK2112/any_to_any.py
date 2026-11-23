from __future__ import annotations

from pathlib import Path

_EXTENSION_TO_KIND: dict[str, str] = {}


def configure_formats(supported_formats: dict) -> None:
    global _EXTENSION_TO_KIND
    mapping: dict[str, str] = {}
    for category, formats in supported_formats.items():
        kind = getattr(category, "value", str(category)).lower()
        for extension in formats:
            mapping[str(extension).lower().lstrip(".")] = kind
    _EXTENSION_TO_KIND = mapping


def _ensure_configured() -> None:
    if _EXTENSION_TO_KIND:
        return
    from core.controller import Controller

    configure_formats(Controller()._supported_formats)


def kind_for(path: str) -> str:
    _ensure_configured()
    return _EXTENSION_TO_KIND.get(Path(path).suffix.lstrip(".").lower(), "other")


def is_image(path: str) -> bool:
    return kind_for(path) == "image"


def is_movie(path: str) -> bool:
    return kind_for(path) == "movie"


def is_audio(path: str) -> bool:
    return kind_for(path) == "audio"
