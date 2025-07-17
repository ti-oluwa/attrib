import pathlib
import typing
import io
import inspect
import base64
import decimal
import ipaddress
import types
import re
import enum
import sys
import datetime
import collections.abc
from importlib.util import find_spec
import uuid
from collections import defaultdict
from typing_extensions import TypeGuard

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo  # type: ignore[no-redef, import-not-found]
try:
    import orjson as json  # type: ignore[import]
except ImportError:
    try:
        import ujson as json  # type: ignore[no-redef, import-untyped]
    except ImportError:
        import json  # type: ignore[no-redef] # Fallback to the standard library json module

from attrib.types import (
    JSONDict,
    JSONList,
    Serializer,
    EMPTY,
    JSONValue,
)
from attrib.exceptions import SerializationError, DetailedError


__all__ = [
    "iexact",
    "is_valid_type",
    "resolve_type",
    "parse_duration",
    "rfc3339_parse",
    "iso_parse",
    "now",
    "make_jsonable",
    "coalesce_funcs",
]


if sys.version_info >= (3, 9):

    def is_generic_type(typ: typing.Any) -> bool:
        """Check whether the type is a generic type."""
        # Inheriting from protocol will inject `Generic` into the MRO
        # without `__orig_bases__`.
        return (
            typing.get_origin(typ)
            or isinstance(typ, (typing._GenericAlias, types.GenericAlias))  # type: ignore
            or (issubclass(typ, typing.Generic) and hasattr(typ, "__orig_bases__"))
        )

else:

    def is_generic_type(typ: typing.Any) -> bool:
        """Check whether the type is a generic type."""
        return (
            typing.get_origin(typ)
            or isinstance(typ, typing._GenericAlias)  # type: ignore
            or (issubclass(typ, typing.Generic) and hasattr(typ, "__orig_bases__"))
        )


def is_namedtuple(cls: typing.Type[typing.Any], /) -> bool:
    """
    Check if a class is a named tuple.

    This checks if the class is a subclass of `tuple` and has a `_fields` attribute.
    """
    return (
        isinstance(cls, type)
        and issubclass(cls, tuple)
        and hasattr(cls, "_fields")
        and isinstance(cls._fields, tuple)  # type: ignore[has-type,attr-defined]
    )


def is_iterable_type(
    typ: typing.Type[typing.Any],
    /,
    *,
    exclude: typing.Optional[typing.Tuple[typing.Type[typing.Any], ...]] = None,
) -> TypeGuard[typing.Type[typing.Iterable[typing.Any]]]:
    """
    Check if a given type is an iterable type. A subclass of `collections.abc.Iterable`.

    :param typ: The type to check.
    :param exclude: A tuple of types to return False for, even if they are iterable types.
    """
    is_iter_type = issubclass(typ, collections.abc.Iterable)
    if not is_iter_type:
        return False

    if exclude:
        for _tp in exclude:
            if not is_iterable_type(_tp):
                raise ValueError(f"{_tp} is not an iterable type.")

        is_iter_type = is_iter_type and not issubclass(typ, tuple(exclude))
    return is_iter_type


def is_iterable(
    obj: typing.Any,
    *,
    exclude: typing.Optional[typing.Tuple[typing.Type[typing.Any], ...]] = None,
) -> TypeGuard[typing.Iterable]:
    """Check if an object is an iterable."""
    return is_iterable_type(type(obj), exclude=exclude)


def is_mapping(obj: typing.Any) -> TypeGuard[typing.Mapping]:
    """Check if an object is a mapping (like dict)."""
    return isinstance(obj, collections.abc.Mapping)


def is_concrete_type(typ: typing.Type[typing.Any], /) -> bool:
    """Check if an object is a concrete type."""
    return not isinstance(typ, typing._SpecialForm) and isinstance(typ, type)


def is_valid_type(typ: typing.Type[typing.Any], /) -> bool:
    """Check if an object is a valid type that can be used in a field"""
    if isinstance(typ, tuple):
        return all(
            (isinstance(obj, typing.ForwardRef) or is_concrete_type(obj) for obj in typ)
        )
    return is_concrete_type(typ) or isinstance(typ, typing.ForwardRef)


def has_package(package_name) -> bool:
    """Check if a package is installed."""
    return find_spec(package_name) is not None


class iexact(typing.NamedTuple):
    s: str

    def __hash__(self) -> int:
        return hash(self.s.upper())


HAS_DATEUTIL = has_package("dateutil")


def resolve_forward_refs(
    type_: typing.Any,
    /,
    globalns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    localns: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Optional[typing.Any]:
    """
    Resolve a forward reference(s) in a type.

    :param type_: The type to resolve.
    :param globalns: The global namespace to use for resolution.
    :param localns: The local namespace to use for resolution.
    :return: The resolved type.
    """
    return typing._eval_type(type_, globalns or {}, localns or {})  # type: ignore[attr-defined]


def resolve_type(
    type_: typing.Any,
    /,
    globalns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    localns: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Any:
    """
    Resolve an adapter type.

    This determines the actual type(s) of the field. Especially
    useful when the field type definition is/contains a forward reference.

    :param type_: The type to resolve.
    :param globalns: The global namespace to use for resolution.
    :param localns: The local namespace to use for resolution.
    :return: The resolved type.
    """
    if (
        inspect.isclass(type_)
        and not issubclass(type_, enum.Enum)
        and isinstance(type_, (tuple, list))
    ):
        return tuple(
            resolve_type(arg, globalns, localns)
            if isinstance(arg, typing.ForwardRef)
            else arg
            for arg in type_
        )
    return resolve_forward_refs(type_, globalns, localns) or type_


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


def parse_duration(value: str) -> typing.Optional[datetime.timedelta]:
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
        days = datetime.timedelta(kw.pop("days", 0.0) or 0.0)  # type: ignore[arg-type]
        if match.re == iso8601_duration_re:
            days *= sign
        return days + sign * datetime.timedelta(**kw)  # type: ignore[arg-type]
    return None


ISO_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"
RFC3339_DATE_FORMAT_0 = "%Y, /-%m-%dT%H:%M:%S.%f%z"
RFC3339_DATE_FORMAT_1 = "%Y, /-%m-%dT%H:%M:%S%z"


def rfc3339_parse(s: str, /) -> datetime.datetime:
    """
    Parse RFC 3339 datetime string.

    Use `dateutil.parser.parse` for more generic (but slower)
    parsing.

    Source: https://stackoverflow.com/a/30696682
    """
    global RFC3339_DATE_FORMAT_0, RFC3339_DATE_FORMAT_1
    try:
        return datetime.datetime.strptime(s, RFC3339_DATE_FORMAT_0)
    except ValueError:
        # Perhaps the datetime has a whole number of seconds with no decimal
        # point. In that case, this will work:
        return datetime.datetime.strptime(s, RFC3339_DATE_FORMAT_1)


if sys.version_info >= (3, 11) and HAS_DATEUTIL:
    from dateutil import parser  # type: ignore[import]

    def iso_parse(
        s: str, /, fmt: typing.Optional[typing.Union[str, typing.Iterable[str]]] = None
    ) -> datetime.datetime:
        """
        Parse ISO 8601 datetime string as fast as possible.

        Reference: https://stackoverflow.com/a/62769371
        """
        global ISO_DATE_FORMAT
        try:
            return datetime.datetime.fromisoformat(s)
        except ValueError:
            pass

        try:
            return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            pass

        try:
            return parser.isoparse(s)
        except ValueError:
            pass

        fmts = fmt or ISO_DATE_FORMAT
        if isinstance(fmts, str):
            try:
                return datetime.datetime.strptime(s, fmts)
            except ValueError:
                pass
        else:
            for fmt in fmts:
                try:
                    return datetime.datetime.strptime(s, fmt)
                except ValueError:
                    continue

        return parser.parse(s)

elif sys.version_info >= (3, 11):

    def iso_parse(
        s: str, /, fmt: typing.Optional[typing.Union[str, typing.Iterable[str]]] = None
    ) -> datetime.datetime:
        """
        Parse ISO 8601 datetime string as fast as possible.

        Reference: https://stackoverflow.com/a/62769371
        """
        global ISO_DATE_FORMAT

        try:
            return datetime.datetime.fromisoformat(s)
        except ValueError:
            pass

        try:
            return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            pass

        fmts = fmt or ISO_DATE_FORMAT
        if isinstance(fmts, str):
            try:
                return datetime.datetime.strptime(s, fmts)
            except ValueError:
                pass
        else:
            for fmt in fmts:
                try:
                    return datetime.datetime.strptime(s, fmt)
                except ValueError:
                    continue

        raise ValueError(f"Could not parse datetime string {s}")

elif HAS_DATEUTIL:
    from dateutil import parser  # type: ignore[import]

    def iso_parse(
        s: str,
        /,
        fmt: typing.Optional[typing.Union[str, typing.Iterable[str]]] = None,
    ) -> datetime.datetime:
        """
        Parse ISO 8601 datetime string as fast as possible.

        Reference: https://stackoverflow.com/a/62769371
        """
        global ISO_DATE_FORMAT

        try:
            return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            pass

        try:
            return parser.isoparse(s)
        except ValueError:
            pass

        fmts = fmt or ISO_DATE_FORMAT
        if isinstance(fmts, str):
            try:
                return datetime.datetime.strptime(s, fmts)
            except ValueError:
                pass
        else:
            for fmt in fmts:
                try:
                    return datetime.datetime.strptime(s, fmt)
                except ValueError:
                    continue

        return parser.parse(s)

else:

    def iso_parse(
        s: str,
        /,
        fmt: typing.Optional[typing.Union[str, typing.Iterable[str]]] = None,
    ) -> datetime.datetime:
        """
        Parse ISO 8601 datetime string as fast as possible.

        Reference: https://stackoverflow.com/a/62769371
        """
        global ISO_DATE_FORMAT

        try:
            return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            pass

        fmts = fmt or ISO_DATE_FORMAT
        if isinstance(fmts, str):
            try:
                return datetime.datetime.strptime(s, fmts)
            except ValueError:
                pass
        else:
            for fmt in fmts:
                try:
                    return datetime.datetime.strptime(s, fmt)
                except ValueError:
                    continue

        raise ValueError(f"Could not parse datetime string {s}")


def now(
    tz: typing.Optional[typing.Union[str, datetime.tzinfo]] = None,
) -> datetime.datetime:
    """
    Get the current time in the specified timezone.

    If no timezone is specified, it returns the current time in UTC.
    """
    if tz is None:
        return datetime.datetime.now(datetime.timezone.utc)
    if isinstance(tz, str):
        tz = zoneinfo.ZoneInfo(tz)

    return datetime.datetime.now(tz).astimezone(tz)


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


def _unsupported_serializer(*args, **kwargs) -> None:
    """Raise an error for unsupported serialization."""
    raise SerializationError(
        "Unsupported serialization format. Register a serializer for this format.",
        code="unsupported_serialization_format",
    )


def _unsupported_serializer_factory():
    """Return a function that raises an error for unsupported serialization."""
    return _unsupported_serializer


@typing.final
class SerializerMap(defaultdict):
    def __init__(
        self,
        map: typing.Mapping[str, Serializer[typing.Any]],
        default_factory: typing.Optional[
            typing.Callable[[], Serializer[typing.Any]]
        ] = _unsupported_serializer_factory,
    ) -> None:
        super().__init__(default_factory, dict(map))


HASHABLE_TYPES = (
    int,
    str,
    float,
    bool,
    bytes,
    bytearray,
    frozenset,
    complex,
)


def get_cache_key(value: typing.Any) -> typing.Any:
    """Create a cache key for the given value."""
    return value if isinstance(value, HASHABLE_TYPES) else id(value)


##################################
### JSON serialization helpers ###
##################################


def unjsonable(obj: typing.Any) -> typing.NoReturn:
    """Raise a TypeError for JSON unserializable objects."""
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable.")


def jsonable_mapping(obj: typing.Mapping[typing.Any, typing.Any]) -> JSONDict:
    """Attempt to convert a mapping to a JSON-serializable format."""
    return {str(key): make_jsonable(value) for key, value in obj.items()}


def jsonable_iterable(obj: typing.Iterable) -> JSONList:
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


def make_jsonable(obj: typing.Any) -> JSONValue:
    """
    Attempt to convert an object to a JSON-serializable format.

    This function recursively converts objects to a format that can be
    serialized to JSON. It handles various types, including lists, sets,
    dictionaries, and custom objects. If a type is not supported, it raises
    a TypeError.
    """
    if obj is None or obj is EMPTY:
        return None

    obj_type = type(obj)
    if isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, collections.abc.Mapping):
        return jsonable_mapping(obj)
    elif is_namedtuple(obj_type):
        return jsonable_mapping(obj._asdict())
    elif isinstance(obj, collections.abc.Iterable):
        return jsonable_iterable(obj)

    encoder = JSON_ENCODERS.get(obj_type, None)
    if encoder is not None:
        return encoder(obj)

    for cls in obj_type.__mro__[1:-1]:  # Skip the first one as we already checked it
        if encoder := JSON_ENCODERS.get(cls, None):
            # Cache this for future use
            JSON_ENCODERS[obj_type] = encoder
            return encoder(obj)

    if hasattr(obj, "__dict__"):
        return jsonable_mapping(vars(obj))
    elif hasattr(obj, "__slots__"):
        return jsonable_mapping(
            {
                slot: getattr(obj, slot)
                for slot in obj.__slots__
                if slot not in {"__weakref__", "__dict__"}
            }
        )  # type: ignore[union-attr]

    return json.loads(json.dumps(obj, default=unjsonable))


JSON_ENCODERS: typing.Dict[typing.Type, typing.Callable[[typing.Any], JSONValue]] = {
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


def coalesce_funcs(
    *funcs: typing.Callable[..., typing.Any],
    target: typing.Union[
        typing.Tuple[typing.Type[Exception], ...], typing.Type[Exception]
    ] = Exception,
    detailed_exc_type: typing.Type[DetailedError] = DetailedError,
) -> typing.Callable[..., typing.Any]:
    """
    Build a function that calls a list of functions and returns the first successful call.
    If all functions fail, it raises a `DetailedError` with details of all exceptions raised.
    This is useful for trying multiple functions in sequence until one succeeds.

    :param funcs: A list of functions to call.
    :param target: The exception type(s) to catch. Default is `Exception`.
    :param detailed_exc_type: The type of exception to raise if all functions fail. Default is `DetailedError`.
    :return: A function that returns the result of the first successful call.
    """
    if not funcs:
        raise ValueError("No functions provided.")

    if len(funcs) == 1:
        return funcs[0]

    def coalesce(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        error = None
        for index, func in enumerate(funcs):
            try:
                return func(*args, **kwargs)
            except target as exc:
                if error is None:
                    error = detailed_exc_type.from_exception(
                        exc,
                        location=[func.__name__, index],
                    )
                else:
                    error.add(
                        exc,
                        location=[func.__name__, index],
                    )
        if error is not None:
            raise error

    return coalesce
