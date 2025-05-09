"""Data description classes"""

import typing
from types import MappingProxyType

from attrib.descriptors import Field, Value
from attrib.exceptions import FrozenInstanceError


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
    if key in instance._set_attributes:
        raise FrozenInstanceError(
            f"Cannot modify '{type(instance).__name__}.{key}'. "
            f"Instance is frozen and field '{key}' has already been set."
        ) from None

    return object.__setattr__(instance, key, value)


def _frozen_delattr(instance: "Dataclass", key: str) -> None:
    """Delete an attribute from a frozen dataclass instance."""
    if key in instance.base_to_effective_name_map:
        raise FrozenInstanceError(
            f"Cannot delete '{type(instance).__name__}.{key}'. Instance is frozen"
        ) from None

    return object.__delattr__(instance, key)


def _get_slotted_instance_state(
    slotted_instance: "Dataclass",
) -> typing.Tuple[typing.Dict[str, typing.Any], typing.Dict[str, typing.Any]]:
    """Get the state of the slotted dataclass instance."""
    fields = slotted_instance.__fields__
    field_values = {}
    instance_type = type(slotted_instance)
    for key, field in fields.items():
        value = field.__get__(slotted_instance, owner=instance_type)
        field_values[key] = value

    attributes = {}
    pickleable_attributes = set(
        getattr(slotted_instance, "__slots__", [])
        + getattr(slotted_instance, "__state_attributes__", [])
    )
    for attr_name in pickleable_attributes:
        if attr_name in fields:
            continue
        if not hasattr(slotted_instance, attr_name):
            continue
        value = getattr(slotted_instance, attr_name)
        attributes[attr_name] = value
    return field_values, attributes


def _set_slotted_instance_state(
    slotted_instance: "Dataclass",
    state: typing.Tuple[typing.Dict[str, typing.Any], typing.Dict[str, typing.Any]],
) -> "Dataclass":
    """Set the state of the slotted dataclass."""
    field_values, attributes = state
    load(slotted_instance, field_values)
    for key, value in attributes.items():
        if key in slotted_instance.__fields__:
            continue
        setattr(slotted_instance, key, value)
    return slotted_instance


def _getnewargs(instance: "Dataclass") -> typing.Tuple:
    """Get the __new__ arguments for the dataclass instance."""
    return (), instance.__getstate__()  # type: ignore[return-value]


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

    # Add __getstate__ and __setstate__ methods for pickling support
    if "__getstate__" not in namespace:
        namespace["__getstate__"] = _get_slotted_instance_state
    if "__setstate__" not in namespace:
        namespace["__setstate__"] = _set_slotted_instance_state
    if "__getnewargs__" not in namespace:
        namespace["__getnewargs__"] = _getnewargs

    namespace["__slots__"] = tuple(slots)
    if parent_slotted_attributes:
        slotted_attributes_names |= parent_slotted_attributes

    namespace["__slotted_names__"] = slotted_attributes_names
    namespace.pop("__dict__", None)
    namespace.pop("__weakref__", None)
    return namespace


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
        raise TypeError(f"Unhashable field value in {instance}: {exc}")


def _eq(
    instance: "Dataclass",
    other: typing.Any
) -> bool:
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


u = str


class DataclassMeta(type):
    """Metaclass for Dataclass types"""

    def __new__(
        cls,
        name: str,
        bases: typing.Tuple[typing.Type],
        attrs: typing.Dict[str, typing.Any],
        frozen: bool = False,
        slots: typing.Union[typing.Tuple[str], bool] = False,
        repr: bool = False,
        str: bool = False,
        sort: typing.Union[
            bool, typing.Callable[[typing.Tuple[str, Field]], typing.Any]
        ] = False,
        hash: bool = False,
        eq: bool = False,
        getitem: bool = False,
        setitem: bool = False,
    ):
        """
        Create a new Dataclass type.

        :param name: Name of the new class.
        :param bases: Base classes for the new class.
        :param attrs: Attributes and namespace for the new class.
        :param slots: If True, use __slots__ for instance attribute storage.
            If a tuple, use as additional slots.
            If False, use __dict__ for instance attribute storage.
        :param dict_repr: Whether to use dict representation for __repr__ or to use the default.
        :param sort: If True, sort fields by name. If a callable, use as the sort key.
            If False, do not sort fields.
        :param frozen: If True, the dataclass is immutable after creation.
        :param hash: If True, add __hash__ method to the class.
        :param eq: If True, add __eq__ method to the class.
        :param getitem: If True, add __getitem__ method to the class.
        :param setitem: If True, add __setitem__ method to the class.
        :return: New Dataclass type
        """
        own_fields = {}
        fields = {}
        base_to_effective_name_map = {}
        effective_to_base_name_map = {}
        parent_slotted_attributes = {}
        for key, value in attrs.items():
            if isinstance(value, Field):
                value.post_init_validate()
                own_fields[key] = value
                fields[key] = value
                effective_name = value.alias or key
                base_to_effective_name_map[key] = effective_name
                effective_to_base_name_map[effective_name] = key

        # Inspect the base classes for fields and borrow them
        inspected = set()
        for base_ in bases:
            for cls_ in base_.mro()[:-1]:
                if cls_ in inspected:
                    continue

                inspected.add(cls_)
                if not hasattr(cls_, "__fields__"):
                    continue

                if slots and hasattr(cls_, "__slotted_names__"):
                    parent_slotted_attributes.update(cls_.__slotted_names__)

                cls_ = typing.cast(typing.Type["Dataclass"], cls_)
                # Borrow fields from the base class
                fields.update(cls_.__fields__)
                base_to_effective_name_map.update(cls_.base_to_effective_name_map)
                effective_to_base_name_map.update(cls_.effective_to_base_name_map)

        if slots:
            # Replace the original namespace with a slotted one.
            slotted_namespace = _build_slotted_namespace(
                namespace=attrs.copy(),
                own_fields=own_fields.keys(),
                additional_slots=slots
                if isinstance(slots, (u, tuple, list, set))
                else None,
                parent_slotted_attributes=parent_slotted_attributes,
            )
            attrs = slotted_namespace

        if frozen:
            attrs["__setattr__"] = _frozen_setattr
            attrs["__delattr__"] = _frozen_delattr
        if repr:
            attrs["__repr__"] = _repr
        if str:
            attrs["__str__"] = _str
        if getitem:
            attrs["__getitem__"] = _getitem
        if setitem:
            attrs["__setitem__"] = _setitem
        if hash:
            attrs["__hash__"] = _hash
        if eq:
            attrs["__eq__"] = _eq

        sort = attrs.get("sort", sort)
        if sort:
            sort_key = sort if callable(sort) else _sort_by_name
            sort_key = typing.cast(
                typing.Callable[[typing.Tuple[u, Field]], u], sort_key
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


class Dataclass(metaclass=DataclassMeta, slots=True):
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
    #         "population": 50_000_000,
    #         "continent": {
    #             "name": "Africa",
    #             "population": 1_300_000_000,
    #         }
    #     },
    #     "population": 4_000_000,
    #     "area": 696.1,
    #     "postal_code": "00100"
    # }
    ```
    """

    __slots__ = ("__weakref__", "_set_attributes")
    __state_attributes__ = ()
    """
    Attributes to be included in the state of the dataclass when __getstate__ is called,
    usually during pickling
    """
    __fields__: typing.Mapping[str, Field[typing.Any]] = {}
    base_to_effective_name_map: typing.Mapping[str, str] = {}
    effective_to_base_name_map: typing.Mapping[str, str] = {}

    @typing.overload
    def __init__(self, data: None = None) -> None:
        """Initialize the dataclass with no data."""
        ...

    @typing.overload
    def __init__(
        self,
        data: typing.Mapping[str, typing.Any],
    ) -> None:
        """Initialize the dataclass with raw data."""
        ...

    @typing.overload
    def __init__(self, **kwargs: typing.Any) -> None:
        """Initialize the dataclass with keyword arguments."""
        ...

    def __init__(
        self,
        data: typing.Optional[typing.Mapping[str, typing.Any]] = None,
        **kwargs,
    ) -> None:
        """
        Initialize the dataclass with raw data or keyword arguments.

        :param data: Raw data to initialize the dataclass with.
        :param kwargs: Additional keyword arguments to initialize the dataclass with.
        """
        self._set_attributes = set()
        combined = {**(data or {}), **kwargs}
        if combined:
            load(self, combined)

    def __init_subclass__(cls) -> None:
        """Ensure that subclasses define fields."""
        if len(cls.__fields__) == 0:
            raise TypeError("Subclasses must define fields")
        return


_Dataclass_co = typing.TypeVar("_Dataclass_co", bound=Dataclass, covariant=True)


def load(
    instance: _Dataclass_co, data: typing.Mapping[str, typing.Any]
) -> _Dataclass_co:
    """
    Load raw data unto the dataclass instance.

    :param data: Mapping of raw data to initialize the dataclass instance with.
    :return: This same instance with the raw data loaded.
    """
    for name, field in instance.__fields__.items():
        key = instance.base_to_effective_name_map[name]
        if key not in data:
            value = field.get_default()
        else:
            value = data[key]

        field.__set__(instance, value)
    return instance


def from_dict(
    dataclass_: typing.Type[_Dataclass_co],
    data: typing.Mapping[str, typing.Any],
) -> _Dataclass_co:
    """
    Convert a dictionary to a dataclass instance.

    :param data: The dictionary to convert.
    :param dataclass_: The dataclass type to convert to.
    :return: The dataclass instance.
    """
    return load(dataclass_(), data)


def from_attributes(
    dataclass_: typing.Type[_Dataclass_co],
    obj: typing.Any,
) -> _Dataclass_co:
    """
    Convert an object to a dataclass instance by loading fields using
    the objects attributes

    :param obj: The object to convert.
    :param dataclass_: The dataclass type to convert to.
    :return: The dataclass instance.
    """
    instance = dataclass_()
    for name, field in dataclass_.__fields__.items():
        key = dataclass_.base_to_effective_name_map[name]

        if not hasattr(obj, key):
            value = field.get_default()
        else:
            value = getattr(obj, key)
        field.__set__(instance, value)
    return instance


def deserialize(
    dataclass_: typing.Type[_Dataclass_co],
    obj: typing.Any,
    *,
    attributes: bool = False,
) -> _Dataclass_co:
    """
    Deserialize an object to a dataclass instance.

    :param obj: The object to deserialize.
    :param dataclass_: The dataclass type to convert to.
    :param attributes: If True, load fields using the object's attributes.
    :return: The dataclass instance.
    """
    if attributes:
        return from_attributes(dataclass_, obj)
    return from_dict(dataclass_, obj)


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
