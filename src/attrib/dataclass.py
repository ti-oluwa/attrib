"""Data description classes"""

from collections.abc import Iterable, Mapping, Sequence
import sys
import typing
import copy as pycopy
from functools import partial
from typing_extensions import Unpack, Self, TypeAlias
import warnings

from attrib._utils import is_generic_type
from attrib.descriptors.base import Field, Value
from attrib.exceptions import (
    FrozenInstanceError,
    DeserializationError,
    ConfigurationError,
    ValidationError,
)
from attrib.types import DataDict, RawData, KwArg
from attrib.contextmanagers import (
    deserialization_context,
    fail_fast_ctx_var,
    by_name_ctx_var,
    is_valid_ctx_var,
    ignore_extras_ctx_var,
)


__all__ = [
    "Dataclass",
    "Config",
    "deserialize",
    "copy",
    "get_field",
    "get_fields",
]


def _sort_by_name(item: typing.Tuple[str, Field]) -> str:
    return item[0]


def _repr(
    instance: "Dataclass",
) -> str:
    """Build a string representation of the dataclass instance."""
    field_strs = []
    instance_type = type(instance)
    for field in instance.__repr_fields__:
        value = field.__get__(instance, instance_type)
        field_strs.append(f"{field.name}={value}")
    return f"{instance_type.__name__}({', '.join(field_strs)})"


def _str(
    instance: "Dataclass",
) -> str:
    """Build a string representation of the dataclass instance."""
    field_values = {}
    instance_type = type(instance)
    for field in instance.__repr_fields__:
        value = field.__get__(instance, instance_type)
        field_values[field.name] = value
    return field_values.__repr__()


def _getitem(instance: "Dataclass", key: str) -> typing.Any:
    field = instance.__dataclass_fields__[key]
    return field.__get__(instance, type(instance))


def _setitem(instance: "Dataclass", key: str, value: typing.Any) -> None:
    field = instance.__dataclass_fields__[key]
    field.__set__(instance, value)


def _frozen_setattr(instance: "Dataclass", key: str, value: Value) -> None:
    """Set an attribute on a frozen dataclass instance."""
    if (
        not getattr(instance, "_initializing", False)
        and key not in instance.__state_attributes__
    ):
        raise FrozenInstanceError(
            f"Immutable instance. Cannot modify '{type(instance).__name__}.{key}'. "
        ) from None
    return object.__setattr__(instance, key, value)


def _frozen_delattr(instance: "Dataclass", key: str) -> None:
    """Delete an attribute from a frozen dataclass instance."""
    if key in type(instance)._name_map:
        raise FrozenInstanceError(
            f"Immutable instance. Cannot delete '{type(instance).__name__}.{key}'."
        ) from None

    return object.__delattr__(instance, key)


def _getstate(
    instance: "Dataclass",
) -> typing.Tuple[typing.Dict[str, typing.Any], typing.Dict[str, typing.Any]]:
    """Get the state of the dataclass instance."""
    field_values = dict(_iter(instance))
    state_attributes = getattr(instance, "__state_attributes__", [])
    if not state_attributes:
        return field_values, {}

    attributes = {}
    for attr_name in state_attributes:
        if (value := getattr(instance, attr_name, _missing)) is _missing:
            continue
        # Copy value to avoid issues with shared mutable objects between instances
        if attr_name == "__fields_set__":
            attributes[attr_name] = set(value)  # type: ignore[assignment]
        else:
            attributes[attr_name] = pycopy.copy(value)
    return field_values, attributes


def _setstate(
    instance: "Dataclass",
    state: typing.Tuple[typing.Dict[str, typing.Any], typing.Dict[str, typing.Any]],
) -> "Dataclass":
    """Set the state of the dataclass instance."""
    field_values, attributes = state
    with deserialization_context(by_name=True):
        instance = load_valid(
            instance,
            fields=instance.__dataclass_fields__.values(),
            data=field_values,
        )

    for key, value in attributes.items():
        setattr(instance, key, value)
    return instance


def _getnewargs_ex(
    instance: "Dataclass",
) -> typing.Tuple[typing.Tuple[typing.Any, ...], typing.Dict[str, typing.Any]]:
    """Get the __new__ arguments for the dataclass instance."""
    return (), {}


def _hash_any(value: typing.Any) -> int:
    """Compute the hash of a value, handling exceptions for unhashable types."""
    try:
        return hash(value)
    except TypeError:
        return id(value)


def _hash(instance: "Dataclass") -> int:
    """Compute the hash of the dataclass instance based on descriptor fields."""
    if (computed_hash := instance.__cache__.get("__hash__", None)) is None:
        instance_type = type(instance)
        values = []
        for field in instance.__hash_fields__:
            value = field.__get__(instance, instance_type)
            if isinstance(value, Iterable) and not isinstance(
                value, (str, bytes, Mapping)
            ):
                values.append(tuple(_hash_any(item) for item in value))
            else:
                values.append(_hash_any(value))

        computed_hash = hash(
            (
                instance_type,
                tuple(values),
                tuple(instance.__state_attributes__),
            )
        )
        instance.__cache__["__hash__"] = computed_hash
    return typing.cast(int, computed_hash)


def _eq(instance: "Dataclass", other: typing.Any) -> bool:
    """Compare two dataclass instances for equality."""
    if not isinstance(other, instance.__class__):
        return NotImplemented
    if instance is other:
        return True

    instance_type = type(instance)
    for field in instance.__eq_fields__:
        if field.__get__(instance, instance_type) != field.__get__(
            other, instance_type
        ):
            return False
    return True


def _iter(instance: "Dataclass") -> typing.Iterator[typing.Tuple[str, typing.Any]]:
    """Iterate over the instance's fields and their values."""
    owner = type(instance)
    for key, field in instance.__dataclass_fields__.items():
        yield key, field.__get__(instance, owner)


def _get_ordering_values(
    instance: "Dataclass",
) -> typing.Tuple[typing.Any, ...]:
    """
    Get the ordering values for the dataclass instance.

    Caches the values to avoid recomputing them multiple times for frozen instances.
    """
    if instance.__config__.frozen:
        cache_key = "_ordering_values"
        if (values := instance.__cache__.get(cache_key, None)) is None:
            instance_type = type(instance)
            values = tuple(
                field.__get__(instance, instance_type)
                for field in instance.__ordering_fields__
            )
            instance.__cache__[cache_key] = values
        return values

    instance_type = type(instance)
    return tuple(
        field.__get__(instance, instance_type) for field in instance.__ordering_fields__
    )


def _lt(
    instance: "Dataclass",
    other: typing.Any,
) -> bool:
    """Compare two dataclass instances for less than."""
    if not isinstance(other, instance.__class__):
        return NotImplemented
    if getattr(instance, "_initializing", False):
        # Incomplete state during initialization is a safety concern for ordering.
        return False
    if instance is other:
        return False
    return _get_ordering_values(instance) < _get_ordering_values(other)


def _le(
    instance: "Dataclass",
    other: typing.Any,
) -> bool:
    """Compare two dataclass instances for less than or equal to."""
    if not isinstance(other, instance.__class__):
        return NotImplemented
    if getattr(instance, "_initializing", False):
        return False
    if instance is other:
        return True
    return _get_ordering_values(instance) <= _get_ordering_values(other)


def _gt(
    instance: "Dataclass",
    other: typing.Any,
) -> bool:
    """Compare two dataclass instances for greater than."""
    if not isinstance(other, instance.__class__):
        return NotImplemented
    if getattr(instance, "_initializing", False):
        return False
    if instance is other:
        return False
    return _get_ordering_values(instance) > _get_ordering_values(other)


def _ge(
    instance: "Dataclass",
    other: typing.Any,
) -> bool:
    """Compare two dataclass instances for greater than or equal to."""
    if not isinstance(other, instance.__class__):
        return NotImplemented
    if getattr(instance, "_initializing", False):
        return False
    if instance is other:
        return True
    return _get_ordering_values(instance) >= _get_ordering_values(other)


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
    slotted_attributes_names = {key: f"_slotted_{key}" for key in own_fields}

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
        slotted_attributes_names.update(parent_slotted_attributes)

    namespace["__slotted_names__"] = slotted_attributes_names
    namespace.pop("__dict__", None)
    namespace.pop("__weakref__", None)
    return namespace


StrType: TypeAlias = str
FieldName: TypeAlias = str


class ConfigSchema(typing.TypedDict, total=False):
    """Configuration schema for Dataclass types"""

    frozen: bool
    """If True, the dataclass is immutable after creation."""
    slots: typing.Union[typing.Tuple[StrType], bool]
    """If True, use __slots__ for instance attribute storage.
        If a tuple, use as additional slots.
        If False, use __dict__ for instance attribute storage."""

    repr: bool
    """
    If True, add __repr__ method to the class, if it does not exist.

    Only fields with `repr=True` will be used to build the repr.
    """
    str: bool
    """If True, add __str__ method to the class, if it does not exist."""
    sort: typing.Union[
        bool, typing.Callable[[typing.Tuple[FieldName, Field]], typing.Any]
    ]
    """If True, sort fields by name. If a callable, use as the sort key.
        If False, do not sort fields."""
    hash: bool
    """
    If True, add __hash__ method to the class, if it does not exist. Should be used with `frozen=True`.
    
    Hashing is unsafe for mutable objects. Set frozen=True to enable hashing.
    Also, the class must have at least one field with `hash=True` to support hashing.
    """
    eq: bool
    """
    If True, add __eq__ method to the class, if it does not exist.
    
    Equality is only supported if the class has at least one field with `eq=True`.
    """
    order: bool
    """
    If True, add __lt__, __le__, __gt__, and __ge__ methods to the class, if it does not exist.

    Ordering is only supported if the class has at least one field with `compare=True`. It also
    only based on fields that have `compare=True` set. Equality and ordering are mutually exclusive.
    Hence, fields used for equality comparison (i.e., `eq=True`) will not be considered for ordering
    by default. 
    """
    getitem: bool
    """If True, add __getitem__ method to the class, if it does not exist."""
    setitem: bool
    """If True, add __setitem__ method to the class, if it does not exist."""
    pickleable: bool
    """If True, adds __getstate__, __setstate__, and __getnewargs__ methods to the class, 
    if it does not exist. If False, do not add these methods.
    If None, use the default behavior of the dataclass."""


@typing.final
class Config(typing.NamedTuple):
    """Configuration for Dataclass types"""

    frozen: bool = False
    """If True, the dataclass is immutable after creation."""
    slots: typing.Union[typing.Tuple[StrType], bool] = False
    """If True, use __slots__ for instance attribute storage.
        If a tuple, use as additional slots.
        If False, use __dict__ for instance attribute storage."""
    repr: bool = False
    """
    If True, add __repr__ method to the class, if it does not exist.

    Only fields with `repr=True` will be used to build the repr.
    """
    str: bool = False
    """If True, add __str__ method to the class, if it does not exist."""
    sort: typing.Union[
        bool, typing.Callable[[typing.Tuple[FieldName, Field]], typing.Any]
    ] = False
    """If True, sort fields by name. If a callable, use as the sort key.
        If False, do not sort fields."""
    hash: bool = False
    """
    If True, add __hash__ method to the class, if it does not exist. Should be used with `frozen=True`.
    
    Hashing is unsafe for mutable objects. Set frozen=True to enable hashing.
    Also, the class must have at least one field with `hash=True` to support hashing.
    """
    eq: bool = True
    """
    If True, add __eq__ method to the class, if it does not exist.
    
    Equality is only supported if the class has at least one field with `eq=True`.
    """
    order: bool = False
    """
    If True, add __lt__, __le__, __gt__, and __ge__ methods to the class, if it does not exist.

    Ordering is only supported if the class has at least one field with `compare=True`. It also
    only based on fields that have `compare=True` set. Equality and ordering are mutually exclusive.
    Hence, fields used for equality comparison (i.e., `eq=True`) will not be considered for ordering
    by default. 
    """
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
            if base_config := getattr(base, "__config__", None):
                config.update(base_config._asdict())

    if class_config:
        config.update(class_config._asdict())

    config.update(meta_config)
    return Config(**config)


FieldMap: TypeAlias = typing.Mapping[str, Field[typing.Any]]
"""A mapping of field names to their corresponding Field instances."""
FieldDict: TypeAlias = typing.Dict[str, Field[typing.Any]]
"""A mapping of field names to their corresponding Field instances."""
NameMap: TypeAlias = typing.Mapping[str, str]
"""A mapping of names"""
NameDict: TypeAlias = typing.Dict[str, str]
"""A mapping of names"""


def build_auxilliary_fields(
    fields: FieldDict,
) -> typing.Dict[str, typing.Tuple[Field[typing.Any]]]:
    auxilliary_fields = {}
    auxilliary_fields["__init_fields__"] = tuple(
        field for field in fields.values() if field.init
    )
    auxilliary_fields["__repr_fields__"] = tuple(
        field for field in fields.values() if field.repr
    )
    auxilliary_fields["__hash_fields__"] = tuple(
        field for field in fields.values() if field.hash
    )
    auxilliary_fields["__eq_fields__"] = tuple(
        field for field in fields.values() if field.eq
    )
    ordering_fields = tuple(
        field for field in fields.values() if field.order is not None
    )
    auxilliary_fields["__ordering_fields__"] = sorted(
        ordering_fields,
        key=lambda f: f.order
        if f.order is not None
        else float(
            "inf"
        ),  # Just to please the type checker since `f.order` can be None
    )
    return auxilliary_fields


def is_dataclass(cls: typing.Type[typing.Any]) -> bool:
    return hasattr(cls, "__dataclass_fields__") or issubclass(cls, Dataclass)


def type_has_dataclass(typ: typing.Any) -> bool:
    """
    Check if a type contains a dataclass.

    :param typ: The type to check.
    :return: True if the type is a dataclass or contains
        a dataclass as a field, False otherwise.
    """
    if is_generic_type(typ):
        # Handle generic types like List[Dataclass]
        return any(
            type_has_dataclass(arg) for arg in typ.__args__ if isinstance(arg, type)
        )
    return is_dataclass(typ)


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
        own_fields: FieldDict = {}
        fields: FieldDict = {}
        _name_map: NameDict = {}
        _effective_name_map: NameDict = {}
        parent_slotted_attributes = {}

        # Inspect the base classes for fields and borrow them
        inspected: typing.Set[typing.Type[typing.Any]] = set()
        for base_ in bases:
            for cls_ in base_.__mro__[:-1]:
                if cls_ in inspected:
                    continue

                inspected.add(cls_)
                if not (cls_fields := getattr(cls_, "__dataclass_fields__", None)):
                    continue

                if config.slots and (
                    slotted_names := getattr(cls_, "__slotted_names__", None)
                ):
                    parent_slotted_attributes.update(slotted_names)

                # Borrow fields from the base class
                fields.update(cls_fields)
                _name_map.update(cls_._name_map)
                _effective_name_map.update(cls_._effective_name_map)

        for key, value in attrs.items():
            if isinstance(value, Field):
                value.post_init()
                own_fields[key] = value
                fields[key] = value
                effective_name = value.alias or key
                _name_map[key] = effective_name
                _effective_name_map[effective_name] = key

        auxilliary_fields = build_auxilliary_fields(fields)
        attrs.update(auxilliary_fields)

        if config.order and config.eq:
            eq_fields_set = set(attrs["__eq_fields__"])
            ordering_fields_set = set(attrs["__ordering_fields__"])
            # Check for potential inconsistencies where fields are used for ordering but not equality
            if ordering_fields_set and eq_fields_set:
                ordering_only = ordering_fields_set - eq_fields_set
                if ordering_only:
                    warnings.warn(
                        f"Dataclass '{name}' has fields {ordering_only} used for ordering but not "
                        f"equality. This may lead to inconsistent behavior where a == b but a < b "
                        f"or b < a. Consider setting both 'eq' and 'compare' to True for these fields.",
                        RuntimeWarning,
                    )

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
            if fields and not attrs["__repr_fields__"]:
                raise ConfigurationError(
                    "Cannot add __repr__ without fields with `repr=True`. No fields with `repr=True` found."
                )
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

            if fields and not attrs["__hash_fields__"]:
                raise ConfigurationError(
                    "Cannot use __hash__ without fields with `hash=True`. No fields with `hash=True` found."
                )
            attrs["__hash__"] = _hash

        if config.eq and "__eq__" not in attrs:
            if fields and not attrs["__eq_fields__"]:
                raise ConfigurationError(
                    "Cannot use __eq__ without fields with `eq=True`. No fields with `eq=True` found."
                )
            attrs["__eq__"] = _eq

        if config.pickleable:
            if "__getstate__" not in attrs:
                attrs["__getstate__"] = _getstate
            if "__setstate__" not in attrs:
                attrs["__setstate__"] = _setstate
            if "__getnewargs__" not in attrs:
                attrs["__getnewargs_ex__"] = _getnewargs_ex
        if config.order:
            if fields and not attrs["__ordering_fields__"]:
                raise ConfigurationError(
                    "Cannot use ordering methods without fields with `order` set."
                )

            if "__lt__" not in attrs:
                attrs["__lt__"] = _lt
            if "__le__" not in attrs:
                attrs["__le__"] = _le
            if "__gt__" not in attrs:
                attrs["__gt__"] = _gt
            if "__ge__" not in attrs:
                attrs["__ge__"] = _ge

        if config.sort:
            sort_key = config.sort if callable(config.sort) else _sort_by_name
            sort_key = typing.cast(
                typing.Callable[[typing.Tuple[str, Field]], str], sort_key
            )
            fields_data = sorted(fields.items(), key=sort_key)
            fields = typing.cast(FieldDict, dict(fields_data))

        if (state_attributes := attrs.get("__state_attributes__", None)) and set(
            state_attributes
        ).intersection(fields.keys()):
            raise ConfigurationError(
                "Cannot use fields as state attributes. "
                "State attributes must not overlap with field names."
            )

        attrs["__dataclass_fields__"] = fields
        attrs["_name_map"] = _name_map
        attrs["_effective_name_map"] = _effective_name_map
        new_cls = super().__new__(cls, name, bases, attrs)
        return new_cls

    def __init__(cls, *args: typing.Any, **kwargs: typing.Any) -> None:
        """
        Initialize the Dataclass type.

        :param args: Positional arguments passed to the metaclass.
        :param kwargs: Keyword arguments passed to the metaclass.
        """
        super().__init__(*args, **kwargs)
        # Update the class annotations after all fields defined in the class
        # have been processed (all forward refs resolved) and bound to the class.
        fields_annotations = {}
        for field_name, field in cls.__dataclass_fields__.items():  # type: ignore
            annotation = field.__get_type_hint__()
            field._meta["_nested"] = type_has_dataclass(annotation)
            fields_annotations[field_name] = annotation

        cls_annotations: typing.Dict[str, typing.Any] = getattr(
            cls, "__annotations__", {}
        )
        cls.__annotations__ = {**cls_annotations, **fields_annotations}
        cls.__fields_annotations__ = fields_annotations


class Dataclass(metaclass=DataclassMeta):
    """
    Data description class.

    Dataclasses are defined by subclassing `Dataclass` and defining fields as class attributes.
    """

    __slots__: typing.ClassVar[typing.Tuple[str, ...]] = (
        "__weakref__",
        "_initializing",
        "__fields_set__",
        "__cache__",
    )
    __state_attributes__: typing.ClassVar[typing.Tuple[str, ...]] = ("__fields_set__",)
    """
    Attributes to be included in the state of the dataclass when __getstate__ is called,
    usually during pickling
    """
    __config__: typing.ClassVar[Config] = Config()
    """Configuration for the dataclass."""
    __dataclass_fields__: typing.ClassVar[FieldMap]
    """Mapping of field names to their corresponding Field instances."""
    __init_fields__: typing.ClassVar[typing.Tuple[Field[typing.Any], ...]]
    """Fields to include when instantiating the dataclass."""
    __repr_fields__: typing.ClassVar[typing.Tuple[Field[typing.Any], ...]]
    """Fields to include in the __repr__ method."""
    __hash_fields__: typing.ClassVar[typing.Tuple[Field[typing.Any], ...]]
    """Fields to include in the __hash__ method."""
    __eq_fields__: typing.ClassVar[typing.Tuple[Field[typing.Any], ...]]
    """Fields to include in the __eq__ method."""
    __ordering_fields__: typing.ClassVar[typing.Tuple[Field[typing.Any], ...]]
    """Fields to include in the ordering methods (__lt__, __le__, __gt__, __ge__)."""
    __fields_annotations__: typing.ClassVar[typing.Dict[str, typing.Any]]
    """Annotations for the fields in the dataclass."""
    _name_map: typing.ClassVar[NameMap]
    """Mapping of actual field names to effective field names."""
    _effective_name_map: typing.ClassVar[NameMap]
    """Mapping of effective field names to actual field names."""

    def __new__(cls, *args: typing.Any, **kwargs: typing.Any) -> Self:
        """
        Create a new instance of the dataclass.

        :param args: Positional arguments to pass to the dataclass constructor
        :param kwargs: Keyword arguments to pass to the dataclass constructor
        :return: A new instance of the dataclass.
        """
        instance = super().__new__(cls)
        object.__setattr__(instance, "__fields_set__", set())
        object.__setattr__(instance, "__cache__", {})
        return instance

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
        self.__fields_set__: typing.Set[str]
        self.__cache__: typing.Dict[str, typing.Any]

        object.__setattr__(self, "_initializing", True)
        combined = {**dict(data or {}), **kwargs}  # type: ignore[assignment]
        load_raw(
            self,
            fields=type(self).__init_fields__,
            data=combined,
        )
        object.__setattr__(self, "_initializing", False)

    def __init_subclass__(cls, **kwargs: Unpack[ConfigSchema]) -> None:
        """Ensure that subclasses define fields."""
        if len(cls.__dataclass_fields__) == 0:
            raise ConfigurationError("Dataclasses must define fields")
        return

    def __copy__(self) -> Self:
        """
        Create a shallow copy of the dataclass instance.

        :return: A new instance of the dataclass with the same field values.
        """
        return copy(self)

    def __deepcopy__(
        self, memo: typing.Optional[typing.Dict[int, typing.Any]] = None
    ) -> Self:
        """
        Create a deep copy of the dataclass instance.

        :param memo: A memo dictionary to avoid infinite recursion.
        :return: A new instance of the dataclass with deep copied field values.
        """
        if memo is None:
            memo = {}
        if (_id := id(self)) in memo:
            return memo[_id]

        memo[_id] = self
        return copy(self, _memo=memo)


DataclassTco = typing.TypeVar("DataclassTco", bound=Dataclass, covariant=True)

_missing = object()
"""Sentinel representing a missing value in a data dict"""


def load_raw(
    instance: DataclassTco,
    fields: typing.Iterable[Field[typing.Any]],
    data: DataDict,
) -> DataclassTco:
    """
    Load raw data unto the dataclass instance.

    :param instance: The dataclass instance to load data unto.
    :param fields: Iterable of fields to be populated in the dataclass.
    :param data: Mapping of raw data to initialize the dataclass instance with.
    :raises DeserializationError: If there are errors during deserialization.
    :return: This same instance with the raw data loaded.
    """
    ignore_extras = ignore_extras_ctx_var.get()
    if not ignore_extras:
        extra_keys = set(data.keys()) - {field.name for field in fields}
        if extra_keys:
            raise DeserializationError(
                f"Unknown field(s) found: {', '.join(extra_keys)}",
                parent_name=type(instance).__name__,
                input_type="dict",
                expected_type=type(instance).__name__,
                code="unknown_fields",
                context={
                    "extra_fields": extra_keys,
                },
            )

    if is_valid_ctx_var.get():
        return load_valid(instance, fields, data)

    error = None
    fail_fast = fail_fast_ctx_var.get()
    by_name = by_name_ctx_var.get()
    name_map = type(instance)._name_map
    for field in fields:
        name: str = field.name  # type: ignore[assignment]
        try:
            if by_name:
                if (value := data.get(name, _missing)) is _missing:
                    field.set_default(instance)
                    continue
            else:
                effective_name = name_map[name]
                if (value := data.get(effective_name, _missing)) is _missing:
                    if (
                        effective_name == name
                        or (value := data.get(name, _missing)) is _missing
                    ):
                        field.set_default(instance)
                        continue

            field.__set__(instance, value)
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


def load_valid(
    instance: DataclassTco,
    fields: typing.Iterable[Field[typing.Any]],
    data: DataDict,
) -> DataclassTco:
    """
    Load already validated data unto the dataclass instance.

    :param instance: The dataclass instance to load data unto.
    :param fields: Iterable of fields to be populated in the dataclass.
    :param data: Mapping of raw data to initialize the dataclass instance with.
    :return: This same instance with the raw data loaded and validated.
    """
    by_name = by_name_ctx_var.get()
    fields_set = instance.__fields_set__
    name_map = type(instance)._name_map
    for field in fields:
        name: str = field.name  # type: ignore[assignment]
        if by_name:
            if (value := data.get(name, _missing)) is _missing:
                field.set_default(instance)
                continue
        else:
            effective_name = name_map[name]
            if (value := data.get(effective_name, _missing)) is _missing:
                if (
                    effective_name == name
                    or (value := data.get(name, _missing)) is _missing
                ):
                    field.set_default(instance)
                    continue

        field._set_value(
            instance,
            value,
            lazy=not field.always_coerce,
            is_lazy_valid=True,
        )  # Bypass coercion and validation, except for fields with `always_coerce=True`
        fields_set.add(name)
    return instance


def _from_attributes(
    dataclass_: typing.Type[DataclassTco], obj: typing.Any
) -> DataclassTco:
    """
    Convert an object to a dataclass instance by initializing an instance using
    the object's attributes

    :param dataclass_: The target dataclass type to convert to.
    :param obj: The object to convert.
    :return: The dataclass instance.
    """
    values = {}
    by_name = by_name_ctx_var.get()
    name_map = dataclass_._name_map
    for field in dataclass_.__init_fields__:
        name: str = field.name  # type: ignore[assignment]
        if by_name:
            if (value := getattr(obj, name, _missing)) is not _missing:
                values[name] = value
        else:
            effective_name = name_map[name]
            if (value := getattr(obj, effective_name, _missing)) is not _missing:
                values[name] = value
            elif (value := getattr(obj, name, _missing)) is not _missing:
                values[name] = value

    return dataclass_(**values)


@typing.overload
def deserialize(
    dataclass_: typing.Type[DataclassTco],
    obj: RawData,
) -> DataclassTco: ...


@typing.overload
def deserialize(
    dataclass_: typing.Type[DataclassTco],
    obj: typing.Any,
    *,
    from_attributes: bool = False,
) -> DataclassTco: ...


def deserialize(
    dataclass_: typing.Type[DataclassTco],
    obj: typing.Union[RawData, typing.Any],
    *,
    from_attributes: bool = False,
) -> DataclassTco:
    """
    Deserialize an object to a dataclass instance.

    :param obj: The object to deserialize.
    :param dataclass_: The dataclass type to convert to.
    :param from_attributes: If True, load fields using the object's attributes.
    :raises DeserializationError: If there are errors during deserialization.
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

    if from_attributes:
        return _from_attributes(dataclass_, obj)
    return dataclass_(obj)


def copy(
    instance: DataclassTco,
    *,
    update: typing.Optional[DataDict] = None,
    deep: bool = False,
    _memo: typing.Optional[typing.Dict[int, typing.Any]] = None,
) -> DataclassTco:
    """
    Create and return a copy of the dataclass instance.

    This implementation uses the state management methods of the dataclass,
    `__getstate__` and `__setstate__`.

    It is important to note that copying involves loading or deserializing
    the state of the original instance unto a new instance(copy), applying
    any updates as needed.

    :param instance: The dataclass instance to copy.
    :param update: Optional dictionary to update fields in the copied instance.
    :param deep: If True, create and return a deep copy of the instance.
    :return: A new dataclass instance that is a copy of the original.

    **Tip: If `update` data provided is confirmed to be valid. Efficiently update with:**

    ```python

    with attrib.deserialization_context(is_valid=True):
        new_instance = attrib.copy(instance, update=update)
    ```
    """
    if (getstate := getattr(instance, "__getstate__", None)) is None:
        getstate = partial(_getstate, instance)

    field_values, attributes = getstate()
    if deep:
        field_values = pycopy.deepcopy(field_values, memo=_memo)
        attributes = pycopy.deepcopy(attributes, memo=_memo)  # TODO: Might remove later

    if getnewargs := getattr(instance, "__getnewargs_ex__", None):
        args, kwargs = getnewargs()
    else:
        args, kwargs = (), {}
    new_instance = type(instance).__new__(type(instance), *args, **kwargs)
    if (setstate := getattr(new_instance, "__setstate__", None)) is None:
        setstate = partial(_setstate, new_instance)

    with deserialization_context(
        fail_fast=True,
        ignore_extras=True,
        by_name=True,
    ):
        new_instance = setstate((field_values, attributes))
        if update:
            fields = instance.__dataclass_fields__
            normalized_update: DataDict = {}
            update_fields = []
            for key, value in update.items():
                if key in instance._effective_name_map:
                    name = instance._effective_name_map[key]
                    normalized_update[name] = value
                    update_fields.append(fields[name])
                else:
                    normalized_update[key] = value
                    if field := fields.get(key, None):
                        update_fields.append(field)

            new_instance = load_raw(
                new_instance,
                fields=update_fields,
                data=normalized_update,
            )
    return typing.cast(DataclassTco, new_instance)


def get_field(
    cls: typing.Type[Dataclass], name: str
) -> typing.Optional[Field[typing.Any]]:
    """
    Get a field by its name.

    :param cls: The Dataclass type to search in.
    :param name: The name of the field to retrieve.
    :return: The field instance or None if not found.
    """
    field = cls.__dataclass_fields__.get(name, None)
    if field is None and name in cls._effective_name_map:
        actual_name = cls._effective_name_map[name]
        field = cls.__dataclass_fields__.get(actual_name, None)
    return field


def get_fields(cls: typing.Type[typing.Any]) -> typing.Dict[str, Field[typing.Any]]:
    """
    Inspect and retrieve all data fields from a class.

    :param cls: The class to inspect.
    :return: A dictionary of field names and their corresponding Field instances.
    """
    if is_dataclass(cls):
        return dict(cls.__dataclass_fields__)

    fields = {}
    for key, value in cls.__dict__.items():
        if isinstance(value, Field):
            fields[key] = value
    return fields
