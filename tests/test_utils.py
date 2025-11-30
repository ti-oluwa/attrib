"""Tests for utility functions."""

import datetime
import re
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from attrib._utils import (
    is_generic_type,
    is_namedtuple,
    is_iterable,
    is_iterable_type,
    is_mapping,
    parse_duration,
    iso_parse,
    now,
    make_jsonable,
    coalesce,
)


class TestTypeChecking:
    """Test type checking utilities."""

    def test_is_generic_type(self):
        """Test is_generic_type function."""
        import typing

        assert is_generic_type(typing.List[int])
        assert is_generic_type(typing.Dict[str, int])
        assert is_generic_type(typing.Optional[str])
        assert not is_generic_type(int)
        assert not is_generic_type(str)

    def test_is_namedtuple(self):
        """Test is_namedtuple function."""
        from collections import namedtuple

        Point = namedtuple("Point", ["x", "y"])
        assert is_namedtuple(Point)
        assert not is_namedtuple(tuple)
        assert not is_namedtuple(list)

    def test_is_iterable(self):
        """Test is_iterable function."""
        assert is_iterable([1, 2, 3])
        assert is_iterable("test")
        assert is_iterable((1, 2))
        assert is_iterable({1, 2})
        assert not is_iterable(5)

    def test_is_iterable_with_exclude(self):
        """Test is_iterable with exclude parameter."""
        assert is_iterable("test", exclude=(str,)) is False
        assert is_iterable([1, 2, 3], exclude=(str,)) is True

    def test_is_iterable_type(self):
        """Test is_iterable_type function."""
        assert is_iterable_type(list)
        assert is_iterable_type(tuple)
        assert is_iterable_type(str)
        assert not is_iterable_type(int)

    def test_is_mapping(self):
        """Test is_mapping function."""
        assert is_mapping({"key": "value"})
        assert is_mapping({})
        assert not is_mapping([1, 2, 3])
        assert not is_mapping("test")


class TestDurationParsing:
    """Test duration parsing."""

    def test_parse_standard_duration(self):
        """Test parsing standard duration format."""
        result = parse_duration("1 days 01:02:03.123456")
        assert result is not None
        assert result == datetime.timedelta(
            days=1, hours=1, minutes=2, seconds=3, microseconds=123456
        )

    def test_parse_simple_time(self):
        """Test parsing simple time format."""
        result = parse_duration("01:02:03")
        assert result is not None
        assert result == datetime.timedelta(hours=1, minutes=2, seconds=3)

    def test_parse_iso8601_duration(self):
        """Test parsing ISO 8601 duration."""
        result = parse_duration("P3DT4H5M6S")
        assert result is not None
        assert result.days == 3

    def test_parse_postgres_interval(self):
        """Test parsing PostgreSQL interval format."""
        result = parse_duration("3 days 04:05:06")
        assert result is not None
        assert result.days == 3

    def test_parse_negative_duration(self):
        """Test parsing negative duration."""
        result = parse_duration("-1 days 00:00:00")
        assert result is not None
        assert result.days == -1

    def test_parse_invalid_duration(self):
        """Test parsing invalid duration returns None."""
        result = parse_duration("invalid duration")
        assert result is None


class TestDatetimeParsing:
    """Test datetime parsing utilities."""

    def test_iso_parse_basic(self):
        """Test basic ISO datetime parsing."""
        result = iso_parse("2024-01-01T12:30:45")
        assert isinstance(result, datetime.datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_iso_parse_with_z(self):
        """Test ISO parsing with Z timezone."""
        result = iso_parse("2024-01-01T12:30:45Z")
        assert isinstance(result, datetime.datetime)
        assert result.tzinfo is not None

    def test_iso_parse_with_timezone(self):
        """Test ISO parsing with timezone offset."""
        result = iso_parse("2024-01-01T12:30:45+05:00")
        assert isinstance(result, datetime.datetime)
        assert result.tzinfo is not None

    def test_iso_parse_microseconds(self):
        """Test ISO parsing with microseconds."""
        result = iso_parse("2024-01-01T12:30:45.123456")
        assert isinstance(result, datetime.datetime)
        assert result.microsecond == 123456

    def test_now_utc(self):
        """Test now() with UTC."""
        result = now()
        assert isinstance(result, datetime.datetime)
        assert result.tzinfo is not None

    def test_now_with_timezone_string(self):
        """Test now() with timezone string."""
        result = now("America/New_York")
        assert isinstance(result, datetime.datetime)
        assert result.tzinfo is not None

    def test_now_with_timezone_object(self):
        """Test now() with timezone object."""
        tz = datetime.timezone.utc
        result = now(tz)
        assert isinstance(result, datetime.datetime)
        assert result.tzinfo == tz


class TestJSONSerialization:
    """Test JSON serialization utilities."""

    def test_make_jsonable_primitives(self):
        """Test make_jsonable with primitive types."""
        assert make_jsonable(42) == 42
        assert make_jsonable("test") == "test"
        assert make_jsonable(3.14) == 3.14
        assert make_jsonable(True) is True
        assert make_jsonable(None) is None

    def test_make_jsonable_list(self):
        """Test make_jsonable with list."""
        result = make_jsonable([1, 2, 3])
        assert result == [1, 2, 3]

    def test_make_jsonable_dict(self):
        """Test make_jsonable with dict."""
        result = make_jsonable({"key": "value", "num": 42})
        assert result == {"key": "value", "num": 42}

    def test_make_jsonable_nested(self):
        """Test make_jsonable with nested structures."""
        data = {
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
            "mixed": [{"a": 1}, {"b": 2}],
        }
        result = make_jsonable(data)
        assert result == data

    def test_make_jsonable_datetime(self):
        """Test make_jsonable with datetime."""
        dt = datetime.datetime(2024, 1, 1, 12, 30)
        result = make_jsonable(dt)
        assert isinstance(result, str)
        assert "2024" in result

    def test_make_jsonable_date(self):
        """Test make_jsonable with date."""
        d = datetime.date(2024, 1, 1)
        result = make_jsonable(d)
        assert isinstance(result, str)
        assert "2024-01-01" in result

    def test_make_jsonable_decimal(self):
        """Test make_jsonable with Decimal."""
        dec = Decimal("123.45")
        result = make_jsonable(dec)
        assert isinstance(result, str)

    def test_make_jsonable_uuid(self):
        """Test make_jsonable with UUID."""
        uid = UUID("12345678-1234-5678-1234-567812345678")
        result = make_jsonable(uid)
        assert isinstance(result, str)

    def test_make_jsonable_path(self):
        """Test make_jsonable with Path."""
        path = Path("/tmp/test.txt")
        result = make_jsonable(path)
        assert isinstance(result, str)

    def test_make_jsonable_bytes(self):
        """Test make_jsonable with bytes."""
        data = b"test data"
        result = make_jsonable(data)
        assert isinstance(result, str)

    def test_make_jsonable_set(self):
        """Test make_jsonable with set."""
        result = make_jsonable({1, 2, 3})
        assert isinstance(result, list)
        assert set(result) == {1, 2, 3}

    def test_make_jsonable_namedtuple(self):
        """Test make_jsonable with namedtuple."""
        from collections import namedtuple

        Point = namedtuple("Point", ["x", "y"])
        point = Point(1, 2)
        result = make_jsonable(point)

        assert isinstance(result, dict)
        assert result["x"] == 1
        assert result["y"] == 2

    def test_make_jsonable_custom_object(self):
        """Test make_jsonable with custom object."""

        class CustomObj:
            def __init__(self):
                self.value = 42
                self.name = "test"

        obj = CustomObj()
        result = make_jsonable(obj)

        assert isinstance(result, dict)
        assert result["value"] == 42
        assert result["name"] == "test"


class TestCoalesce:
    """Test coalesce utility function."""

    def test_coalesce_first_succeeds(self):
        """Test coalesce when first function succeeds."""

        def func1(x):
            return x * 2

        def func2(x):
            return x * 3

        coalesced = coalesce(func1, func2)
        result = coalesced(5)
        assert result == 10

    def test_coalesce_fallback(self):
        """Test coalesce falls back to second function."""

        def func1(x):
            raise ValueError("First failed")

        def func2(x):
            return x * 3

        coalesced = coalesce(func1, func2, target=ValueError)
        result = coalesced(5)
        assert result == 15

    def test_coalesce_all_fail(self):
        """Test coalesce when all functions fail."""

        def func1(x):
            raise ValueError("First failed")

        def func2(x):
            raise ValueError("Second failed")

        coalesced = coalesce(func1, func2, target=ValueError)

        with pytest.raises(Exception):
            coalesced(5)

    def test_coalesce_single_function(self):
        """Test coalesce with single function."""

        def func1(x):
            return x * 2

        coalesced = coalesce(func1)
        # Should return the function itself
        assert coalesced(5) == 10

    def test_coalesce_empty_raises(self):
        """Test coalesce with no functions raises error."""
        with pytest.raises(ValueError):
            coalesce()


class TestUtilsPerformance:
    """Test utilities performance (caching)."""

    def test_namedtuple_caching(self):
        """Test that is_namedtuple uses caching."""
        from collections import namedtuple

        Point = namedtuple("Point", ["x", "y"])

        # Call multiple times - should use cache
        for _ in range(100):
            assert is_namedtuple(Point)

    def test_datetime_parsing_caching(self):
        """Test that datetime parsing uses caching."""
        timestamp = "2024-01-01T12:00:00Z"

        # Parse same timestamp multiple times - should use cache
        results = [iso_parse(timestamp) for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_timezone_caching(self):
        """Test that timezone objects are cached."""
        # Call now() multiple times with same timezone
        results = [now("UTC") for _ in range(10)]
        assert all(isinstance(r, datetime.datetime) for r in results)
