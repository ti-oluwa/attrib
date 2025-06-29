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
import importlib.util
import uuid
from collections import defaultdict, deque
from typing_extensions import TypeAlias, TypeGuard

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo  # type: ignore[import]
try:
    import orjson as json  # type: ignore[import]
except ImportError:
    try:
        import ujson as json  # type: ignore[import]
    except ImportError:
        import json  # Fallback to the standard library json module

from attrib._typing import (
    IterTco,
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


def has_package(package_name) -> bool:
    """Check if a package is installed."""
    return importlib.util.find_spec(package_name) is not None


class caseinsensitive(typing.NamedTuple):
    s: str

    def __hash__(self) -> int:
        return hash(self.s.upper())


iexact: TypeAlias = caseinsensitive


def is_iterable_type(
    tp: typing.Type[typing.Any],
    /,
    *,
    exclude: typing.Optional[typing.Tuple[typing.Type[typing.Any], ...]] = None,
) -> TypeGuard[typing.Type[typing.Iterable[typing.Any]]]:
    """
    Check if a given type is an iterable type. A subclass of `collections.abc.Iterable`.

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
) -> TypeGuard[typing.Iterable]:
    """Check if an object is an iterable."""
    return is_iterable_type(type(obj), exclude=exclude)


def is_mapping(obj: typing.Any) -> TypeGuard[typing.Mapping]:
    """Check if an object is a mapping (like dict)."""
    return isinstance(obj, collections.abc.Mapping)


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


def is_generic_type(o: typing.Any, /) -> bool:
    """Check if an object is a generic type."""
    return typing.get_origin(o) is not None and not isinstance(o, typing._SpecialForm)


def is_mapping_type(
    tp: typing.Type[typing.Any], /
) -> TypeGuard[typing.Type[typing.Mapping]]:
    """
    Check if a given type is a mapping type. A subclass of `collections.abc.Mapping`.

    :param tp: The type to check.
    :return: True if the type is a mapping type, False otherwise.
    """
    return inspect.isclass(tp) and issubclass(tp, collections.abc.Mapping)


def is_typed_dict(cls: type) -> bool:
    """
    Make shift check for TypedDict.
    """
    return (
        isinstance(cls, type)
        and issubclass(cls, dict)
        and "__required_keys__" in cls.__dict__
    )


def is_named_tuple(cls: typing.Type[typing.Any], /) -> bool:
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


def is_slotted_cls(cls: typing.Type[typing.Any], /) -> bool:
    """Check if a class has __slots__ defined."""
    return "__slots__" in cls.__dict__


def _list_adder(
    list_: typing.List[typing.Any], value: typing.Any
) -> typing.List[typing.Any]:
    """
    Add a value to a list and return the updated list.
    """
    list_.append(value)
    return list_


def _set_adder(
    set_: typing.Set[typing.Any], value: typing.Any
) -> typing.Set[typing.Any]:
    """
    Add a value to a set and return the updated set.
    """
    set_.add(value)
    return set_


def _tuple_adder(
    tuple_: typing.Tuple[typing.Any, ...], value: typing.Any
) -> typing.Tuple[typing.Any, ...]:
    return (*tuple_, value)


def _frozenset_adder(
    frozenset_: typing.FrozenSet[typing.Any], value: typing.Any
) -> typing.FrozenSet[typing.Any]:
    return frozenset(list(frozenset_) + [value])


def get_itertype_adder(
    field_type: typing.Type[IterTco],
) -> typing.Callable[[IterTco, typing.Any], IterTco]:
    """
    Get the appropriate adder function for the specified iterable type.
    This function returns the method used to add elements to the iterable type.

    Example:
    ```python

    adder = get_itertype_adder(list)
    print(adder([], 1))
    # Output: [1]
    ```
    """
    adder = None
    if issubclass(field_type, (list, deque)):
        adder = _list_adder
    elif issubclass(field_type, set):
        adder = _set_adder
    elif issubclass(field_type, tuple):
        adder = _tuple_adder
    elif issubclass(field_type, frozenset):
        adder = _frozenset_adder

    if adder is None:
        raise TypeError(f"Unsupported iterable type: {field_type}")
    return typing.cast(typing.Callable[[IterTco, typing.Any], IterTco], adder)


HAS_DATEUTIL = has_package("dateutil")
PY_GE_3_11 = sys.version_info >= (3, 11)


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
    return typing._eval_type(type_, globalns or {}, localns or {})  # type: ignore[no-redef]


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
        days = datetime.timedelta(kw.pop("days", 0.0) or 0.0)
        if match.re == iso8601_duration_re:
            days *= sign
        return days + sign * datetime.timedelta(**kw)


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


def iso_parse(
    s: str, /, fmt: typing.Optional[typing.Union[str, typing.Iterable[str]]] = None
) -> datetime.datetime:
    """
    Parse ISO 8601 datetime string as fast as possible.

    Reference: https://stackoverflow.com/a/62769371
    """
    global HAS_DATEUTIL, ISO_DATE_FORMAT

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

    fmt = fmt or ISO_DATE_FORMAT
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
class SerializerRegistry(typing.NamedTuple):
    """
    Registry class to handle different serialization formats.

    :param map: A dictionary mapping format names to their respective serializer functions.
    """

    map: typing.DefaultDict[str, Serializer[typing.Any]] = defaultdict(
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
        return self.map[fmt](*args, **kwargs)


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
    elif is_named_tuple(obj_type):
        return jsonable_mapping(obj._asdict())
    elif isinstance(obj, collections.abc.Iterable):
        return jsonable_iterable(obj)

    encoder = JSON_ENCODERS.get(obj_type, None)
    if encoder is not None:
        return encoder(obj)

    mro = obj_type.__mro__
    for i in range(1, len(mro) - 1):  # Skip the first one as we already checked it
        cls = mro[i]
        if cls in JSON_ENCODERS:
            encoder = JSON_ENCODERS[cls]
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
