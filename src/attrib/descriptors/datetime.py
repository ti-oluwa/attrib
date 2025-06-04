import typing
import datetime
from typing_extensions import Unpack

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo  # type: ignore[import]


from attrib.descriptors.base import Field, FieldKwargs, to_string_serializer
from attrib._typing import Context
from attrib._utils import iso_parse, parse_duration, _LRUCache
from attrib.exceptions import DeserializationError


__all__ = [
    "Date",
    "Time",
    "DateTime",
    "TimeZone",
    "Duration",
]


def timedelta_deserializer(
    value: typing.Any, field: Field[typing.Any]
) -> datetime.timedelta:
    """Deserialize duration data to time delta."""
    duration = parse_duration(value)
    if duration is None:
        raise DeserializationError(
            "Invalid/unsupported duration value",
            input_type=type(value),
            expected_type="timedelta",
            code="invalid_duration",
        )
    return duration


class Duration(Field[datetime.timedelta]):
    """Field for handling duration values."""

    default_serializers = {
        "json": to_string_serializer,
    }
    default_deserializer = timedelta_deserializer

    def __init__(self, **kwargs: Unpack[FieldKwargs]) -> None:
        super().__init__(field_type=datetime.timedelta, **kwargs)


TimeDelta = Duration


def timezone_deserializer(
    value: typing.Any, field: Field[typing.Any]
) -> zoneinfo.ZoneInfo:
    """Deserialize timezone data to `zoneinfo.ZoneInfo` object."""
    return zoneinfo.ZoneInfo(value)


class TimeZone(Field[datetime.tzinfo]):
    """Field for handling timezone values."""

    default_serializers = {
        "json": to_string_serializer,
    }
    default_deserializer = timezone_deserializer

    def __init__(self, **kwargs: Unpack[FieldKwargs]):
        super().__init__(field_type=datetime.tzinfo, **kwargs)


DatetimeType = typing.TypeVar(
    "DatetimeType",
    bound=typing.Union[datetime.date, datetime.datetime, datetime.time],
)


def datetime_serializer(
    value: DatetimeType,
    field: "DateTimeBase[DatetimeType]",
    context: Context,
) -> str:
    """Serialize a datetime object to a string."""
    return value.strftime(field.output_format)


class DateTimeBase(Field[DatetimeType]):
    """Base class for datetime fields."""

    default_output_format: typing.ClassVar[str] = "%Y-%m-%d %H:%M:%S%z"
    default_serializers = {
        "json": datetime_serializer,
    }

    def __init__(
        self,
        field_type: typing.Type[DatetimeType],
        *,
        input_formats: typing.Optional[typing.Iterable[str]] = None,
        output_format: typing.Optional[str] = None,
        **kwargs: Unpack[FieldKwargs],
    ):
        """
        Initialize the field.

        :param input_formats: Possible expected input format (ISO or RFC) for the date value.
            If not provided, the field will attempt to parse the date value
            itself, which may be slower.

        :param output_format: The preferred output format for the date value.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(field_type=field_type, **kwargs)  # type: ignore
        self.input_formats = input_formats
        self.output_format = output_format or self.default_output_format


_datetime_cache = _LRUCache[str, datetime.datetime](maxsize=128)


def cached_iso_parse(
    value: typing.Any,
    fmt: typing.Optional[typing.Iterable[str]] = None,
) -> datetime.datetime:
    """Parse a datetime string in ISO format with caching."""
    if isinstance(value, datetime.datetime):
        return value

    if value in _datetime_cache:
        return _datetime_cache[value]

    parsed = iso_parse(value, fmt=fmt)
    _datetime_cache[value] = parsed
    return parsed


def iso_date_deserializer(
    value: str, field: DateTimeBase[datetime.date]
) -> datetime.date:
    """Parse a date string in ISO format."""
    return cached_iso_parse(value, fmt=field.input_formats).date()


def iso_time_deserializer(
    value: str, field: DateTimeBase[datetime.time]
) -> datetime.time:
    """Parse a time string in ISO format."""
    return cached_iso_parse(value, fmt=field.input_formats).time()


class Date(DateTimeBase[datetime.date]):
    """Field for handling date values."""

    default_output_format = "%Y-%m-%d"
    default_deserializer = iso_date_deserializer

    def __init__(
        self,
        *,
        input_formats: typing.Optional[typing.Iterable[str]] = None,
        output_format: typing.Optional[str] = None,
        **kwargs: Unpack[FieldKwargs],
    ):
        super().__init__(
            field_type=datetime.date,
            input_formats=input_formats,
            output_format=output_format,
            **kwargs,
        )


class Time(DateTimeBase[datetime.time]):
    """Field for handling time values."""

    default_output_format = "%H:%M:%S.%s"
    default_deserializer = iso_time_deserializer

    def __init__(
        self,
        *,
        input_formats: typing.Optional[typing.Iterable[str]] = None,
        output_format: typing.Optional[str] = None,
        **kwargs: Unpack[FieldKwargs],
    ):
        super().__init__(
            field_type=datetime.time,
            input_formats=input_formats,
            output_format=output_format,
            **kwargs,
        )


def datetime_deserializer(
    value: str, field: DateTimeBase[datetime.datetime]
) -> datetime.datetime:
    """Parse a datetime string in ISO format."""
    return cached_iso_parse(value, fmt=field.input_formats)


def is_aware_datetime(value: datetime.datetime) -> bool:
    """Check if a datetime object is timezone-aware."""
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


class DateTime(DateTimeBase[datetime.datetime]):
    """
    Field for handling datetime values.

    Datetime values returned by this field will be never be naive.

    If no timezone is defined for the field, and the input datetime is naive,
    it will be assumed to be in UTC timezone.

    Note that if a default value is provided, it should be a timezone-aware
    datetime object, or a callable that returns one. If a naive datetime is
    provided as a default, it will remain naive as default values are treated
    as valid input values and will not be modified by the field.
    """

    default_output_format = "%Y-%m-%d %H:%M:%S%z"
    default_deserializer = datetime_deserializer

    def __init__(
        self,
        *,
        tz: typing.Optional[typing.Union[datetime.tzinfo, str]] = None,
        input_formats: typing.Optional[typing.Iterable[str]] = None,
        output_format: typing.Optional[str] = None,
        **kwargs: Unpack[FieldKwargs],
    ):
        """
        Initialize the field.

        :param tz: The timezone to use for the datetime value. If this set,
            the datetime value will be represented in this timezone.

        :param input_format: Possible expected input format (ISO or RFC) for the datetime value.
            If not provided, the field will attempt to parse the datetime value
            itself, which may be slower.

        :param output_format: The preferred output format for the datetime value.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(
            field_type=datetime.datetime,
            input_formats=input_formats,
            output_format=output_format,
            **kwargs,
        )
        self.tz = timezone_deserializer(tz, self) if tz else None

    def deserialize(
        self,
        value: typing.Union[datetime.datetime, typing.Any],
        instance: typing.Optional[typing.Any] = None,
    ) -> typing.Optional[datetime.datetime]:
        deserialized = super().deserialize(value, instance)
        if deserialized is None:
            return None

        tz_available = self.tz is not None
        is_aware = is_aware_datetime(deserialized)
        if is_aware and tz_available:
            return deserialized.astimezone(self.tz)
        if is_aware and not tz_available:
            return deserialized
        return deserialized.replace(tzinfo=self.tz or zoneinfo.ZoneInfo("UTC"))
