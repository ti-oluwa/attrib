import functools
import sys
import typing
from collections.abc import Iterable, Mapping

from attrib._utils import (
    is_generic_type,
    is_namedtuple,
    json_serializer,
    no_op_serializer,
)
from attrib.dataclasses import Dataclass, DataclassTco, deserialize
from attrib.exceptions import DeserializationError, InvalidTypeError, ValidationError
from attrib.serializers import _asdict, serialize
from attrib.types import (
    Deserializer,
    NoneType,
    Serializer,
    SerializerMap,
    T,
    TypeAdapter,
    Validator,
)
from attrib.validators import instance_of

try:
    from typing_extensions import is_typeddict
except ImportError:  # pragma: no cover
    assert sys.version_info >= (3, 10)
    from typing import is_typeddict


_COMMON_DESERIALIZERS: typing.Dict[type, Deserializer[typing.Any]] = {
    int: lambda v, *_, **__: v if isinstance(v, int) else int(v),
    str: lambda v, *_, **__: v if isinstance(v, str) else str(v),
    float: lambda v, *_, **__: v if isinstance(v, float) else float(v),
    bool: lambda v, *_, **__: v if isinstance(v, bool) else bool(v),
    bytes: lambda v, *_, **__: v
    if isinstance(v, bytes)
    else (v.encode() if isinstance(v, str) else bytes(v)),
}

_COMMON_VALIDATORS: typing.Dict[type, Validator[typing.Any]] = {
    int: instance_of(int),
    str: instance_of(str),
    float: instance_of(float),
    bool: instance_of(bool),
    bytes: instance_of(bytes),
    list: instance_of(list),
    dict: instance_of(dict),
    tuple: instance_of(tuple),
    set: instance_of(set),
}


def _dataclass_deserializer(
    target: typing.Type[DataclassTco],
    /,
    value: typing.Any,
    *_: typing.Any,
    **kwargs: typing.Any,
) -> DataclassTco:
    """
    A deserializer function that attempts to coerce the value to the target type.

    :param value: The value to deserialize
    :param args: Additional arguments for deserialization
    :param kwargs: Additional keyword arguments for deserialization
    """
    if isinstance(value, target):
        return value
    return deserialize(target, value, **kwargs)


#########################
# SPECIAL-TYPE BUILDERS #
#########################

TypeDictType = typing.TypeVar("TypeDictType", bound=typing.Mapping[str, typing.Any])
NamedTupleType = typing.TypeVar("NamedTupleType", bound=typing.NamedTuple)


@functools.lru_cache(maxsize=128)
def build_typeddict_deserializer(
    target: typing.Type[TypeDictType],
    /,
    depth: typing.Optional[int] = None,
) -> Deserializer[TypeDictType]:
    """
    Build a deserializer for a TypedDict type.

    :param target: The target type to adapt
    :return: A function that attempts to coerce the value to the target type
    """
    from attrib.adapters._generics import build_generic_type_deserializer

    if not is_typeddict(target):
        raise TypeError(f"Cannot build deserializer for non-TypedDict type {target!r}")

    annotations = typing.get_type_hints(target)
    deserializers_map: typing.Dict[str, Deserializer[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            deserializers_map[key] = build_generic_type_deserializer(value, depth=depth)
        else:
            deserializers_map[key] = build_concrete_type_deserializer(
                value, depth=depth
            )

    typeddict_keys = set(deserializers_map.keys())

    def deserializer(
        value: typing.Union[TypeDictType, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> TypeDictType:
        """
        A deserializer function that attempts to coerce the value to the target type.

        :param value: The value to deserialize
        :param args: Additional arguments for deserialization
        :param kwargs: Additional keyword arguments for deserialization
        """
        if not isinstance(value, Mapping):
            raise InvalidTypeError(
                "Cannot deserialize value. Expected a Mapping.",
                input_type=type(value),
                expected_type=target,
            )

        mapping_keys = set(value.keys())
        # If deserialization is not strict and all of the typedicts keys are not present in the
        # mapping, just return an empty mapping
        if (
            not kwargs.get("strict", False)
            and (mapping_keys - typeddict_keys) == mapping_keys
        ):
            return target()

        new_mapping = {}
        for key, item in value.items():
            if key not in typeddict_keys:
                continue
            try:
                new_mapping[key] = deserializers_map[key](item, *args, **kwargs)
            except (TypeError, ValueError, DeserializationError) as exc:
                raise DeserializationError.from_exc(
                    exc,
                    input_type=type(value),
                    expected_type=target,
                    location=[key],
                ) from exc

        return target(**new_mapping)

    deserializer.__name__ = f"{target.__name__}_deserializer"
    return deserializer


@functools.lru_cache(maxsize=128)
def build_typeddict_validator(
    target: typing.Type[TypeDictType],
    /,
    depth: typing.Optional[int] = None,
) -> Validator[TypeDictType]:
    """
    Build a validator for a TypedDict type.

    :param target: The target TypedDict type to validate against.
    :return: A function that attempts to coerce the value to the target type
    """
    from attrib.adapters._generics import build_generic_type_validator

    annotations = typing.get_type_hints(target)
    required_keys = getattr(target, "__required_keys__", set())
    validators_map: typing.Dict[str, Validator[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            validators_map[key] = build_generic_type_validator(value, depth=depth)
        else:
            validators_map[key] = build_concrete_type_validator(value, depth=depth)

    typeddict_keys = set(validators_map.keys())

    def validator(
        value: typing.Union[TypeDictType, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        A validator function that attempts to coerce the value to the target type.

        :param value: The value to validate
        :param args: Additional arguments for validation
        :param kwargs: Additional keyword arguments for validation
        """
        if not isinstance(value, Mapping):
            raise InvalidTypeError(
                "Cannot validate value. Expected a Mapping.",
                input_type=type(value),
                expected_type=target,
            )

        mapping_keys = set(value.keys())
        # If all of the typedicts keys are not present in the
        # mapping, just return
        if (mapping_keys - typeddict_keys) == mapping_keys:
            return

        if required_keys and (mapping_keys & required_keys) != required_keys:
            raise ValidationError(
                f"Value is missing required keys {required_keys - mapping_keys} in {value!r}"
            )

        for key, item in value.items():
            if key not in typeddict_keys:
                continue
            try:
                validators_map[key](item, *args, **kwargs)
            except (ValueError, ValidationError) as exc:
                raise ValidationError.from_exc(
                    exc,
                    input_type=type(value),
                    expected_type=target,
                    location=[key],
                ) from exc

        return None

    validator.__name__ = f"{target.__name__}_validator"
    return validator


@functools.lru_cache(maxsize=128)
def build_namedtuple_deserializer(
    target: typing.Type[NamedTupleType],
    /,
    depth: typing.Optional[int] = None,
) -> Deserializer[NamedTupleType]:
    """
    Build a deserializer for a NamedTuple type.

    :param target: The target NamedTuple type to adapt
    :return: A function that attempts to coerce the value to the target type
    """
    from attrib.adapters._generics import build_generic_type_deserializer

    annotations = typing.get_type_hints(target)
    deserializers_map: typing.Dict[str, Deserializer[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            deserializers_map[key] = build_generic_type_deserializer(value, depth=depth)
        else:
            deserializers_map[key] = build_concrete_type_deserializer(
                value, depth=depth
            )

    def deserializer(
        value: typing.Union[NamedTupleType, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> NamedTupleType:
        """
        A deserializer function that attempts to coerce the value to the target type.

        :param value: The value to deserialize
        :param args: Additional arguments for deserialization
        :param kwargs: Additional keyword arguments for deserialization
        """
        if not isinstance(value, (Mapping, Iterable)):
            raise InvalidTypeError(
                "Expected a Mapping or Iterable.",
                input_type=type(value),
                expected_type=target,
            )

        if isinstance(value, Mapping):
            items = value.items()
        else:
            items = zip(target._fields, value)

        new_mapping = {}
        for key, item in items:
            try:
                new_mapping[key] = deserializers_map[key](item, *args, **kwargs)
            except (TypeError, ValueError, DeserializationError) as exc:
                raise DeserializationError.from_exc(
                    exc,
                    input_type=type(value),
                    expected_type=target,
                    location=[key],
                ) from exc

        return target(**new_mapping)  # type: ignore[call-arg]

    deserializer.__name__ = f"{target.__name__}_deserializer"
    return deserializer


@functools.lru_cache(maxsize=128)
def build_namedtuple_validator(
    target: typing.Type[NamedTupleType],
    /,
    depth: typing.Optional[int] = None,
) -> Validator[NamedTupleType]:
    """
    Build a validator for a NamedTuple type.

    :param target: The target NamedTuple type to validate against.
    :return: A function that attempts to validate the value against the target type
    """
    from attrib.adapters._generics import build_generic_type_validator

    annotations = typing.get_type_hints(target)
    validators_map: typing.Dict[str, Validator[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            validators_map[key] = build_generic_type_validator(value, depth=depth)
        else:
            validators_map[key] = build_concrete_type_validator(value, depth=depth)

    def validator(
        value: typing.Union[NamedTupleType, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        A validator function that attempts to validate the value against the target type.

        :param value: The value to validate
        :param args: Additional arguments for validation
        :param kwargs: Additional keyword arguments for validation
        """
        if not isinstance(value, (Mapping, Iterable)):
            raise InvalidTypeError(
                "Cannot validate value. Expected a Mapping or Iterable.",
                input_type=type(value),
                expected_type=target,
            )

        if isinstance(value, Mapping):
            items = value.items()
        else:
            items = zip(target._fields, value)

        for key, item in items:
            if key not in validators_map:
                continue
            try:
                validators_map[key](item, *args, **kwargs)
            except (ValidationError, ValueError) as exc:
                raise ValidationError.from_exc(
                    exc,
                    input_type=type(value),
                    expected_type=target,
                    location=[key],
                ) from exc
        return None

    validator.__name__ = f"{target.__name__}_validator"
    return validator


@functools.lru_cache(maxsize=128)
def build_namedtuple_serializer(
    target: typing.Type[NamedTupleType],
    /,
    fmt: typing.Literal["python", "json"] = "python",
    depth: typing.Optional[int] = None,
) -> Serializer[NamedTupleType]:
    """
    Build a serializer for a NamedTuple type.

    :param target: The target NamedTuple type to adapt
    :param fmt: The format to use for serialization, e.g., "json" or "python"
    :return: A function that serializes the value to the target format
    """
    from attrib.adapters._generics import build_generic_type_serializer

    if not is_namedtuple(target):
        raise TypeError(f"Cannot build serializer for non-NamedTuple type {target!r}")

    annotations = typing.get_type_hints(target)
    serializer_map: typing.Dict[str, Serializer[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            serializer_map[key] = build_generic_type_serializer(
                value, fmt=fmt, depth=depth
            )
        else:
            serializer_map[key] = build_concrete_type_serializer(
                value, fmt=fmt, depth=depth
            )

    def serializer(
        value: typing.Union[NamedTupleType, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Any:
        """
        A serializer function that serializes the value to the target format.

        :param value: The value to serialize
        :param args: Additional arguments for serialization
        :param kwargs: Additional keyword arguments for serialization
        """
        if not isinstance(value, (Mapping, Iterable)):
            raise InvalidTypeError(
                "Cannot serialize value. Expected a Mapping or Iterable.",
                input_type=type(value),
                expected_type=target,
            )

        if isinstance(value, Mapping):
            items = value.items()
        else:
            items = zip(target._fields, value)

        serialized = []
        for key, item in items:
            if key not in serializer_map:
                continue
            serialized.append(serializer_map[key](item, *args, **kwargs))
        return tuple(serialized)

    serializer.__name__ = f"{target.__name__}_serializer"
    return serializer


#############################
# NON-GENERIC TYPE BUILDERS #
#############################


@functools.lru_cache(maxsize=128)
def build_concrete_type_deserializer(
    type_: typing.Type[T],
    depth: typing.Optional[int] = None,
) -> Deserializer[typing.Any]:
    """
    Build a deserializer for a non-generic type.

    :param type_: The target non-generic type to build deserializer for.
    :param depth: The depth for nested deserialization (if applicable)
    :param strict: Whether to enforce strict type checking and not attempt type coercion.
    :return: A function that attempts to coerce the value to the target type
    """
    # Fast path for common types
    if type_ in _COMMON_DESERIALIZERS:
        base_deserializer = _COMMON_DESERIALIZERS[type_]

        def fast_deserializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> T:
            if isinstance(value, type_):
                return value
            if kwargs.pop("strict", False):
                raise DeserializationError(
                    "Cannot deserialize value without coercion. Set strict=False to allow coercion.",
                    input_type=type(value),
                    expected_type=type_,
                )
            try:
                return base_deserializer(value)
            except (ValueError, TypeError) as exc:
                raise DeserializationError.from_exc(
                    exc,
                    input_type=type(value),
                    expected_type=type_,
                ) from exc

        fast_deserializer.__name__ = f"{type_.__name__}_deserializer"
        return fast_deserializer

    if is_typeddict(type_):
        return build_typeddict_deserializer(type_, depth=depth)

    if is_namedtuple(type_):
        return build_namedtuple_deserializer(type_, depth=depth)

    if issubclass(type_, Dataclass):

        def to_dataclass(
            value: typing.Any, *args: typing.Any, **kwargs: typing.Any
        ) -> T:
            return _dataclass_deserializer(
                type_,  # type: ignore[return-value]
                value,
                *args,
                **kwargs,
            )

        to_type = to_dataclass
    elif issubclass(type_, NoneType):

        def to_none_type(
            value: typing.Any, *args: typing.Any, **kwargs: typing.Any
        ) -> T:
            if value is not None:
                raise DeserializationError(
                    "Cannot deserialize value. Expected value to be None",
                    input_type=type(value),
                    expected_type="null",
                )
            return value

        to_type = to_none_type
    else:

        def to_any_type(
            value: typing.Any, *args: typing.Any, **kwargs: typing.Any
        ) -> T:
            if isinstance(value, type_):
                return value
            return type_(value)  # type: ignore[call-arg]

        to_type = to_any_type

    allow_any_type = type_ is typing.Any
    type_ = typing.cast(typing.Type[T], type_)  # type: ignore

    def deserializer(
        value: typing.Any,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> T:
        """
        A deserializer function that attempts to coerce the value to the target type.

        :param value: The value to deserialize
        :param args: Additional arguments for deserialization
        :param kwargs: Additional keyword arguments for deserialization
        """
        if allow_any_type or isinstance(value, type_):
            return value

        if kwargs.pop("strict", False):
            raise DeserializationError(
                "Cannot deserialize value without coercion. Set strict=False to allow coercion.",
                input_type=type(value),
                expected_type=type_,
            )

        try:
            return to_type(value, *args, **kwargs)
        except (ValueError, TypeError) as exc:
            raise DeserializationError.from_exc(
                exc,
                input_type=type(value),
                expected_type=type_,
            ) from exc

    deserializer.__name__ = f"{type_.__name__}_deserializer"
    return deserializer


def build_concrete_type_validator(
    target: typing.Type[T],
    /,
    depth: typing.Optional[int] = None,
) -> Validator[typing.Any]:
    """
    Build a validator for a non-generic type.

    :param target: The target non-generic type.
    :param depth: The depth for nested build operations (if applicable)
    :return: A function that attempts to validate the value against the target type
    """
    # Fast path for common types
    if target in _COMMON_VALIDATORS:
        return _COMMON_VALIDATORS[target]

    if is_typeddict(target):
        return build_typeddict_validator(target, depth=depth)
    if is_namedtuple(target):
        return build_namedtuple_validator(target, depth=depth)
    return instance_of(target)


def build_concrete_type_serializer(
    target: typing.Type[T],
    *,
    fmt: typing.Literal["python", "json"] = "python",
    depth: typing.Optional[int] = None,
) -> Serializer[typing.Any]:
    """
    Build a serializer for a non-generic type.

    :param target: The target non-generic type to build serializer for
    :param fmt: The format to use for serialization, e.g., "json" or "python"
    :param depth: The depth for nested serialization (if applicable)
    :return: A function that serializes the value to the target format
    """
    if is_namedtuple(target):
        return build_namedtuple_serializer(target, fmt=fmt, depth=depth)

    if issubclass(target, Dataclass):

        def dataclass_serializer(
            value: typing.Any,
            _: TypeAdapter,
            *args: typing.Any,
            **kwargs: typing.Any,
        ):
            kwargs["fmt"] = fmt
            return _asdict(value, *args, **kwargs)

        dataclass_serializer.__name__ = f"{target.__name__}_serializer"
        return dataclass_serializer

    if fmt == "json":
        return json_serializer
    return no_op_serializer


###########################
# SERIALIZER MAP BUILDERS #
###########################


def build_concrete_type_serializers_map(
    target: typing.Type[T],
    /,
    serializers: typing.Optional[SerializerMap] = None,
    depth: typing.Optional[int] = None,
) -> typing.Dict[str, Serializer[typing.Any]]:
    """
    Build a serializer registry for non-generic types.

    :param target: The target non-generic type.
    :param serializers: A mapping of serialization formats to their respective serializer functions
    :param depth: Optional depth for serialization
    :return: A SerializerMap with the provided serializers
    """
    serializers_map = {**(serializers or {})}
    if "json" not in serializers_map:
        json_serializer = build_concrete_type_serializer(
            target, fmt="json", depth=depth
        )
        serializers_map["json"] = json_serializer
    if "python" not in serializers_map:
        python_serializer = build_concrete_type_serializer(
            target, fmt="python", depth=depth
        )
        serializers_map["python"] = python_serializer
    return serializers_map


def build_dataclass_serializers_map(
    serializers: typing.Optional[SerializerMap] = None,
) -> typing.Dict[str, Serializer[typing.Any]]:
    """
    Build a serializer registry for dataclass types.

    :param serializers: A mapping of serialization formats to their respective serializer functions
    :return: A SerializerMap with the provided serializers
    """
    serializers_map = {**(serializers or {})}
    if "json" not in serializers_map:
        serializers_map["json"] = lambda value, *_, **kwargs: serialize(
            value,
            fmt="json",
            **kwargs,
        )
    if "python" not in serializers_map:
        serializers_map["python"] = lambda value, *_, **kwargs: serialize(
            value,
            fmt="python",
            **kwargs,
        )
    return serializers_map
