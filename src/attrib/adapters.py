import inspect
import typing
import functools
from collections.abc import (
    Iterable,
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
    Set,
)
from types import NoneType
from collections import defaultdict

from attrib._typing import JSONValue, Validator, T, Serializer, Deserializer
from attrib._utils import (
    is_generic_type,
    is_named_tuple,
    is_typed_dict,
    make_jsonable,
    SerializerRegistry,
    _unsupported_serializer_factory,
    coalesce_funcs,
    resolve_type,
)
from attrib.exceptions import (
    DeserializationError,
    InvalidTypeError,
    SerializationError,
    ValidationError,
)
from attrib.validators import (
    Or,
    instance_of,
    iterable,
    mapping,
    member_of,
    eq,
    optional,
)
from attrib.serializers import serialize
from attrib.dataclass import Dataclass, deserialize, DataclassTco


__all__ = ["TypeAdapter"]


@typing.final
class TypeAdapter(typing.Generic[T]):
    """
    Concrete `TypeAdapter` implementation.

    A type adapter is a pseudo-type. It defines type-like behavior using 3 main methods:
    - validate: Validates the value
    - serialize: Serializes the value to a specific format
    - deserialize: Coerces the value to a specific type

    Example usage:
    ```python
    from attrib import TypeAdapter
    from attrib.validators import ge

    adapter = TypeAdapter(
        int,
        name="StrictPositiveInt",
        validators=[ge(0)],
        strict=True,
    )

    value = adapter.adapt("123") # deserializes to int and validates
    print(type(value), value, sep=", ")  # <class 'int'>, 123

    value = adapter.deserialize("123")
    print(type(value), value, sep=", ")  # <class 'int'>, 123

    value = adapter.validate("123")
    # raises attrib.exceptions.ValidationError
    value = adapter.validate(123)
    print(value)  # 123

    value = adapter.serialize(123, "json")
    print(value)  # 123
    ```
    """

    __slots__ = (
        "adapted",
        "name",
        "validator",
        "serializer",
        "deserializer",
        "strict",
        "_is_built",
    )

    def __init__(
        self,
        adapted: typing.Union[typing.Type[T], T],
        /,
        *,
        name: typing.Optional[str] = None,
        deserializer: typing.Optional[Deserializer[typing.Union[T, typing.Any]]] = None,
        validator: typing.Optional[Validator[typing.Union[T, typing.Any]]] = None,
        serializers: typing.Optional[
            typing.Mapping[str, Serializer[typing.Any]]
        ] = None,
        defer_build: bool = False,
        strict: bool = False,
    ) -> None:
        """
        Initialize the adapter.

        :param adapted: The target type to adapt
        :param name: The name of the adapted type
        :param validator: A function to validate values for the adapted type
        :param serializers: A mapping of serialization formats to their respective serializer functions
        :param deserializer: A function to coerce the value to a specific type
        :param defer_build: Whether to defer the building of the adapter probably for performance reasons,
            or for later resolving forward references.
        :param strict: Whether to enforce strict type checking and not attempt type coercion.
        """
        self.adapted = adapted
        self.name = name
        self.validator = validator
        self.deserializer = deserializer
        self.serializer = SerializerRegistry(
            defaultdict(
                _unsupported_serializer_factory,
                (serializers or {}),
            )
        )
        self.strict = strict
        self._is_built = False
        if not defer_build:
            self.build()

    def build(
        self,
        *,
        globalns: typing.Optional[typing.Dict[str, typing.Any]] = None,
        localns: typing.Optional[typing.Dict[str, typing.Any]] = None,
        depth: typing.Optional[int] = None,
    ) -> None:
        """
        Build the adapter with the provided parameters.

        ***This method is idempotent. Building the adapter multiple times***
        ***will not change its state after the first build.***

        :param depth: Defines how many type-levels deep the necessary mechanisms should be built. 
            This is especially necessary for nested types or self-referencing types that may cause 
            infinite recursion of deserializer and validator building. An example is a typed dict 
            that contains a field that is a list of instances of the same typed dict.

        :param globalns: Global namespace for resolving type references. It is advisable to always provide this
            parameter. If it is not provided, the adapter will try to resolve the type from the current frame's
            module's namespace, which may not always be available or correct and can be expensive.
        :param localns: Local namespace for resolving type references
        """
        if self._is_built:
            raise RuntimeError(
                f"Adapter {self.name or repr(self)} is already built. "
                "You cannot build it again."
            )

        self._is_built = True
        if not globalns:
            current_frame = inspect.currentframe()
            if current_frame is None:
                raise RuntimeError(
                    "Cannot build adapter without a global namespace. Provide a global namespace."
                )
            module = inspect.getmodule(current_frame.f_back)
            globalns = module.__dict__ if module else {}

        self.adapted = resolve_type(
            self.adapted,
            globalns=globalns,
            localns=localns,
        )
        if is_generic_type(self.adapted):
            if (
                len(self.serializer.map) < 2
            ):  # Should contain at least "python" and "json" serializers
                self.serializer = build_generic_type_serializer_registry(
                    self.adapted, serializers=self.serializer.map, depth=depth
                )

            if self.validator is None:
                self.validator = build_generic_type_validator(self.adapted, depth=depth)

            if self.deserializer is None:
                self.deserializer = build_generic_type_deserializer(
                    self.adapted, depth=depth
                )
            return

        if not isinstance(self.adapted, type):
            raise TypeError(f"Adapter target `{self.adapted}` must be a type")

        if len(self.serializer.map) < 2:
            serializers = self.serializer.map
            self.serializer = (
                build_dataclass_serializer_registry(serializers)
                if issubclass(self.adapted, Dataclass)
                else build_non_generic_type_serializer_registry(
                    self.adapted, serializers=serializers, depth=depth
                )
            )

        if self.validator is None:
            self.validator = instance_of(self.adapted)
        if self.deserializer is None:
            self.deserializer = build_non_generic_type_deserializer(
                self.adapted, depth=depth
            )
        return

    def validate(
        self,
        value: typing.Union[T, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Validate the value using the validator.

        :param value: The value to validate
        :param args: Additional arguments to pass to the validator
        :param kwargs: Additional keyword arguments to pass to the validator
        """
        if not self.validator:
            return
        try:
            self.validator(value, self, *args, **kwargs)
        except (ValidationError, ValueError) as exc:
            raise ValidationError.from_exception(
                exc,
                message="Invalid value",
                input_type=type(value),
                expected_type=self.adapted,
            ) from exc

    def serialize(
        self,
        value: typing.Union[T, typing.Any],
        fmt: typing.Union[typing.Literal["python", "json"], str] = "python",
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Optional[typing.Any]:
        """
        Serialize the value using the serializer.

        :param value: The value to serialize
        :param fmt: The format to use for serialization, e.g., "json" or "python"
        :param args: Additional arguments to pass to the serializer
        :param kwargs: Additional keyword arguments to pass to the serializer
        :return: The serialized value
        """
        if self.serializer is None:
            raise SerializationError(
                f"Cannot serialize value. A serializer was not initialized for '{self.name or repr(self)}'",
                input_type=type(value),
                expected_type=self.adapted,
                code="serializer_not_initialized",
            )
        return self.serializer(fmt, value, *args, **kwargs)

    def deserialize(
        self,
        value: typing.Any,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Optional[T]:
        """
        Deserialize the value using the deserializer.

        :param value: The value to deserialize
        :param args: Additional arguments to pass to the deserializer
        :param kwargs: Additional keyword arguments to pass to the deserializer
        :return: The deserialized value
        """
        if self.deserializer is None:
            raise DeserializationError(
                f"Cannot deserialize value. A deserializer was not initialized for '{self.name or repr(self)}'",
                input_type=type(value),
                expected_type=self.adapted,
                code="deserializer_not_initialized",
            )

        kwargs.setdefault("strict", self.strict)
        try:
            return self.deserializer(value, *args, **kwargs)
        except (DeserializationError, ValueError, TypeError) as exc:
            raise DeserializationError.from_exception(
                exc,
                message="Deserialization failed",
                input_type=type(value),
                expected_type=self.adapted,
                context={
                    "strict": kwargs.get("strict"),
                },
            ) from exc

    def adapt(
        self,
        value: typing.Union[T, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Optional[T]:
        """
        Adapt the value to the adapted type and validate it.
        This method is a convenience method that combines deserialization and validation.

        :param value: The value to adapt
        :param args: Additional arguments for deserialization/validation
        :param kwargs: Additional keyword arguments for deserialization/validation
        :return: The adapted and validated value
        """
        deserialized = self.deserialize(value, *args, **kwargs)
        self.validate(deserialized, *args, **kwargs)
        return deserialized

    def __repr__(self) -> str:
        """
        Return a string representation of the adapter.

        :return: A string representation of the adapter
        """
        return f"{self.__class__.__name__}(name={self.name or 'unset'}, adapted={self.adapted})"


BUILTIN_TYPES = {
    int,
    float,
    bool,
    set,
    list,
    tuple,
    dict,
    NoneType,
    str,
    bytes,
    complex,
    bytearray,
    frozenset,
    memoryview,
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

    if type(value) not in BUILTIN_TYPES:
        kwargs.setdefault("from_attributes", True)
    return deserialize(target, value, **kwargs)


def _non_generic_type_json_serializer(
    value: typing.Any, *_: typing.Any, **kwargs: typing.Any
) -> JSONValue:
    """
    Serialize a non-generic type.

    :param value: The value to serialize
    :return: The serialized value
    """
    if isinstance(value, Dataclass):
        return serialize(value, fmt="json", **kwargs)
    return make_jsonable(value)


def _non_generic_type_python_serializer(
    value: typing.Any, *_: typing.Any, **kwargs: typing.Any
) -> typing.Any:
    """
    Serialize a non-generic type to Python.

    :param value: The value to serialize
    :return: The serialized value
    """
    if isinstance(value, Dataclass):
        return serialize(value, fmt="python", **kwargs)
    return value


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
    if not is_typed_dict(target):
        raise TypeError(f"Cannot build deserializer for non-TypedDict type {target!r}")

    annotations = typing.get_type_hints(target, include_extras=True)
    deserializers_map: typing.Dict[str, Deserializer[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            deserializers_map[key] = build_generic_type_deserializer(value, depth=depth)
        else:
            deserializers_map[key] = build_non_generic_type_deserializer(
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
                raise DeserializationError.from_exception(
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
    annotations = typing.get_type_hints(target, include_extras=True)
    required_keys = getattr(target, "__required_keys__", set())
    validators_map: typing.Dict[str, Validator[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            validators_map[key] = build_generic_type_validator(value, depth=depth)
        else:
            validators_map[key] = build_non_generic_type_validator(value, depth=depth)

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
                raise ValidationError.from_exception(
                    exc,
                    input_type=type(value),
                    expected_type=target,
                    location=[key],
                ) from exc

        return None

    validator.__name__ = f"{target.__name__}_validator"
    return validator


@functools.lru_cache(maxsize=128)
def build_named_tuple_deserializer(
    target: typing.Type[NamedTupleType],
    /,
    depth: typing.Optional[int] = None,
) -> Deserializer[NamedTupleType]:
    """
    Build a deserializer for a NamedTuple type.

    :param target: The target NamedTuple type to adapt
    :return: A function that attempts to coerce the value to the target type
    """
    annotations = typing.get_type_hints(target, include_extras=True)
    deserializers_map: typing.Dict[str, Deserializer[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            deserializers_map[key] = build_generic_type_deserializer(value, depth=depth)
        else:
            deserializers_map[key] = build_non_generic_type_deserializer(
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
                raise DeserializationError.from_exception(
                    exc,
                    input_type=type(value),
                    expected_type=target,
                    location=[key],
                ) from exc

        return target(**new_mapping)  # type: ignore[call-arg]

    deserializer.__name__ = f"{target.__name__}_deserializer"
    return deserializer


@functools.lru_cache(maxsize=128)
def build_named_tuple_validator(
    target: typing.Type[NamedTupleType],
    /,
    depth: typing.Optional[int] = None,
) -> Validator[NamedTupleType]:
    """
    Build a validator for a NamedTuple type.

    :param target: The target NamedTuple type to validate against.
    :return: A function that attempts to validate the value against the target type
    """
    annotations = typing.get_type_hints(target, include_extras=True)
    validators_map: typing.Dict[str, Validator[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            validators_map[key] = build_generic_type_validator(value, depth=depth)
        else:
            validators_map[key] = build_non_generic_type_validator(value, depth=depth)

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
                raise ValidationError.from_exception(
                    exc,
                    input_type=type(value),
                    expected_type=target,
                    location=[key],
                ) from exc
        return None

    validator.__name__ = f"{target.__name__}_validator"
    return validator


@functools.lru_cache(maxsize=128)
def build_named_tuple_serializer(
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
    if not is_named_tuple(target):
        raise TypeError(f"Cannot build serializer for non-NamedTuple type {target!r}")

    annotations = typing.get_type_hints(target, include_extras=True)
    serializer_map: typing.Dict[str, Serializer[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            serializer_map[key] = build_generic_type_serializer(
                value, fmt=fmt, depth=depth
            )
        else:
            if fmt == "json":
                serializer_map[key] = _non_generic_type_json_serializer
            else:
                serializer_map[key] = _non_generic_type_python_serializer

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

        new_mapping = {}
        for key, item in items:
            if key not in serializer_map:
                continue
            new_mapping[key] = serializer_map[key](item, *args, **kwargs)

        return new_mapping

    serializer.__name__ = f"{target.__name__}_serializer"
    return serializer


#############################
# NON-GENERIC TYPE BUILDERS #
#############################


@functools.lru_cache(maxsize=128)
def build_non_generic_type_deserializer(
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
    if is_typed_dict(type_):
        return build_typeddict_deserializer(type_, depth=depth)

    if is_named_tuple(type_):
        return build_named_tuple_deserializer(type_, depth=depth)

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
    type_ = typing.cast(typing.Type[T], type_)

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
            raise DeserializationError.from_exception(
                exc,
                input_type=type(value),
                expected_type=type_,
            ) from exc

    deserializer.__name__ = f"{type_.__name__}_deserializer"
    return deserializer


def build_non_generic_type_validator(
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
    if is_typed_dict(target):
        return build_typeddict_validator(target, depth=depth)
    if is_named_tuple(target):
        return build_named_tuple_validator(target, depth=depth)
    return instance_of(target)


def build_non_generic_type_serializer(
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
    if is_named_tuple(target):
        return build_named_tuple_serializer(target, fmt=fmt, depth=depth)

    if fmt == "json":
        return _non_generic_type_json_serializer
    return _non_generic_type_python_serializer


#########################
# GENERIC TYPE BUILDERS #
#########################


@functools.lru_cache(maxsize=128)
def build_generic_type_deserializer(
    target: typing.Union[typing.Type[T], T],
    depth: typing.Optional[int] = None,
) -> Deserializer[typing.Union[T, typing.Any]]:
    """
    Build a deserializer for a generic type.

    :param target: The target generic type to build deserializer for
    :return: A deserializer function for the target type
    """
    next_depth = None
    if depth is not None:
        if depth <= 0:
            return lambda value, *args, **kwargs: value
        else:
            next_depth = depth - 1

    origin = typing.get_origin(target)
    type_args = typing.get_args(target)
    if not (origin or type_args):
        raise TypeError(f"Cannot build deserializer for non-generic type {target!r}")

    if origin is None:
        if not type_args:
            raise TypeError(
                f"Cannot build deserializer for non-generic type {target!r}"
            )
        # If the origin is None, we need to use the first argument as the origin
        # and the rest as arguments.
        return coalesce_funcs(
            *(
                build_generic_type_deserializer(arg, depth=next_depth)
                if is_generic_type(arg)
                else build_non_generic_type_deserializer(arg, depth=next_depth)
                for arg in type_args
            ),
            target=(
                TypeError,
                ValueError,
                DeserializationError,
            ),
            detailed_exc_type=DeserializationError,
        )
    elif origin and not type_args:
        return (
            build_generic_type_deserializer(origin, depth=next_depth)
            if is_generic_type(origin)
            else build_non_generic_type_deserializer(origin, depth=next_depth)
        )

    if not inspect.isclass(origin):
        if origin is typing.Literal:
            # If the origin is Literal, the deserializer should just return the value as is
            return lambda value, *args, **kwargs: value

        if origin is typing.Union and NoneType in type_args:
            # If the origin is Union and NoneType is one of the arguments,
            # We have an optional type.
            any_deserializer = coalesce_funcs(
                *(
                    build_generic_type_deserializer(arg, depth=next_depth)
                    if is_generic_type(arg)
                    else build_non_generic_type_deserializer(arg, depth=next_depth)
                    for arg in type_args
                    if arg is not NoneType
                ),
                target=(
                    TypeError,
                    ValueError,
                    DeserializationError,
                ),
                detailed_exc_type=DeserializationError,
            )

            def optional_deserializer(
                value: typing.Any, *args: typing.Any, **kwargs: typing.Any
            ) -> typing.Optional[typing.Any]:
                if value is None:
                    return None
                return any_deserializer(value, *args, **kwargs)

            return optional_deserializer

        args_deserializers = tuple(
            [
                build_generic_type_deserializer(arg, depth=next_depth)
                if is_generic_type(arg)
                else build_non_generic_type_deserializer(arg, depth=next_depth)
                for arg in type_args
            ]
        )
        return coalesce_funcs(
            *args_deserializers,
            target=(
                TypeError,
                ValueError,
                DeserializationError,
            ),
            detailed_exc_type=DeserializationError,
        )

    args_deserializers = tuple(
        [
            build_generic_type_deserializer(arg, depth=next_depth)
            if is_generic_type(arg)
            else build_non_generic_type_deserializer(arg, depth=next_depth)
            for arg in type_args
        ]
    )
    if issubclass(origin, Mapping):
        assert len(args_deserializers) == 2, (
            f"Deserializer count mismatch. Expected 2 but got {len(args_deserializers)}"
        )

        key_deserializer, value_deserializer = args_deserializers
        if inspect.isabstract(origin) or not issubclass(origin, MutableMapping):
            origin = dict

        def mapping_deserializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Mapping[typing.Any, typing.Any]:
            if not isinstance(value, (Mapping, Iterable)):
                raise InvalidTypeError(
                    "Expected a Mapping or Iterable.",
                    input_type=type(value),
                    expected_type=origin,
                )

            new_mapping = origin.__new__(origin)  # type: ignore[assignment]
            if isinstance(value, Mapping):
                items = value.items()
            else:
                items = iter(value)

            for key, item in items:
                try:
                    new_mapping[key_deserializer(key, *args, **kwargs)] = (
                        value_deserializer(item, *args, **kwargs)
                    )
                except (TypeError, ValueError, DeserializationError) as exc:
                    raise DeserializationError.from_exception(
                        exc,
                        input_type=type(value),
                        expected_type=origin,
                        location=[key],
                    ) from exc
            return new_mapping

        return mapping_deserializer

    if issubclass(origin, (Sequence, Set)):
        args_count = len(type_args)
        assert args_count == len(args_deserializers), (
            f"Deserializer count mismatch. Expected {args_count} but got {len(args_deserializers)}"
        )

        if issubclass(origin, tuple) and args_count > 1:

            def tuple_deserializer(
                value: typing.Any,
                *args: typing.Any,
                **kwargs: typing.Any,
            ) -> typing.Tuple[typing.Any, ...]:
                if not isinstance(value, Iterable) or len(value) != args_count:  # type: ignore
                    raise InvalidTypeError(
                        f"Expected an Iterable with {args_count} items.",
                        input_type=type(value),
                        expected_type=origin,
                    )

                new_tuple = []
                for index, item in enumerate(value):
                    try:
                        new_tuple.append(
                            args_deserializers[index](item, *args, **kwargs)
                        )
                    except (TypeError, ValueError, DeserializationError) as exc:
                        raise DeserializationError.from_exception(
                            exc,
                            input_type=type(value),
                            expected_type=type_args[index],
                            location=[index],
                        ) from exc

                return origin(new_tuple)

            return tuple_deserializer

        if inspect.isabstract(origin) or not issubclass(origin, MutableSequence):
            origin = list

        def iterable_deserializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Iterable[typing.Any]:
            if not isinstance(value, Iterable):
                raise InvalidTypeError(
                    "Expected an Iterable.",
                    input_type=type(value),
                    expected_type=origin,
                )

            new_iterable = []
            for item_index, item in enumerate(value):
                error = None
                for args_index, deserializer in enumerate(args_deserializers):
                    try:
                        new_iterable.append(deserializer(item, *args, **kwargs))
                        break
                    except (TypeError, ValueError, DeserializationError) as exc:
                        if error is None:
                            error = DeserializationError.from_exception(
                                exc,
                                message="Failed to deserialize item at index",
                                input_type=type(value),
                                expected_type=type_args[args_index],
                                location=[item_index],
                            )
                        else:
                            error.add(
                                exc,
                                input_type=type(value),
                                expected_type=type_args[args_index],
                                location=[item_index],
                            )
                else:
                    if error:
                        raise error

            return origin(new_iterable)  # type: ignore

        return iterable_deserializer

    raise TypeError(
        f"Cannot build deserializer for generic type {target!r} with origin {origin!r} and arguments {type_args!r}"
    )


@functools.lru_cache(maxsize=128)
def build_generic_type_validator(
    target: typing.Union[typing.Type[T], T],
    /,
    depth: typing.Optional[int] = None,
) -> Validator[typing.Union[T, typing.Any]]:
    """
    Build a validator for a generic type.

    :param target: The target generic type to build validator for
    :return: A validator function for the target type
    """
    next_depth = None
    if depth is not None:
        if depth <= 0:
            return lambda value, *args, **kwargs: None
        else:
            next_depth = depth - 1

    origin = typing.get_origin(target)
    type_args = typing.get_args(target)
    if not (origin or type_args):
        raise TypeError(f"Cannot build validator for non-generic type {target!r}")

    if origin is None:
        if not type_args:
            raise TypeError(
                f"Cannot build deserializer for non-generic type {target!r}"
            )
        args_validators = tuple(
            build_generic_type_validator(arg, depth=next_depth)
            if is_generic_type(arg)
            else build_non_generic_type_validator(arg, depth=next_depth)
            for arg in type_args
        )
        if len(args_validators) == 1:
            return args_validators[0]
        return Or(args_validators)

    elif origin and not type_args:
        return (
            build_generic_type_validator(origin, depth=next_depth)
            if is_generic_type(origin)
            else build_non_generic_type_validator(origin, depth=next_depth)
        )

    # If the origin is not a class, we can just build an Or validator
    # from the arguments validators.
    if not inspect.isclass(origin):
        if origin is typing.Literal:
            return eq(type_args[0]) if len(type_args) == 1 else member_of(type_args)

        if origin is typing.Union and NoneType in type_args:
            # If the origin is Union and NoneType is one of the arguments,
            # we have an optional type.
            args_validators = tuple(
                [
                    build_generic_type_validator(arg, depth=next_depth)
                    if is_generic_type(arg)
                    else build_non_generic_type_validator(arg, depth=next_depth)
                    for arg in type_args
                    if arg is not NoneType
                ]
            )
            if not args_validators:
                raise TypeError(
                    f"Cannot build validator for generic type {target!r} with origin {origin!r} and arguments {type_args!r}"
                )
            if len(args_validators) == 1:
                return optional(args_validators[0])
            return optional(Or(args_validators))

        args_validators = tuple(
            [
                build_generic_type_validator(arg, depth=next_depth)
                if is_generic_type(arg)
                else build_non_generic_type_validator(arg, depth=next_depth)
                for arg in type_args
            ]
        )
        return Or(args_validators)

    args_validators = tuple(
        [
            build_generic_type_validator(arg, depth=next_depth)
            if is_generic_type(arg)
            else build_non_generic_type_validator(arg, depth=next_depth)
            for arg in type_args
        ]
    )
    if issubclass(origin, Mapping):
        assert len(args_validators) == 2, (
            f"Validator count mismatch. Expected 2 but got {len(args_validators)}"
        )
        key_validator, value_validator = args_validators
        return mapping(key_validator, value_validator)

    if issubclass(origin, (Sequence, Set)):
        args_count = len(type_args)
        assert args_count == len(args_validators), (
            f"Validator count mismatch. Expected {args_count} but got {len(args_validators)}"
        )

        if issubclass(origin, tuple) and len(args_validators) > 1:

            def tuple_validator(
                value: typing.Any,
                *args: typing.Any,
                **kwargs: typing.Any,
            ) -> None:
                if not isinstance(value, Iterable) or len(value) != args_count:  # type: ignore
                    raise InvalidTypeError(
                        f"Expected an Iterable with {args_count} items.",
                        input_type=type(value),
                        expected_type=origin,
                    )

                for index, item in enumerate(value):
                    try:
                        args_validators[index](item, *args, **kwargs)
                    except (ValidationError, TypeError, ValueError) as exc:
                        raise ValidationError.from_exception(
                            exc,
                            input_type=type(value),
                            expected_type=type_args[index],
                            location=[index],
                        ) from exc

                return None

            return tuple_validator

        if len(args_validators) == 1:
            return iterable(args_validators[0])
        return iterable(Or(args_validators))

    raise TypeError(
        f"Cannot build validator for generic type {target!r} with origin {origin!r} and arguments {type_args!r}"
    )


@typing.overload
def build_generic_type_serializer(
    target: typing.Union[typing.Type[T], T, typing.Any],
    *,
    fmt: typing.Literal["python"] = ...,
    depth: typing.Optional[int] = None,
) -> Serializer[typing.Any]: ...


@typing.overload
def build_generic_type_serializer(
    target: typing.Union[typing.Type[T], T, typing.Any],
    *,
    fmt: typing.Literal["json"] = ...,
    depth: typing.Optional[int] = None,
) -> Serializer[JSONValue]: ...


@functools.lru_cache(maxsize=128)
def build_generic_type_serializer(
    target: typing.Union[typing.Type[T], T, typing.Any],
    *,
    fmt: typing.Literal["json", "python"] = "python",
    depth: typing.Optional[int] = None,
) -> Serializer[typing.Any]:
    """
    Build a python serializer for a generic type.

    :param target: The target generic type to build serializer for
    :param depth: Optional depth for serialization
    :return: A serializer function for the target type
    """
    next_depth = None
    if depth is not None:
        if depth <= 0:
            return lambda value, *args, **kwargs: value
        else:
            next_depth = depth - 1

    origin = typing.get_origin(target)
    type_args = typing.get_args(target)

    if not (origin or type_args):
        raise TypeError(
            f"Cannot build {fmt!r} serializer for non-generic type {target!r}"
        )

    if origin is None:
        if not type_args:
            raise TypeError(
                f"Cannot build {fmt!r} serializer for non-generic type {target!r}"
            )
        return coalesce_funcs(
            *(
                build_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
                if is_generic_type(arg)
                else build_non_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
                for arg in type_args
            ),
            target=(
                TypeError,
                ValueError,
                SerializationError,
            ),
            detailed_exc_type=SerializationError,
        )

    elif origin and not type_args:
        return (
            build_generic_type_serializer(origin, fmt=fmt, depth=next_depth)
            if is_generic_type(origin)
            else build_non_generic_type_serializer(origin, fmt=fmt, depth=next_depth)
        )

    args_serializers = tuple(
        [
            build_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
            if is_generic_type(arg)
            else build_non_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
            for arg in type_args
        ]
    )

    if not inspect.isclass(origin):
        if origin is typing.Literal:
            if fmt == "json":
                return _non_generic_type_json_serializer
            return _non_generic_type_python_serializer

        if origin is typing.Union and NoneType in type_args:
            # If the origin is Union and NoneType is one of the arguments,
            # we have an optional type.
            any_serializer = coalesce_funcs(
                *(
                    build_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
                    if is_generic_type(arg)
                    else build_non_generic_type_serializer(
                        arg, fmt=fmt, depth=next_depth
                    )
                    for arg in type_args
                    if arg is not NoneType
                ),
                target=(
                    TypeError,
                    ValueError,
                    SerializationError,
                ),
                detailed_exc_type=SerializationError,
            )

            def optional_serializer(
                value: typing.Any, *args: typing.Any, **kwargs: typing.Any
            ) -> typing.Optional[typing.Any]:
                if value is None:
                    return None
                return any_serializer(value, *args, **kwargs)

            return optional_serializer

        args_serializers = tuple(
            [
                build_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
                if is_generic_type(arg)
                else build_non_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
                for arg in type_args
            ]
        )
        return coalesce_funcs(
            *args_serializers,
            target=(
                TypeError,
                ValueError,
                SerializationError,
            ),
            detailed_exc_type=SerializationError,
        )

    args_serializers = tuple(
        [
            build_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
            if is_generic_type(arg)
            else build_non_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
            for arg in type_args
        ]
    )
    if issubclass(origin, Mapping):
        assert len(args_serializers) == 2, (
            f"Serializer count mismatch. Expected 2 but got {len(args_serializers)}"
        )

        key_serializer, value_serializer = args_serializers
        if inspect.isabstract(origin) or not issubclass(origin, MutableMapping):
            origin = dict

        def mapping_serializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Mapping[typing.Any, typing.Any]:
            if not isinstance(value, (Mapping, Iterable)):
                raise InvalidTypeError(
                    "Expected a Mapping or Iterable.",
                    input_type=type(value),
                    expected_type=origin,
                )

            new_mapping = origin.__new__(origin)  # type: ignore[assignment]
            if isinstance(value, Mapping):
                items = value.items()
            else:
                items = iter(value)

            for key, item in items:
                try:
                    new_mapping[key_serializer(key, *args, **kwargs)] = (
                        value_serializer(item, *args, **kwargs)
                    )
                except (SerializationError, TypeError, ValueError) as exc:
                    raise SerializationError.from_exception(
                        exc,
                        input_type=type(value),
                        expected_type=origin,
                        location=[key],
                    ) from exc
            return new_mapping

        return mapping_serializer

    if issubclass(origin, (Sequence, Set)):
        args_count = len(type_args)
        assert args_count == len(args_serializers), (
            f"Serializer count mismatch. Expected {args_count} but got {len(args_serializers)}"
        )

        if issubclass(origin, tuple) and args_count > 1:

            def tuple_serializer(
                value: typing.Any,
                *args: typing.Any,
                **kwargs: typing.Any,
            ) -> typing.Tuple[typing.Any, ...]:
                if not isinstance(value, Iterable) or len(value) != args_count:  # type: ignore
                    raise InvalidTypeError(
                        f"Expected an Iterable with {args_count} items.",
                        input_type=type(value),
                        expected_type=origin,
                    )

                new_tuple = []
                for index, item in enumerate(value):
                    try:
                        new_tuple.append(args_serializers[index](item, *args, **kwargs))
                    except (SerializationError, TypeError, ValueError) as exc:
                        raise SerializationError.from_exception(
                            exc,
                            input_type=type(value),
                            expected_type=type_args[index],
                            location=[index],
                        ) from exc
                return origin(new_tuple)

            return tuple_serializer

        if inspect.isabstract(origin) or not issubclass(origin, MutableSequence):
            origin = list

        def iterable_serializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Iterable[typing.Any]:
            if not isinstance(value, Iterable):
                raise InvalidTypeError(
                    "Expected an Iterable.",
                    input_type=type(value),
                    expected_type=origin,
                )
            new_iterable = []
            for item_index, item in enumerate(value):
                error = None
                for arg_index, serializer in enumerate(args_serializers):
                    try:
                        new_iterable.append(serializer(item, *args, **kwargs))
                        break
                    except (SerializationError, TypeError, ValueError) as exc:
                        if error is None:
                            error = SerializationError.from_exception(
                                exc,
                                message="Failed to serialize item at index",
                                input_type=type(value),
                                expected_type=type_args[arg_index],
                                location=[item_index],
                            )
                        else:
                            error.add(
                                exc,
                                input_type=type(value),
                                expected_type=type_args[arg_index],
                                location=[item_index],
                            )
                else:
                    if error:
                        raise error

            return origin(new_iterable)  # type: ignore

        return iterable_serializer

    raise TypeError(
        f"Cannot build {fmt!r} serializer for generic type {target!r} with origin {origin!r} and arguments {type_args!r}"
    )


################################
# SERIALIZER REGISTRY BUILDERS #
################################


def build_non_generic_type_serializer_registry(
    target: typing.Type[T],
    /,
    serializers: typing.Optional[
        typing.Mapping[
            str,
            Serializer[typing.Any],
        ]
    ] = None,
    depth: typing.Optional[int] = None,
) -> SerializerRegistry:
    """
    Build a serializer registry for non-generic types.

    :param target: The target non-generic type.
    :param serializers: A mapping of serialization formats to their respective serializer functions
    :param depth: Optional depth for serialization
    :return: A SerializerRegistry with the provided serializers
    """
    serializers_map = {
        **(serializers or {}),
    }
    if "json" not in serializers_map:
        serializers_map["json"] = build_generic_type_serializer(
            target, fmt="json", depth=depth
        )
    if "python" not in serializers_map:
        serializers_map["python"] = build_generic_type_serializer(
            target, fmt="python", depth=depth
        )
    return SerializerRegistry(
        defaultdict(
            _unsupported_serializer_factory,
            serializers_map,
        )
    )


def build_dataclass_serializer_registry(
    serializers: typing.Optional[typing.Mapping[str, Serializer[typing.Any]]] = None,
) -> SerializerRegistry:
    """
    Build a serializer registry for dataclass types.

    :param serializers: A mapping of serialization formats to their respective serializer functions
    :return: A SerializerRegistry with the provided serializers
    """
    serializers_map = {
        **(serializers or {}),
    }
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
    return SerializerRegistry(
        defaultdict(
            _unsupported_serializer_factory,
            serializers_map,
        )
    )


def build_generic_type_serializer_registry(
    target: typing.Union[typing.Type[T], T],
    /,
    serializers: typing.Optional[
        typing.Mapping[
            str,
            Serializer[typing.Any],
        ]
    ] = None,
    depth: typing.Optional[int] = None,
) -> SerializerRegistry:
    """
    Build a serializer registry for generic types.

    :param target: The target generic type.
    :param serializers: A mapping of serialization formats to their respective serializer functions
    :param depth: Optional depth for serialization
    """
    serializers_map = {
        **(serializers or {}),
    }
    if "json" not in serializers_map:
        serializers_map["json"] = build_generic_type_serializer(
            target,
            fmt="json",
            depth=depth,
        )
    if "python" not in serializers_map:
        serializers_map["python"] = build_generic_type_serializer(
            target,
            fmt="python",
            depth=depth,
        )
    return SerializerRegistry(
        defaultdict(
            _unsupported_serializer_factory,
            serializers_map,
        )
    )
