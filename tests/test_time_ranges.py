import pytest

from core.utils.time_ranges import (
    parse_split_points,
    parse_time_value,
    parse_trim_range,
    plan_time_segments,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30", 30.0),
        ("1:45", 105.0),
        ("01:02:03.5", 3723.5),
        ("0", 0.0),
    ],
)
def test_parse_time_value_accepts_supported_formats(value, expected):
    assert parse_time_value(value) == expected


@pytest.mark.parametrize("value", ["", "-1", "1:60", "1:2:60", "abc", "1::2"])
def test_parse_time_value_rejects_invalid_formats(value):
    assert parse_time_value(value) is None


def test_parse_trim_range_supports_open_ends_and_end_keyword():
    assert parse_trim_range("00:00:30-00:01:45") == (30.0, 105.0)
    assert parse_trim_range("30-") == (30.0, None)
    assert parse_trim_range("-45") == (0.0, 45.0)
    assert parse_trim_range("30-end") == (30.0, None)


def test_parse_trim_range_rejects_invalid_ranges():
    assert parse_trim_range("10-5") is None
    assert parse_trim_range("abc-def") is None
    assert parse_trim_range("30") is None


def test_parse_split_points_sorts_and_deduplicates():
    assert parse_split_points("120,60;60") == [60.0, 120.0]


def test_parse_split_points_rejects_invalid_points():
    assert parse_split_points("0,60") is None
    assert parse_split_points("60,,120") is None
    assert parse_split_points("abc") is None


def test_plan_time_segments_for_trim_and_split():
    assert plan_time_segments(10, trim=(2, 5)) == [(2, 5)]
    assert plan_time_segments(10, trim=(2, None)) == [(2, 10)]
    assert plan_time_segments(10, split_at=[4, 7]) == [
        (0.0, 4.0),
        (4.0, 7.0),
        (7.0, 10.0),
    ]


def test_plan_time_segments_drops_out_of_range_split_points():
    assert plan_time_segments(10, split_at=[4, 20]) == [(0.0, 4.0), (4.0, 10.0)]
    assert plan_time_segments(10, split_at=[20]) == []
