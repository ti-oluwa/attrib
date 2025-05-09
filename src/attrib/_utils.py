import pathlib
import typing
import io
import base64
import decimal
import ipaddress
import types
import re
import enum
import zoneinfo
import sys
import datetime
from collections import defaultdict
import collections.abc
import importlib.util
import uuid

try:
    import orjson as json  # type: ignore[import]
except ImportError:
    import json

from .exceptions import SerializationError
from ._typing import P, R


def has_package(package_name) -> bool:
    """Check if a package is installed."""
    return importlib.util.find_spec(package_name) is not None


class caseinsensitive(typing.NamedTuple):
    s: str

    def __hash__(self) -> int:
        return hash(self.s.upper())


iexact: typing.TypeAlias = caseinsensitive


def is_iterable_type(
    tp: typing.Type[typing.Any],
    /,
    *,
    exclude: typing.Optional[typing.Tuple[typing.Type[typing.Any], ...]] = None,
) -> typing.TypeGuard[typing.Type[collections.abc.Iterable]]:
    """
    Check if a given type is an iterable.

    :param tp: The type to check.
    :param exclude: A tuple of types to return False for, even if they are iterable types.
    """
    is_iter_type = issubclass(tp, collections.abc.Iterable)
    if not is_iter_type:
        return False

    if exclude:
        for _tp in exclude:
            if not is_iterable_type(_tp):
                raise ValueError(f"{_tp} is not an iterable type.")

        is_iter_type = is_iter_type and not issubclass(tp, tuple(exclude))
    return is_iter_type


def is_iterable(
    obj: typing.Any,
    *,
    exclude: typing.Optional[typing.Tuple[typing.Type[typing.Any], ...]] = None,
) -> typing.TypeGuard[collections.abc.Iterable]:
    """Check if an object is an iterable."""
    return is_iterable_type(type(obj), exclude=exclude)


def is_concrete_type(o: typing.Any, /) -> bool:
    """Check if an object is a concrete type."""
    if isinstance(o, typing._SpecialForm):
        return False
    return isinstance(o, type)


def is_valid_type(o: typing.Any, /) -> bool:
    """Check if an object is a valid type that can be used in a field"""
    if isinstance(o, tuple):
        return all(
            (isinstance(obj, typing.ForwardRef) or is_concrete_type(obj) for obj in o)
        )
    return is_concrete_type(o) or isinstance(o, typing.ForwardRef)


def is_slotted_cls(cls: typing.Type[typing.Any], /) -> bool:
    """Check if a class has __slots__ defined."""
    return "__slots__" in cls.__dict__


HAS_DATEUTIL = has_package("dateutil")
PY_GE_3_11 = sys.version_info >= (3, 11)


def resolve_forward_ref(
    ref: typing.ForwardRef,
    /,
    globalns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    localns: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Optional[typing.Any]:
    """Resolve a forward reference to its actual type."""
    return ref._evaluate(globalns or globals(), localns or {}, frozenset())


_Serializer: typing.TypeAlias = typing.Callable[..., typing.Any]


def _unsupported_serializer(*args, **kwargs) -> None:
    """Raise an error for unsupported serialization."""
    raise SerializationError(
        "Unsupported serialization format. Register a serializer for this format."
    )


def _unsupported_serializer_factory():
    """Return a function that raises an error for unsupported serialization."""
    return _unsupported_serializer


class SerializerRegistry(typing.NamedTuple):
    """
    Serializer registry class to handle different serialization formats.

    :param serializer_map: A dictionary mapping format names to their respective serializer functions.
    """

    serializer_map: typing.DefaultDict[str, _Serializer] = defaultdict(
        _unsupported_serializer_factory
    )

    def __call__(self, fmt: str, *args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        """
        Serialize data using the specified format.

        :param fmt: The format to serialize to (e.g., 'json', 'xml').
        :param args: Positional arguments to pass to the format's serializer.
        :param kwargs: Keyword arguments to pass to the format's serializer.
        :return: Serialized data in the specified format.
        """
        return self.serializer_map[fmt](*args, **kwargs)


standard_duration_re = re.compile(
    r"^"
    r"(?:(?P<days>-?\d+) (days?, )?)?"
    r"(?P<sign>-?)"
    r"((?:(?P<hours>\d+):)(?=\d+:\d+))?"
    r"(?:(?P<minutes>\d+):)?"
    r"(?P<seconds>\d+)"
    r"(?:[.,](?P<microseconds>\d{1,6})\d{0,6})?"
    r"$"
)

# Support the sections of ISO 8601 date representation that are accepted by
# timedelta
iso8601_duration_re = re.compile(
    r"^(?P<sign>[-+]?)"
    r"P"
    r"(?:(?P<days>\d+([.,]\d+)?)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+([.,]\d+)?)H)?"
    r"(?:(?P<minutes>\d+([.,]\d+)?)M)?"
    r"(?:(?P<seconds>\d+([.,]\d+)?)S)?"
    r")?"
    r"$"
)

# Support PostgreSQL's day-time interval format, e.g. "3 days 04:05:06". The
# year-month and mixed intervals cannot be converted to a timedelta and thus
# aren't accepted.
postgres_interval_re = re.compile(
    r"^"
    r"(?:(?P<days>-?\d+) (days? ?))?"
    r"(?:(?P<sign>[-+])?"
    r"(?P<hours>\d+):"
    r"(?P<minutes>\d\d):"
    r"(?P<seconds>\d\d)"
    r"(?:\.(?P<microseconds>\d{1,6}))?"
    r")?$"
)


def parse_duration(value):
    """
    Parse a duration string and return a datetime.timedelta.

    The preferred format for durations is '%d %H:%M:%S.%f'.

    Also supports ISO 8601 representation and PostgreSQL's day-time interval
    format.

    Extracted from Django's django.utils.dateparse module.
    """
    match = (
        standard_duration_re.match(value)
        or iso8601_duration_re.match(value)
        or postgres_interval_re.match(value)
    )
    if match:
        kw = match.groupdict()
        sign = -1 if kw.pop("sign", "+") == "-" else 1
        if kw.get("microseconds"):
            kw["microseconds"] = kw["microseconds"].ljust(6, "0")
        kw = {k: float(v.replace(",", ".")) for k, v in kw.items() if v is not None}
        days = datetime.timedelta(kw.pop("days", 0.0) or 0.0)
        if match.re == iso8601_duration_re:
            days *= sign
        return days + sign * datetime.timedelta(**kw)


_ISO_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"
_RFC3339_DATE_FORMAT_0 = "%Y, /-%m-%dT%H:%M:%S.%f%z"
_RFC3339_DATE_FORMAT_1 = "%Y, /-%m-%dT%H:%M:%S%z"


def rfc3339_parse(s: str, /) -> datetime.datetime:
    """
    Parse RFC 3339 datetime string.

    Use `dateutil.parser.parse` for more generic (but slower)
    parsing.

    Source: https://stackoverflow.com/a/30696682
    """
    global _RFC3339_DATE_FORMAT_0, _RFC3339_DATE_FORMAT_1
    try:
        return datetime.datetime.strptime(s, _RFC3339_DATE_FORMAT_0)
    except ValueError:
        # Perhaps the datetime has a whole number of seconds with no decimal
        # point. In that case, this will work:
        return datetime.datetime.strptime(s, _RFC3339_DATE_FORMAT_1)


def iso_parse(
    s: str, /, fmt: typing.Optional[typing.Union[str, typing.Iterable[str]]] = None
) -> datetime.datetime:
    """
    Parse ISO 8601 datetime string as fast as possible.

    Reference: https://stackoverflow.com/a/62769371
    """
    global HAS_DATEUTIL, _ISO_DATE_FORMAT

    if PY_GE_3_11:
        try:
            return datetime.datetime.fromisoformat(s)
        except ValueError:
            pass
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass

    if HAS_DATEUTIL:
        try:
            from dateutil import parser  # type: ignore

            return parser.isoparse(s)
        except ValueError:
            pass

    fmt = fmt or _ISO_DATE_FORMAT
    if isinstance(fmt, str):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            pass
    else:
        for f in fmt:
            try:
                return datetime.datetime.strptime(s, f)
            except ValueError:
                continue

    if HAS_DATEUTIL:
        return parser.parse(s)  # type: ignore
    raise ValueError(f"Could not parse datetime string {s}")


K = typing.TypeVar("K")
V = typing.TypeVar("V")


class _LRUCache(typing.Generic[K, V]):
    """
    Simple LRU cache implementation.
    """

    def __init__(self, maxsize: int = 128) -> None:
        self.cache: typing.OrderedDict[K, V] = collections.OrderedDict()
        self.maxsize = maxsize

    def __getitem__(self, key: K) -> V:
        value = self.cache.pop(key)
        self.cache[key] = value
        return value

    def __setitem__(self, key: K, value: V) -> None:
        if key in self.cache:
            self.cache.pop(key)
        elif len(self.cache) >= self.maxsize:
            self.cache.popitem(last=False)
        self.cache[key] = value

    def __contains__(self, key: K) -> bool:
        return key in self.cache

    def __delitem__(self, key: K) -> None:
        del self.cache[key]

    def __len__(self) -> int:
        return len(self.cache)

    def __iter__(self) -> typing.Iterator[K]:
        return iter(self.cache)

    def clear(self) -> None:
        self.cache.clear()


HASHABLE_TYPES = (
    int,
    str,
    float,
    bool,
    bytes,
    bytearray,
    frozenset,
    tuple,
    complex,
)


def get_cache_key(value: typing.Any) -> typing.Any:
    """Create a cache key for the given value."""
    return value if isinstance(value, HASHABLE_TYPES) else id(value)


### JSON serialization helpers


def unjsonable(obj: typing.Any) -> typing.Any:
    """Raise a TypeError for unjsonable objects."""
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable.")


def jsonable_mapping(obj: typing.Mapping) -> typing.Any:
    """Attempt to convert a mapping to a JSON-serializable format."""
    return {str(key): make_jsonable(value) for key, value in obj.items()}


def jsonable_iterable(obj: typing.Iterable) -> typing.List[typing.Any]:
    """Attempt to convert an iterable to a JSON-serializable format."""
    return [make_jsonable(item) for item in obj]


def jsonable_datetime(
    obj: typing.Union[datetime.datetime, datetime.date, datetime.time],
) -> str:
    """Attempt to convert a datetime object to a JSON-serializable format."""
    return obj.isoformat()


def jsonable_bytes(obj: bytes) -> str:
    """Attempt to convert bytes to a JSON-serializable format."""
    return base64.b64encode(obj).decode("utf-8")


def make_jsonable(obj: typing.Any) -> typing.Any:
    """
    Attempt to convert an object to a JSON-serializable format.

    This function recursively converts objects to a format that can be
    serialized to JSON. It handles various types, including lists, sets,
    dictionaries, and custom objects. If a type is not supported, it raises
    a TypeError.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, collections.abc.Mapping):
        return jsonable_mapping(obj)
    elif isinstance(obj, collections.abc.Iterable):
        return jsonable_iterable(obj)

    encoder = JSON_ENCODERS.get(type(obj), None)
    if encoder is not None:
        try:
            return encoder(obj)
        except Exception as exc:
            raise TypeError(f"Failed to serialize object of type {type(obj)}: {exc}")

    for cls, encoder in JSON_ENCODERS.items():
        if isinstance(obj, cls):
            encoded = encoder(obj)
            # Update the encoders mapping to include the encoder for this type
            JSON_ENCODERS[cls] = encoder
            return encoded

    if hasattr(obj, "__dict__"):
        return jsonable_mapping(vars(obj))
    elif hasattr(obj, "__slots__"):
        return jsonable_mapping({slot: getattr(obj, slot) for slot in obj.__slots__})  # type: ignore[union-attr]

    raise json.loads(json.dumps(obj, default=unjsonable))


JSON_ENCODERS = {
    list: jsonable_iterable,
    set: jsonable_iterable,
    frozenset: jsonable_iterable,
    tuple: jsonable_iterable,
    collections.deque: jsonable_iterable,
    collections.ChainMap: jsonable_iterable,
    collections.OrderedDict: jsonable_mapping,
    dict: jsonable_mapping,
    uuid.UUID: str,
    re.Pattern: str,
    enum.Enum: lambda obj: obj.value,
    decimal.Decimal: str,
    bytes: jsonable_bytes,
    bytearray: jsonable_bytes,
    datetime.timedelta: str,
    datetime.datetime: jsonable_datetime,
    datetime.date: jsonable_datetime,
    datetime.time: jsonable_datetime,
    datetime.tzinfo: str,
    zoneinfo.ZoneInfo: str,
    typing.Generator: jsonable_iterable,
    memoryview: lambda obj: base64.b64encode(obj.tobytes()).decode("utf-8"),
    io.BytesIO: lambda obj: base64.b64encode(obj.getvalue()).decode("utf-8"),
    types.SimpleNamespace: vars,
    complex: lambda obj: [obj.real, obj.imag],
    pathlib.PurePath: str,
    ipaddress._IPAddressBase: str,
    ipaddress.IPv4Address: str,
    ipaddress.IPv6Address: str,
    ipaddress.IPv4Network: str,
    ipaddress.IPv6Network: str,
    ipaddress.IPv4Interface: str,
    ipaddress.IPv6Interface: str,
}
