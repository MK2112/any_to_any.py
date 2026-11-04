import math


def parse_time_value(value) -> float | None:
    if value is None:
        return None
    token = str(value).strip()
    if not token:
        return None
    try:
        if ":" not in token:
            seconds = float(token)
            return seconds if math.isfinite(seconds) and seconds >= 0 else None
        parts = token.split(":")
        if len(parts) not in (2, 3) or any(not part.strip() for part in parts):
            return None
        numbers = [float(part) for part in parts]
        if any(not math.isfinite(number) or number < 0 for number in numbers):
            return None
        if any(number >= 60 for number in numbers[1:]):
            return None
        if len(numbers) == 2:
            minutes, seconds = numbers
            return minutes * 60 + seconds
        hours, minutes, seconds = numbers
        return hours * 3600 + minutes * 60 + seconds
    except (TypeError, ValueError):
        return None


def parse_trim_range(value) -> tuple[float, float | None] | None:
    if isinstance(value, (tuple, list)):
        if len(value) != 2:
            return None
        start = parse_time_value(value[0])
        end = None if value[1] is None else parse_time_value(value[1])
        if start is None or (value[1] is not None and end is None) or (end is not None and end <= start):
            return None
        return (start, end)
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token or "-" not in token:
        return None
    start_token, end_token = token.split("-", 1)
    start = 0.0 if not start_token.strip() else parse_time_value(start_token)
    if start is None:
        return None
    if not end_token.strip() or end_token.strip().lower() in ("end", "rest"):
        end = None
    else:
        end = parse_time_value(end_token)
        if end is None:
            return None
    if end is not None and end <= start:
        return None
    return (start, end)


def parse_split_points(value) -> list[float] | None:
    if isinstance(value, (tuple, list)):
        tokens = list(value)
    elif isinstance(value, str):
        tokens = [token.strip() for token in value.replace(";", ",").split(",")]
        if not tokens or any(not token for token in tokens):
            return None
    else:
        return None
    points = []
    for token in tokens:
        point = parse_time_value(token)
        if point is None or point <= 0:
            return None
        points.append(point)
    points = sorted(set(points))
    return points or None


def normalize_trim(value):
    if value is None:
        return None
    if isinstance(value, str):
        return parse_trim_range(value)
    return parse_trim_range(value) if isinstance(value, (tuple, list)) else None


def normalize_split_points(value):
    if value is None:
        return None
    if isinstance(value, (str, tuple, list)):
        return parse_split_points(value)
    return None


def plan_time_segments(duration, trim=None, split_at=None) -> list[tuple] | None:
    trim = normalize_trim(trim)
    split_at = normalize_split_points(split_at)
    if trim is not None and split_at is not None:
        return None
    if trim is not None:
        start = trim[0]
        end = trim[1]
        if duration is not None:
            duration = max(float(duration), 0.0)
            if end is None:
                end = duration
            end = min(end, duration)
        if end is not None and end <= start:
            return []
        return [(start, end)]
    if split_at is not None:
        if duration is None or duration <= 0:
            return []
        cuts = sorted(point for point in split_at if 0 < point < duration)
        if not cuts:
            return []
        boundaries = [0.0] + cuts + [float(duration)]
        return [
            (boundaries[index], boundaries[index + 1])
            for index in range(len(boundaries) - 1)
        ]
    return None
