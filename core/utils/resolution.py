def normalize_resolution(res_aliases, res_all, resolution: str) -> str | None:
    # Resolve alias like '1080p' or 'WxH' string to 'WxH' form
    if not resolution:
        return None
    value = str(resolution).strip().lower()
    if value in res_aliases:
        return res_aliases[value]
    elif value in res_all:
        return value
    return None


def available_resolutions(supported_formats_category: dict, format: str) -> list:
    # Sorted list (largest first) of resolutions allowed for given format
    resolutions = supported_formats_category.get(format)
    if not resolutions:
        return []
    allowed = next((item for item in resolutions if isinstance(item, frozenset)), None)
    if not allowed:
        return []
    return sorted(
        allowed,
        key=lambda res: tuple(int(part) for part in res.split("x")),
        reverse=True,
    )


def resolution_allowed(
    supported_formats_category: dict, format: str, resolution: str
) -> bool:
    # Check if given resolution is allowed for given format
    return resolution in available_resolutions(supported_formats_category, format)


def resolution_size(resolution: str) -> tuple:
    width, height = resolution.split("x")
    return int(width), int(height)


def parse_resolution(resolution: str) -> tuple:
    # Convert a canonical 'WxH' string to (width, height).
    try:
        return resolution_size(resolution)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Unknown resolution: {resolution}") from exc
