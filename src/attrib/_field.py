import datetime
import decimal
import ipaddress
import pathlib
import typing
import uuid
from multiprocessing import RLock

from typing_extensions import Unpack

from attrib._utils import is_generic_type
from attrib.adapters import TypeAdapter
from attrib.dataclass import is_dataclass
from attrib.descriptors.base import (
    Boolean,
    Bytes,
    Decimal,
    Field,
    FieldKwargs,
    FieldType,
    Float,
    Integer,
    Path as PathField,
    String,
    UUID as UUIDField,
)
from attrib.descriptors.datetime import Date, DateTime, Duration, Time, TimeZone
from attrib.descriptors.nested import Nested
from attrib.descriptors.networks import IPAddress, IPInterface, IPNetwork
from attrib.types import T

__field_mappings = {
    datetime.date: Date,
    datetime.time: Time,
    datetime.datetime: DateTime,
    datetime.tzinfo: TimeZone,
    datetime.timedelta: Duration,
    str: String,
    int: Integer,
    float: Float,
    bool: Boolean,
    decimal.Decimal: Decimal,
    bytes: Bytes,
    uuid.UUID: UUIDField,
    pathlib.Path: PathField,
    ipaddress.IPv4Address: IPAddress,
    ipaddress.IPv6Address: IPAddress,
    ipaddress.IPv4Network: IPAddress,
    ipaddress.IPv6Network: IPNetwork,
    ipaddress.IPv4Interface: IPAddress,
    ipaddress.IPv6Interface: IPInterface,
}
__lock = RLock()

FieldT = typing.TypeVar("FieldT", bound=Field)


@typing.overload
def register(
    typ: typing.Type[T],
    /,
    field_cls: typing.Type[FieldT],
) -> typing.Type[FieldT]: ...


@typing.overload
def register(
    typ: typing.Type[T], /
) -> typing.Callable[[typing.Type[FieldT]], typing.Type[FieldT]]: ...


@typing.overload
def register(
    typ: typing.Type[T], /, field_cls: None
) -> typing.Callable[[typing.Type[FieldT]], typing.Type[FieldT]]: ...


def register(
    typ: typing.Type[T], /, field_cls: typing.Optional[typing.Type[FieldT]] = None
) -> typing.Union[
    typing.Type[FieldT], typing.Callable[[typing.Type[FieldT]], typing.Type[FieldT]]
]:
    """
    Register a custom field class for a specific type.

    :param typ: The type to register the field for.
    :param field_cls: The field class to register. If None, a decorator will be returned.
    """

    def _decorator(
        cls: typing.Type[FieldT],
    ) -> typing.Type[FieldT]:
        with __lock:
            __field_mappings[typ] = cls
        return cls

    if field_cls is not None:
        return _decorator(field_cls)
    return _decorator


@typing.overload
def field(
    typ: typing.Type[Field[T]], /, *args, **kwargs: Unpack[FieldKwargs]
) -> Field[T]: ...


@typing.overload
def field(typ: FieldType[T], /, *args, **kwargs: Unpack[FieldKwargs]) -> Field[T]: ...


@typing.overload
def field(
    typ: typing.Type[Field[T]],
    /,
    *args,
    defer_build: bool,
    **kwargs: Unpack[FieldKwargs],
) -> Field[T]: ...


@typing.overload
def field(
    typ: FieldType[T], /, *args, defer_build: bool, **kwargs: Unpack[FieldKwargs]
) -> Field[T]: ...


@typing.overload
def field(typ: typing.Type[Field[T]], /, *args, **kwargs: typing.Any) -> Field[T]: ...


@typing.overload
def field(typ: FieldType[T], /, *args, **kwargs: typing.Any) -> Field[T]: ...


def field(
    typ: typing.Union[FieldType[T], typing.Type[Field[T]]],
    /,
    *args: typing.Any,
    defer_build: bool = False,
    **kwargs: typing.Any,
) -> Field[T]:
    """Create a field based on the provided type.

    :param type_: The type of the field.
    :param defer_build: Whether to defer building the field type when a forward reference is used.
    :param kwargs: Additional keyword arguments for the field.
    :return: An instance of the appropriate Field subclass.
    """
    if typ in __field_mappings:
        field_type = __field_mappings[typ]
        return field_type(*args, **kwargs)  # type: ignore[arg-type]

    if isinstance(typ, TypeAdapter):
        return Field(typ, *args, **kwargs)

    if isinstance(typ, type):
        # Check if it's a `Field` subclass
        if issubclass(typ, Field):
            return typ(*args, **kwargs)  # type: ignore[arg-type]
        
        # Check if it's a dataclass
        if is_dataclass(typ):
            return Nested(typ, *args, **kwargs)  # type: ignore[arg-type]

    # Handle generic `Field` types like `Field[int]`, `Choice[str]`
    if is_generic_type(typ):
        origin = typing.get_origin(typ)
        if isinstance(origin, type) and issubclass(origin, Field):
            type_args = typing.get_args(typ)
            if type_args:
                return origin(*type_args, *args, **kwargs)  # type: ignore[arg-type]
            return origin(*args, **kwargs)  # type: ignore[arg-type]

    # Fallbac to creating a `TypeAdapter`
    deserializer = kwargs.pop("deserializer", None)
    validator = kwargs.pop("validator", None)
    serializers = kwargs.pop("serializers", None)
    strict = kwargs.get("strict", False)
    adapter = TypeAdapter(
        typ,
        defer_build=defer_build,
        strict=strict,
        deserializer=deserializer,
        validator=validator,
        serializers=serializers,
    )
    return Field(adapter, *args, **kwargs)
