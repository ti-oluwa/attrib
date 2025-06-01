"""Data description classes"""

from collections.abc import Sequence
from contextvars import ContextVar
import typing
from functools import cache
from types import MappingProxyType
from typing_extensions import Unpack
from contextlib import contextmanager

from attrib.descriptors.base import Field, Value
from attrib.exceptions import (
    FrozenInstanceError,
    DeserializationError,
    ConfigurationError,
    ValidationError,
)
from attrib._typing import DataDict, RawData, KwArg


__all__ = [
    "Dataclass",
    "get_fields",
    "load",
    "deserialize",
    "deserialization_context",
    "get_field",
]


def get_fields(cls: typing.Type) -> typing.Dict[str, Field]:
    """
    Inspect and retrieve all data fields from a class.

    :param cls: The class to inspect.
    :return: A dictionary of field names and their corresponding Field instances.
    """
    if issubclass(cls, Dataclass) or hasattr(cls, "__fields__"):
        return dict(cls.__fields__)

    fields = {}
    for key, value in cls.__dict__.items():
        if isinstance(value, Field):
            fields[key] = value
    return fields


def _sort_by_name(item: typing.Tuple[str, Field]) -> str:
    return item[0]


def _repr(
    instance: "Dataclass",
) -> str:
    """Build a string representation of the dataclass instance."""
    fields = instance.__fields__
    field_strs = []
    instance_type = type(instance)
    for key, field in fields.items():
        value = field.__get__(instance, owner=instance_type)
        field_strs.append(f"{key}={value}")
    return f"{instance_type.__name__}({', '.join(field_strs)})"


def _str(
    instance: "Dataclass",
) -> str:
    """Build a string representation of the dataclass instance."""
    fields = instance.__fields__
    field_values = {}
    instance_type = type(instance)
    for key, field in fields.items():
        value = field.__get__(instance, owner=instance_type)
        field_values[key] = value
    return field_values.__repr__()


def _getitem(instance: "Dataclass", key: str) -> typing.Any:
    field = instance.__fields__[key]
    return field.__get__(instance, owner=type(instance))


def _setitem(instance: "Dataclass", key: str, value: typing.Any) -> None:
    field = instance.__fields__[key]
    field.__set__(instance, value)


def _frozen_setattr(instance: "Dataclass", key: str, value: Value) -> None:
    """Set an attribute on a frozen dataclass instance."""
    if not getattr(instance, "_initializing", False):
        raise FrozenInstanceError(
            f"Immutable instance. Cannot modify '{type(instance).__name__}.{key}'. "
        ) from None
    return object.__setattr__(instance, key, value)


def _frozen_delattr(instance: "Dataclass", key: str) -> None:
    """Delete an attribute from a frozen dataclass instance."""
    if key in instance.base_to_effective_name_map:
        raise FrozenInstanceError(
            f"Immutable instance. Cannot delete '{type(instance).__name__}.{key}'."
        ) from None

    return object.__delattr__(instance, key)


def _getstate(
    instance: "Dataclass",
) -> typing.Tuple[typing.Dict[str, typing.Any], typing.Dict[str, typing.Any]]:
    """Get the state of the dataclass instance."""
    fields = instance.__fields__
    field_values = {}
    instance_type = type(instance)
    for key, field in fields.items():
        value = field.__get__(instance, owner=instance_type)
        field_values[key] = value

    pickleable_attribute_names = getattr(instance, "__state_attributes__", [])
    if not pickleable_attribute_names:
        return field_values, {}

    attributes = {}
    for attr_name in pickleable_attribute_names:
        if attr_name in fields:
            continue
        if not hasattr(instance, attr_name):
            continue
        value = getattr(instance, attr_name)
        attributes[attr_name] = value

    return field_values, attributes


def _setstate(
    instance: "Dataclass",
    state: typing.Tuple[typing.Dict[str, typing.Any], typing.Dict[str, typing.Any]],
) -> "Dataclass":
    """Set the state of the dataclass instance."""
    field_values, attributes = state
    load(instance, field_values)
    for key, value in attributes.items():
        if key in instance.__fields__:
            continue
        setattr(instance, key, value)
    return instance


def _getnewargs(instance: "Dataclass") -> typing.Tuple:
    """Get the __new__ arguments for the dataclass instance."""
    return (), instance.__getstate__()  # type: ignore[return-value]


def _hash(instance: "Dataclass") -> int:
    """Compute the hash of the dataclass instance based on descriptor fields."""
    fields = instance.__fields__
    instance_type = type(instance)
    try:
        return hash(
            tuple(
                hash(field.__get__(instance, instance_type))
                for field in fields.values()
            )
        )
    except TypeError as exc:
        raise TypeError(f"Unhashable value in {instance}: {exc}")


def _eq(instance: "Dataclass", other: typing.Any) -> bool:
    """Compare two dataclass instances for equality."""
    if not isinstance(other, instance.__class__):
        return NotImplemented
    if instance is other:
        return True

    for field in instance.__fields__.values():
        if field.__get__(instance, type(instance)) != field.__get__(
            other, type(instance)
        ):
            return False
    return True


def _iter(instance: "Dataclass") -> typing.Iterator[typing.Tuple[str, typing.Any]]:
    """Iterate over the instance's fields and their values."""
    owner = type(instance)
    for key, field in instance.__fields__.items():
        yield key, field.__get__(instance, owner=owner)


def _get_slot_attribute_name(
    unique_prefix: str,
    field_name: str,
) -> str:
    return f"_{unique_prefix}_{field_name}"


def _build_slotted_namespace(
    namespace: typing.Dict[str, typing.Any],
    own_fields: typing.Iterable[str],
    additional_slots: typing.Optional[typing.Union[typing.Tuple[str], str]] = None,
    parent_slotted_attributes: typing.Optional[typing.Dict[str, str]] = None,
) -> typing.Dict[str, typing.Any]:
    """
    Build a namespace for a slotted dataclass.

    :param namespace: The original namespace of the dataclass.
    :param own_fields: The fields directly defined in the dataclass.
    :param additional_slots: Additional slots to include in the __slots__ attribute.
    :param parent_slotted_attributes: Slotted attributes from parent classes, if any.
    :return: The modified namespace with __slots__ and other attributes.
    """
    # Only add slots for fields defined in the class, i.e those that are not
    # inherited from a base class.
    slotted_attributes_names = {
        key: _get_slot_attribute_name("slotted", key) for key in own_fields
    }

    slots = set(slotted_attributes_names.values())
    if additional_slots:
        if isinstance(additional_slots, str):
            slots.add(additional_slots)
        else:
            slots.update(additional_slots)

    defined_slots = namespace.get("__slots__", None)
    if defined_slots:
        if isinstance(defined_slots, str):
            slots.add(defined_slots)
        else:
            slots.update(defined_slots)

    namespace["__slots__"] = tuple(slots)
    if parent_slotted_attributes:
        slotted_attributes_names |= parent_slotted_attributes

    namespace["__slotted_names__"] = slotted_attributes_names
    namespace.pop("__dict__", None)
    namespace.pop("__weakref__", None)
    return namespace


StrType: typing.TypeAlias = str
FieldName: typing.TypeAlias = str


class ConfigSchema(typing.TypedDict, total=False):
    """Configuration schema for Dataclass types"""

    frozen: bool
    """If True, the dataclass is immutable after creation."""
    slots: typing.Union[typing.Tuple[StrType], bool]
    """If True, use __slots__ for instance attribute storage.
        If a tuple, use as additional slots.
        If False, use __dict__ for instance attribute storage."""

    repr: bool
    """If True, add __repr__ method to the class, if it does not exist."""
    str: bool
    """If True, add __str__ method to the class, if it does not exist."""
    sort: typing.Union[
        bool, typing.Callable[[typing.Tuple[FieldName, Field]], typing.Any]
    ]
    """If True, sort fields by name. If a callable, use as the sort key.
        If False, do not sort fields."""
    hash: bool
    """If True, add __hash__ method to the class, if it does not exist. Should be used with `frozen=True`."""
    eq: bool
    """If True, add __eq__ method to the class, if it does not exist."""
    getitem: bool
    """If True, add __getitem__ method to the class, if it does not exist."""
    setitem: bool
    """If True, add __setitem__ method to the class, if it does not exist."""
    pickleable: bool
    """If True, adds __getstate__, __setstate__, and __getnewargs__ methods to the class, 
    if it does not exist. If False, do not add these methods.
    If None, use the default behavior of the dataclass."""


class Config(typing.NamedTuple):
    """Configuration for Dataclass types"""

    frozen: bool = False
    """If True, the dataclass is immutable after creation."""
    slots: typing.Union[typing.Tuple[StrType], bool] = False
    """If True, use __slots__ for instance attribute storage.
        If a tuple, use as additional slots.
        If False, use __dict__ for instance attribute storage."""
    repr: bool = False
    """If True, add __repr__ method to the class, if it does not exist."""
    str: bool = False
    """If True, add __str__ method to the class, if it does not exist."""
    sort: typing.Union[
        bool, typing.Callable[[typing.Tuple[FieldName, Field]], typing.Any]
    ] = False
    """If True, sort fields by name. If a callable, use as the sort key.
        If False, do not sort fields."""
    hash: bool = False
    """If True, add __hash__ method to the class, if it does not exist. Should be used with `frozen=True`."""
    eq: bool = True
    """If True, add __eq__ method to the class, if it does not exist."""
    getitem: bool = False
    """If True, add __getitem__ method to the class, if it does not exist."""
    setitem: bool = False
    """If True, add __setitem__ method to the class, if it does not exist."""
    pickleable: bool = False
    """If True, adds __getstate__, __setstate__, and __getnewargs__ methods to the class, 
    if they do not exist. If False, do not add these methods.
    If None, use the default behavior of the dataclass."""


def build_config(
    class_config: typing.Optional[Config] = None,
    bases: typing.Optional[typing.Tuple[typing.Type[typing.Any]]] = None,
    **meta_config: Unpack[ConfigSchema],
) -> Config:
    """
    Build a configuration for Dataclass types.

    Order of precedence (from lowest to highest):
    1. Base class(es) configuration
    2. Class configuration
    3. Meta configuration

    :param class_config: Configuration defined directly in the class using `__config__` class variable.
    :param bases: Base classes to inspect for configuration.
    :param meta_config: Additional configuration options defined in the metaclass.
    :return: A Config instance with the combined configuration.
    """
    config = {}

    if bases:
        for base in bases:
            if isinstance(getattr(base, "__config__", None), Config):
                config.update(base.__config__._asdict())

    if class_config:
        config.update(class_config._asdict())

    config.update(meta_config)
    return Config(**config)


class DataclassMeta(type):
    """Metaclass for Dataclass types"""

    def __new__(
        cls,
        name: str,
        bases: typing.Tuple[typing.Type],
        attrs: typing.Dict[str, typing.Any],
        **meta_config: Unpack[ConfigSchema],
    ):
        """
        Create a new Dataclass type.

        :param name: Name of the new class.
        :param bases: Base classes for the new class.
        :param attrs: Attributes and namespace for the new class.
        :param meta_config: Additional configuration options for the new class.
        :return: New Dataclass type
        """
        config = build_config(
            class_config=attrs.get("__config__", None),
            bases=bases,
            **meta_config,
        )
        attrs["__config__"] = config
        own_fields = {}
        fields = {}
        base_to_effective_name_map = {}
        effective_to_base_name_map = {}
        parent_slotted_attributes = {}

        # Inspect the base classes for fields and borrow them
        inspected = set()
        for base_ in bases:
            for cls_ in base_.__mro__[:-1]:
                if cls_ in inspected:
                    continue

                inspected.add(cls_)
                if not hasattr(cls_, "__fields__"):
                    continue

                if config.slots and hasattr(cls_, "__slotted_names__"):
                    parent_slotted_attributes.update(cls_.__slotted_names__)

                cls_ = typing.cast(typing.Type["Dataclass"], cls_)
                # Borrow fields from the base class
                fields.update(cls_.__fields__)
                base_to_effective_name_map.update(cls_.base_to_effective_name_map)
                effective_to_base_name_map.update(cls_.effective_to_base_name_map)

        for key, value in attrs.items():
            if isinstance(value, Field):
                value.post_init_validate()
                own_fields[key] = value
                fields[key] = value
                effective_name = value.alias or key
                base_to_effective_name_map[key] = effective_name
                effective_to_base_name_map[effective_name] = key

        if config.slots:
            # Replace the original namespace with a slotted one.
            slotted_namespace = _build_slotted_namespace(
                namespace=attrs.copy(),
                own_fields=own_fields.keys(),
                additional_slots=config.slots
                if isinstance(config.slots, Sequence)
                else None,
                parent_slotted_attributes=parent_slotted_attributes,
            )
            attrs = slotted_namespace

        if config.frozen:
            attrs["__setattr__"] = _frozen_setattr
            attrs["__delattr__"] = _frozen_delattr
            # Only allow frozen dataclasses to be iterable by default. We do not want to allow
            # iteration over mutable dataclasses as it can lead to unexpected behavior.
            if "__iter__" not in attrs:
                attrs["__iter__"] = _iter
        if config.repr and "__repr__" not in attrs:
            attrs["__repr__"] = _repr
        if config.str and "__str__" not in attrs:
            attrs["__str__"] = _str
        if config.getitem and "__getitem__" not in attrs:
            attrs["__getitem__"] = _getitem
        if config.setitem and "__setitem__" not in attrs:
            attrs["__setitem__"] = _setitem
        if config.hash and "__hash__" not in attrs:
            if not config.frozen:
                raise ConfigurationError(
                    "Cannot use __hash__ without frozen=True. Hashing is unsafe for mutable objects."
                    " Set frozen=True to enable hashing."
                )
            attrs["__hash__"] = cache(
                _hash
            )  # Cache the hash value since the instance is frozen
        if config.eq and "__eq__" not in attrs:
            attrs["__eq__"] = _eq
        if config.pickleable:
            if "__getstate__" not in attrs:
                attrs["__getstate__"] = _getstate
            if "__setstate__" not in attrs:
                attrs["__setstate__"] = _setstate
            if "__getnewargs__" not in attrs:
                attrs["__getnewargs__"] = _getnewargs

        if config.sort:
            sort_key = config.sort if callable(config.sort) else _sort_by_name
            sort_key = typing.cast(
                typing.Callable[[typing.Tuple[str, Field]], str], sort_key
            )
            fields_data = sorted(fields.items(), key=sort_key)
            fields = dict(fields_data)

        # Make read-only to prevent accidental modification
        attrs["__fields__"] = MappingProxyType(fields)
        attrs["base_to_effective_name_map"] = MappingProxyType(
            base_to_effective_name_map
        )
        attrs["effective_to_base_name_map"] = MappingProxyType(
            effective_to_base_name_map
        )
        new_cls = super().__new__(cls, name, bases, attrs)
        return new_cls


class Dataclass(metaclass=DataclassMeta):
    """
    Data description class.

    Define data structures with special descriptors.

    Dataclasses are defined by subclassing `Dataclass` and defining fields as class attributes.
    Dataclasses enforce type conversion, validation, and other behaviors on the fields.

    :param frozen: If True, the dataclass is immutable after creation.
    :param slots: If True, use __slots__ for instance attribute storage.
        If a tuple, use as additional slots.
        If False, use __dict__ for instance attribute storage.
    :param repr: If True, use dict representation for __repr__ or to use the default.
    :param str: If True, use dict representation for __str__ or to use the default.
    :param sort: If True, sort fields by name. If a callable, use as the sort key.
        If False, do not sort fields.
    :param getitem: If True, add __getitem__ method to the class.
    :param setitem: If True, add __setitem__ method to the class.

    Example:
    ```
    import attrib

    class Continent(attrib.Dataclass):
        name = attrib.String()
        population = attrib.Integer()


    class Country(attrib.Dataclass):
        name = attrib.String()
        code = attrib.String()
        population = attrib.Integer()
        continent = attrib.Nested(Continent)


    class City(attrib.Dataclass):
        name = attrib.String()
        country = attrib.Nested(Country)
        population = attrib.Integer()
        area = attrib.Float()
        postal_code = attrib.String(allow_null=True, default=None)


    africa = Continent(
        name="Africa",
        population=1_300_000_000,
    )
    kenya = Country(
        name="Kenya",
        code="KE",
        population=50_000_000,
        continent=africa,
    )
    nairobi = City(
        name="Nairobi",
        country=kenya,
        population=4_000_000,
        area="696.1",
        postal_code="00100",
    )

    print(attrib.serialize(nairobi, fmt="json"))
    # Output:
    # {
    #     "name": "Nairobi",
    #     "country": {
    #         "name": "Kenya",
    #         "code": "KE",
    #         "population": 50000000,
    #         "continent": {
    #             "name": "Africa",
    #             "population": 1300000000,
    #         }
    #     },
    #     "population": 4000000,
    #     "area": 696.1,
    #     "postal_code": "00100"
    # }
    ```
    """

    __slots__: typing.ClassVar[typing.Tuple[str, ...]] = (
        "__weakref__",
        "_initializing",
        "__fields_set__",
    )
    __state_attributes__: typing.ClassVar[typing.Tuple[str, ...]] = ()
    """
    Attributes to be included in the state of the dataclass when __getstate__ is called,
    usually during pickling
    """
    __config__: typing.ClassVar[Config] = Config(slots=True)
    """Configuration for the dataclass."""
    __fields__: typing.ClassVar[typing.Mapping[str, Field[typing.Any]]] = {}
    """Mapping of field names to their corresponding Field instances."""
    base_to_effective_name_map: typing.ClassVar[typing.Mapping[str, str]] = {}
    """Mapping of base field names to effective field names."""
    effective_to_base_name_map: typing.ClassVar[typing.Mapping[str, str]] = {}
    """Mapping of effective field names to base field names."""

    @typing.overload
    def __init__(self, data: None = None) -> None:
        """Initialize the dataclass with no data."""
        ...

    @typing.overload
    def __init__(
        self,
        data: RawData,
        **kwargs: KwArg[typing.Any],
    ) -> None:
        """Initialize the dataclass with raw data."""
        ...

    @typing.overload
    def __init__(self, data: None = None, **kwargs: KwArg[typing.Any]) -> None:
        """Initialize the dataclass with keyword arguments."""
        ...

    def __init__(
        self,
        data: typing.Optional[RawData] = None,
        **kwargs: KwArg[typing.Any],
    ) -> None:
        """
        Initialize the dataclass with raw data or keyword arguments.

        :param data: Raw data to initialize the dataclass with.
        :param kwargs: Keyword arguments with values for the fields in the dataclass.
        """
        object.__setattr__(self, "_initializing", True)
        self.__fields_set__: typing.Set[str] = set()
        combined = {**dict(data or {}), **kwargs}  # type: ignore[assignment]
        load(self, data=combined)
        object.__setattr__(self, "_initializing", False)

    def __init_subclass__(cls, **kwargs: Unpack[ConfigSchema]) -> None:
        """Ensure that subclasses define fields."""
        if len(cls.__fields__) == 0:
            raise ConfigurationError("Dataclasses must define fields")
        return


DataclassTco = typing.TypeVar("DataclassTco", bound=Dataclass, covariant=True)

_fail_fast: ContextVar[bool] = ContextVar("fail_fast", default=False)
"""
`fail_fast` context variable to control whether to stop on the first error encountered during loading
data onto dataclass instances.
"""
_ignore_extras: ContextVar[bool] = ContextVar("ignore_extras", default=False)
"""
`ignore_extras` context variable to control whether to ignore extra fields not defined in the dataclass
"""


@contextmanager
def deserialization_context(
    fail_fast: typing.Optional[bool] = None, ignore_extras: typing.Optional[bool] = None
) -> typing.Generator[None, None, None]:
    """
    Deserialization context manager.

    All deserialization occurring within this context will use the defined settings.

    :param fail_fast: If True, stop on the first error encountered during loading.
    :param ignore_extras: If True, ignore extra fields not defined in the dataclass

    Leaving any of this parameters as None will leave the current context variable value unchanged.
    """
    if fail_fast is not None:
        fail_fast_token = _fail_fast.set(fail_fast)
    else:
        fail_fast_token = None
    if ignore_extras is not None:
        ignore_extras_token = _ignore_extras.set(ignore_extras)
    else:
        ignore_extras_token = None
    try:
        yield
    finally:
        if fail_fast_token is not None:
            _fail_fast.reset(fail_fast_token)
        if ignore_extras_token is not None:
            _ignore_extras.reset(ignore_extras_token)


def load(
    instance: DataclassTco,
    data: DataDict,
) -> DataclassTco:
    """
    Load raw data unto the dataclass instance.

    :param data: Mapping of raw data to initialize the dataclass instance with.
    :param ignore_extras: If True, ignore extra fields not defined in the dataclass.
        Else, raise a DeserializationError if extra fields are found.
    :param fail_fast: If True, stop on the first error encountered during loading.
    :raises DeserializationError: If there are errors during deserialization.
    :return: This same instance with the raw data loaded.
    """
    ignore_extras = _ignore_extras.get()
    if not ignore_extras:
        extra_keys = set(data) - set(instance.__fields__)
        if extra_keys:
            raise DeserializationError(
                f"Unknown fields found: {', '.join(extra_keys)}",
                parent_name=type(instance).__name__,
                input_type="dict",
                expected_type=type(instance).__name__,
                code="unknown_fields",
            )

    fail_fast = _fail_fast.get()
    error = None
    for name, field in instance.__fields__.items():
        key = instance.base_to_effective_name_map[name]
        try:
            if key not in data:
                field.set_default(instance)
                continue

            field.__set__(instance, data[key])
        except (DeserializationError, ValidationError) as exc:
            if fail_fast:
                raise DeserializationError.from_exception(
                    exc,
                    parent_name=type(instance).__name__,
                ) from exc
            else:
                if error is None:
                    error = DeserializationError.from_exception(
                        exc,
                        parent_name=type(instance).__name__,
                    )
                else:
                    error.add(
                        exc,
                        parent_name=type(instance).__name__,
                    )

    if error is not None:
        raise error
    return instance


def _from_attributes(
    dataclass_: typing.Type[DataclassTco],
    obj: typing.Any,
) -> DataclassTco:
    """
    Convert an object to a dataclass instance by loading fields using
    the object's attributes

    :param obj: The object to convert.
    :param dataclass_: The dataclass type to convert to.
    :param fail_fast: If True, stop on the first error encountered during conversion.
    :return: The dataclass instance.
    """
    if dataclass_.__config__.frozen:
        raise ConfigurationError(
            f"Cannot convert {obj!r} to a frozen dataclass. Use the constructor instead."
        )
    fail_fast = _fail_fast.get()
    instance = dataclass_()
    error = None
    for name, field in dataclass_.__fields__.items():
        key = dataclass_.base_to_effective_name_map[name]
        try:
            if not hasattr(obj, key):
                field.set_default(instance)
                continue

            value = getattr(obj, key)
            field.__set__(instance, value)
        except (DeserializationError, ValidationError) as exc:
            if fail_fast:
                raise DeserializationError.from_exception(
                    exc,
                    parent_name=type(instance).__name__,
                    location=[name],
                ) from exc
            else:
                if error is None:
                    error = DeserializationError.from_exception(
                        exc,
                        parent_name=type(instance).__name__,
                        location=[name],
                    )
                else:
                    error.add(
                        exc,
                        parent_name=type(instance).__name__,
                        location=[name],
                    )

    if error is not None:
        raise error
    return instance


@typing.overload
def deserialize(
    dataclass_: typing.Type[DataclassTco],
    obj: RawData,
    *,
    fail_fast: typing.Optional[bool] = None,
    ignore_extras: typing.Optional[bool] = None,
) -> DataclassTco: ...


@typing.overload
def deserialize(
    dataclass_: typing.Type[DataclassTco],
    obj: typing.Any,
    *,
    from_attributes: bool = False,
    fail_fast: typing.Optional[bool] = None,
    ignore_extras: typing.Optional[bool] = None,
) -> DataclassTco: ...


def deserialize(
    dataclass_: typing.Type[DataclassTco],
    obj: typing.Union[RawData, typing.Any],
    *,
    from_attributes: bool = False,
    fail_fast: typing.Optional[bool] = None,
    ignore_extras: typing.Optional[bool] = None,
) -> DataclassTco:
    """
    Deserialize an object to a dataclass instance.

    :param obj: The object to deserialize.
    :param dataclass_: The dataclass type to convert to.
    :param from_attributes: If True, load fields using the object's attributes.
    :param fail_fast: If True, stop on the first error encountered during deserialization.
    :param ignore_extras: If True, ignore extra fields not defined in the dataclass.
    :return: The dataclass instance.
    """
    if obj is None:
        raise DeserializationError(
            "Cannot deserialize 'None'",
            parent_name=dataclass_.__name__,
            input_type="null",
            expected_type=dataclass_.__name__,
            code="invalid_value",
        )

    with deserialization_context(fail_fast=fail_fast, ignore_extras=ignore_extras):
        if from_attributes:
            return _from_attributes(dataclass_, obj)
        return dataclass_(obj)


def get_field(
    cls: typing.Type[Dataclass],
    field_name: str,
) -> typing.Optional[Field]:
    """
    Get a field by its name.

    :param cls: The Dataclass type to search in.
    :param field_name: The name of the field to retrieve.
    :return: The field instance or None if not found.
    """
    field = cls.__fields__.get(field_name, None)
    if field is None and field_name in cls.effective_to_base_name_map:
        field_name = cls.effective_to_base_name_map[field_name]
        field = cls.__fields__.get(field_name, None)
    return field
