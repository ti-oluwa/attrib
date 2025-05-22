import inspect
import typing
import functools
from collections.abc import Iterable, Mapping, MutableMapping, Sequence, Set
from collections import defaultdict

from attrib._typing import Validator, T, Serializer, Deserializer
from attrib._utils import (
    is_generic_type,
    is_typed_dict,
    make_jsonable,
    SerializerRegistry,
    _unsupported_serializer_factory,
    any_func,
    resolve_type,
)
from attrib.exceptions import DeserializationError, SerializationError, ValidationError
from attrib.validators import Or, instance_of, iterable, mapping, member_of, eq
from attrib.serializers import serialize
from attrib.dataclass import Dataclass, deserialize, _Dataclass_co


class TypeAdapter(typing.Generic[T]):
    """
    Concrete `TypeAdapter` implementation.

    A type adapter is a pseudo-type. It defines type-like behavior using 3 methods:
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
        deserializer=lambda value, *args, **kwargs: value, # No coercion attempted
    )

    value = adapter("123") # deserializes to int and validates
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
    )

    def __init__(
        self,
        adapted: typing.Union[typing.Type[T], T],
        /,
        *,
        name: typing.Optional[str] = None,
        deserializer: typing.Optional[Deserializer[T]] = None,
        validator: typing.Optional[Validator[T]] = None,
        serializers: typing.Optional[
            typing.Mapping[str, Serializer[typing.Any]]
        ] = None,
        defer: bool = False,
        strict: bool = False,
    ) -> None:
        """
        Initialize the adapter.

        :param adapted: The target type to adapt
        :param name: The name of the adapted type
        :param validator: A function to validate values for the adapted type
        :param serializers: A mapping of serialization formats to their respective serializer functions
        :param deserializer: A function to coerce the value to a specific type
        :param defer: Whether to defer the building of the adapter probably for performance reasons,
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
        if not defer:
            self.build()

    def build(
        self,
        *,
        globalns: typing.Optional[typing.Dict[str, typing.Any]] = None,
        localns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> None:
        """
        Build the adapter with the provided parameters.

        :param globalns: Global namespace for resolving type references
        :param localns: Local namespace for resolving type references
        """
        self.adapted = resolve_type(
            self.adapted,
            globalns=globalns,
            localns=localns,
        )
        if is_generic_type(self.adapted):
            if (
                len(self.serializer.serializer_map) < 2
            ):  # Should contain at least "python" and "json" serializers
                self.serializer = build_generic_type_serializer_registry(
                    self.adapted, serializers=self.serializer.serializer_map
                )

            if self.validator is None:
                self.validator = build_generic_type_validator(self.adapted)

            if self.deserializer is None:
                self.deserializer = build_generic_type_deserializer(self.adapted)
            return

        if not isinstance(self.adapted, type):
            raise TypeError(f"Adapter target `{self.adapted}` must be a type")

        if len(self.serializer.serializer_map) < 2:
            serializers = self.serializer.serializer_map
            self.serializer = (
                build_dataclass_serializer_registry(serializers)
                if issubclass(self.adapted, Dataclass)
                else build_non_generic_type_serializer_registry(serializers)
            )

        if self.validator is None:
            self.validator = instance_of(self.adapted)
        if self.deserializer is None:
            self.deserializer = build_non_generic_type_deserializer(self.adapted)
        return

    @typing.overload
    def validate(
        self,
        value: T,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> T: ...

    @typing.overload
    def validate(
        self,
        value: typing.Any,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Any: ...

    def validate(
        self,
        value: typing.Union[T, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Union[T, typing.Any]:
        """
        Validate the value using the validator.

        :param value: The value to validate
        :param args: Additional arguments to pass to the validator
        :param kwargs: Additional keyword arguments to pass to the validator
        :return: None if all validators pass
        """
        if self.validator:
            try:
                self.validator(value, self, *args, **kwargs)
            except (ValidationError, ValueError, TypeError) as exc:
                raise ValidationError(
                    f"{value!r} is not a valid {self.name!r}"
                ) from exc
        return value

    def serialize(
        self,
        value: T,
        fmt: typing.Union[typing.Literal["python", "json"], str] = "python",
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Any:
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
                f"Cannot serialize value. A serializer was not initialized for '{self.name or repr(self)}'"
            )
        return self.serializer(fmt, value, *args, **kwargs)

    def deserialize(
        self,
        value: typing.Any,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> T:
        """
        Deserialize the value using the deserializer.

        :param value: The value to deserialize
        :param args: Additional arguments to pass to the deserializer
        :param kwargs: Additional keyword arguments to pass to the deserializer
        :return: The deserialized value
        """
        if self.deserializer is None:
            raise DeserializationError(
                f"Cannot deserialize value. A deserializer was not initialized for '{self.name or repr(self)}'"
            )

        kwargs.setdefault("strict", self.strict)
        try:
            return self.deserializer(value, *args, **kwargs)
        except (DeserializationError, ValueError, TypeError) as exc:
            raise DeserializationError(
                f"{value!r} cannot be deserialized to {self.name!r}"
            ) from exc

    def __call__(
        self,
        value: typing.Union[T, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> T:
        """
        Call the adapter to coerce the value to the adapted type and validate it.
        This method is a convenience method that combines deserialization and validation.

        :param value: The value to adapt
        :param args: Additional arguments for deserialization/validation
        :param kwargs: Additional keyword arguments for deserialization/validation
        :return: The validated value
        """
        deserialized = self.deserialize(value, *args, **kwargs)
        validated = self.validate(deserialized, *args, **kwargs)
        return validated

    def __repr__(self) -> str:
        """
        Return a string representation of the adapter.

        :return: A string representation of the adapter
        """
        return f"{self.__class__.__name__}(name={self.name or 'unset'}, adapted={self.adapted})"


def build_non_generic_type_serializer_registry(
    serializers: typing.Optional[
        typing.Mapping[
            str,
            Serializer[typing.Any],
        ]
    ] = None,
) -> SerializerRegistry:
    serializers_map = {
        **(serializers or {}),
    }
    if "json" not in serializers_map:
        serializers_map["json"] = _non_generic_type_json_serializer
    if "python" not in serializers_map:
        serializers_map["python"] = _non_generic_type_python_serializer
    return SerializerRegistry(
        defaultdict(
            _unsupported_serializer_factory,
            serializers_map,
        )
    )


@functools.lru_cache
def build_non_generic_type_deserializer(
    type_: typing.Type[T],
) -> Deserializer[T]:
    """
    Build a deserializer for a non-generic type.

    :param type_: The target type to adapt
    :param strict: Whether to enforce strict type checking and not attempt type coercion.
    :return: A function that attempts to coerce the value to the target type
    """
    if is_typed_dict(type_):
        return build_typeddict_deserializer(type_)

    def deserializer(
        value: typing.Any,
        *_: typing.Any,
        **kwargs: typing.Any,
    ) -> T:
        """
        A deserializer function that attempts to coerce the value to the target type.

        :param value: The value to deserialize
        :param args: Additional arguments for deserialization
        :param kwargs: Additional keyword arguments for deserialization
        """
        if type_ is typing.Any or isinstance(value, type_):
            return value

        if kwargs.pop("strict", False):
            raise DeserializationError(
                f"Cannot deserialize {value!r} to {type_!r} without coercion. Set strict=False to allow coercion."
            )

        if issubclass(type_, type(None)) and value is not None:
            raise DeserializationError(
                f"Cannot deserialize {value!r}. Expected value to be None"
            )

        if issubclass(type_, Dataclass):
            return _dataclass_deserializer(type_, value, **kwargs)

        try:
            return type_(value)  # type: ignore[call-arg]
        except (ValueError, TypeError) as exc:
            raise DeserializationError(
                f"Cannot deserialize {value!r} to {type_!r}"
            ) from exc

    deserializer.__name__ = f"{type_.__name__}_deserializer"
    return deserializer


def build_non_generic_type_validator(target: typing.Type[T], /) -> Validator[T]:
    if is_typed_dict(target):
        return build_typeddict_validator(target)
    return instance_of(target)


def build_dataclass_serializer_registry(
    serializers: typing.Optional[typing.Mapping[str, Serializer[typing.Any]]] = None,
) -> SerializerRegistry:
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
) -> SerializerRegistry:
    serializers_map = {
        **(serializers or {}),
    }
    if "json" not in serializers_map:
        serializers_map["json"] = build_generic_type_serializer(
            target,
            fmt="json",
        )
    if "python" not in serializers_map:
        serializers_map["python"] = build_generic_type_serializer(
            target,
            fmt="python",
        )
    return SerializerRegistry(
        defaultdict(
            _unsupported_serializer_factory,
            serializers_map,
        )
    )


@functools.lru_cache
def build_typeddict_deserializer(
    target: typing.Type[T],
    /,
) -> Deserializer[T]:
    """
    Build a deserializer for a TypedDict type.

    :param target: The target type to adapt
    :return: A function that attempts to coerce the value to the target type
    """
    if not is_typed_dict(target):
        raise TypeError(f"Cannot build deserializer for non-TypedDict type {target!r}")

    annotations = typing.get_type_hints(target, include_extras=True)
    required_keys = getattr(target, "__required_keys__", set())
    optional_keys = getattr(target, "__optional_keys__", set())
    deserializers_map: typing.Dict[str, Deserializer[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            deserializers_map[key] = build_generic_type_deserializer(value)
        else:
            deserializers_map[key] = build_non_generic_type_deserializer(value)

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
        if not isinstance(value, Mapping):
            raise DeserializationError(f"Cannot deserialize {value!r} to {target!r}")

        mapping_keys = set(value.keys())
        # If deserialization is not strict and all of the typedicts keys are not present in the
        # mapping, just return an empty mapping
        if (
            not kwargs.get("strict", False)
            and (mapping_keys - set(deserializers_map.keys())) == mapping_keys
        ):
            return target()

        if required_keys:
            if (mapping_keys & required_keys) != required_keys:
                raise DeserializationError(
                    f"Value is missing required keys {required_keys - mapping_keys} in {value!r}"
                )

        new_mapping = {}
        for key, item in value.items():
            if key not in deserializers_map:
                continue
            try:
                new_mapping[key] = deserializers_map[key](item, *args, **kwargs)
            except (TypeError, ValueError, DeserializationError) as exc:
                if key in optional_keys:
                    continue
                raise DeserializationError(
                    f"Failed to deserialize {value!r} to {target!r}"
                ) from exc

        return target(**new_mapping)

    deserializer.__name__ = f"{target.__name__}_deserializer"
    return deserializer


@functools.lru_cache
def build_typeddict_validator(
    target: typing.Type[T],
    /,
) -> Validator[T]:
    """
    Build a validator for a TypedDict type.

    :param target: The target type to adapt
    :return: A function that attempts to coerce the value to the target type
    """
    annotations = typing.get_type_hints(target, include_extras=True)
    required_keys = getattr(target, "__required_keys__", set())
    validators_map: typing.Dict[str, Validator[typing.Any]] = {}
    for key, value in annotations.items():
        if is_generic_type(value):
            validators_map[key] = build_generic_type_validator(value)
        else:
            validators_map[key] = build_non_generic_type_validator(value)

    def validator(
        value: typing.Union[T, typing.Any],
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
            raise ValidationError(f"Cannot validate {value!r} as {target!r}")

        mapping_keys = set(value.keys())
        # If all of the typedicts keys are not present in the
        # mapping, just return
        if (mapping_keys - set(validators_map.keys())) == mapping_keys:
            return

        if required_keys:
            if (mapping_keys & required_keys) != required_keys:
                raise ValidationError(
                    f"Value is missing required keys {required_keys - mapping_keys} in {value!r}"
                )

        for key, item in value.items():
            if key not in validators_map:
                continue
            try:
                validators_map[key](item, *args, **kwargs)
            except (ValidationError, TypeError, ValueError) as exc:
                raise ValidationError(
                    f"Failed to validate {value!r} as {target!r}"
                ) from exc

        return None

    validator.__name__ = f"{target.__name__}_validator"
    return validator


@functools.lru_cache
def build_generic_type_deserializer(
    target: typing.Union[typing.Type[T], T],
) -> Deserializer[typing.Any]:
    """
    Build a deserializer for a generic type.

    :param target: The target type to build deserializer for
    :param strict: Whether to enforce strict type checking and not attempt type coercion.
    :return: A deserializer function for the target type
    """
    origin = typing.get_origin(target)
    args = typing.get_args(target)
    if not (origin or args):
        raise TypeError(f"Cannot build deserializer for non-generic type {target!r}")

    if origin is None:
        if not args:
            raise TypeError(
                f"Cannot build deserializer for non-generic type {target!r}"
            )
        # If the origin is None, we need to use the first argument as the origin
        # and the rest as arguments.
        return any_func(
            *(
                build_generic_type_deserializer(arg)
                if is_generic_type(arg)
                else build_non_generic_type_deserializer(arg)
                for arg in args
            ),
            target_exception=(
                TypeError,
                ValueError,
                DeserializationError,
            ),
        )
    elif origin and not args:
        return (
            build_generic_type_deserializer(origin)
            if is_generic_type(origin)
            else build_non_generic_type_deserializer(origin)
        )

    if not inspect.isclass(origin):
        if origin is typing.Literal:
            # If the origin is Literal, the deserializer should just return the value as is
            return lambda value, *args, **kwargs: value

        args_deserializers = tuple(
            [
                build_generic_type_deserializer(arg)
                if is_generic_type(arg)
                else build_non_generic_type_deserializer(arg)
                for arg in args
            ]
        )
        return any_func(
            *args_deserializers,
            target_exception=(
                TypeError,
                ValueError,
                DeserializationError,
            ),
        )

    args_deserializers = tuple(
        [
            build_generic_type_deserializer(arg)
            if is_generic_type(arg)
            else build_non_generic_type_deserializer(arg)
            for arg in args
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
            try:
                new_mapping = origin.__new__(origin)  # type: ignore[assignment]
                if isinstance(value, Mapping):
                    iterator = value.items()
                else:
                    iterator = iter(value)

                for key, item in iterator:
                    new_mapping[key_deserializer(key, *args, **kwargs)] = (
                        value_deserializer(item, *args, **kwargs)
                    )
                return new_mapping
            except Exception as exc:
                raise DeserializationError(
                    f"Failed to deserialize {value!r} to type {target!r}"
                ) from exc

        return mapping_deserializer

    if issubclass(origin, (Sequence, Set)):
        args_count = len(args)
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
                    raise DeserializationError(
                        f"Cannot deserialize {value!r} to {target!r}"
                    )

                new_tuple = []
                for index, item in enumerate(value):
                    try:
                        new_tuple.append(
                            args_deserializers[index](item, *args, **kwargs)
                        )
                    except (TypeError, ValueError, DeserializationError) as exc:
                        raise DeserializationError(
                            f"Failed to deserialize {value!r} to {target!r}"
                        ) from exc

                return origin(new_tuple)

            return tuple_deserializer

        def sequence_deserializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Iterable[typing.Any]:
            if not isinstance(value, Iterable):
                raise DeserializationError(
                    f"Cannot deserialize {value!r} to {target!r}"
                )

            new_sequence = []
            for item in value:
                error = None
                for deserializer in args_deserializers:
                    try:
                        new_sequence.append(deserializer(item, *args, **kwargs))
                        break
                    except (TypeError, ValueError, DeserializationError) as exc:
                        error = exc
                        continue
                else:
                    if error:
                        raise DeserializationError(
                            f"Failed to deserialize {value!r} to {target!r}"
                        ) from error

            return origin(new_sequence)  # type: ignore

        return sequence_deserializer

    raise TypeError(
        f"Cannot build deserializer for generic type {target!r} with origin {origin!r} and arguments {args!r}"
    )


@functools.lru_cache
def build_generic_type_validator(
    target: typing.Union[typing.Type[T], T],
) -> Validator[T]:
    """
    Build a validator for a generic type.

    :param target: The target type to build validator for
    :return: A validator function for the target type
    """
    origin = typing.get_origin(target)
    args = typing.get_args(target)
    if not (origin or args):
        raise TypeError(f"Cannot build validator for non-generic type {target!r}")

    if origin is None:
        if not args:
            raise TypeError(
                f"Cannot build deserializer for non-generic type {target!r}"
            )
        # If the origin is None, we need to use the first argument as the origin
        # and the rest as arguments.
        return Or(
            tuple(
                build_generic_type_validator(arg)
                if is_generic_type(arg)
                else build_non_generic_type_validator(arg)
                for arg in args
            )
        )
    elif origin and not args:
        return (
            build_generic_type_validator(origin)
            if is_generic_type(origin)
            else build_non_generic_type_validator(origin)
        )

    # If the origin is not a class, we can just build an Or validator
    # from the arguments validators.
    if not inspect.isclass(origin):
        if origin is typing.Literal:
            return eq(args[0]) if len(args) == 1 else member_of(args)

        args_validators = tuple(
            [
                build_generic_type_validator(arg)
                if is_generic_type(arg)
                else build_non_generic_type_validator(arg)
                for arg in args
            ]
        )
        return Or(args_validators)

    args_validators = tuple(
        [
            build_generic_type_validator(arg)
            if is_generic_type(arg)
            else build_non_generic_type_validator(arg)
            for arg in args
        ]
    )
    if issubclass(origin, Mapping):
        assert len(args_validators) == 2, (
            f"Validator count mismatch. Expected 2 but got {len(args_validators)}"
        )
        key_validator, value_validator = args_validators
        return mapping(key_validator, value_validator)

    if issubclass(origin, (Sequence, Set)):
        return iterable(Or(args_validators))

    raise TypeError(
        f"Cannot build validator for generic type {target!r} with origin {origin!r} and arguments {args!r}"
    )


@functools.lru_cache
def build_generic_type_serializer(
    target: typing.Union[typing.Type[T], T],
    *,
    fmt: typing.Literal["json", "python"] = "python",
) -> Serializer[typing.Any]:
    """
    Build a python serializer for a generic type.

    :param target: The target type to build serializer for
    :return: A serializer function for the target type
    """
    origin = typing.get_origin(target)
    args = typing.get_args(target)

    if not (origin or args):
        raise TypeError(
            f"Cannot build {fmt!r} serializer for non-generic type {target!r}"
        )

    if origin is None:
        if not args:
            raise TypeError(
                f"Cannot build {fmt!r} serializer for non-generic type {target!r}"
            )
        return any_func(
            *(
                build_generic_type_serializer(arg, fmt=fmt)
                if is_generic_type(arg)
                else (
                    _non_generic_type_python_serializer
                    if fmt == "python"
                    else _non_generic_type_json_serializer
                )
                for arg in args
            ),
            target_exception=(
                TypeError,
                ValueError,
                SerializationError,
            ),
        )

    elif origin and not args:
        return (
            build_generic_type_serializer(origin, fmt=fmt)
            if is_generic_type(origin)
            else (
                _non_generic_type_python_serializer
                if fmt == "python"
                else _non_generic_type_json_serializer
            )
        )

    args_serializers = tuple(
        [
            build_generic_type_serializer(arg, fmt=fmt)
            if is_generic_type(arg)
            else (
                _non_generic_type_python_serializer
                if fmt == "python"
                else _non_generic_type_json_serializer
            )
            for arg in args
        ]
    )

    if not inspect.isclass(origin):
        if origin is typing.Literal:
            if fmt == "json":
                return _non_generic_type_json_serializer
            return _non_generic_type_python_serializer

        args_serializers = tuple(
            [
                build_generic_type_serializer(arg, fmt=fmt)
                if is_generic_type(arg)
                else (
                    _non_generic_type_python_serializer
                    if fmt == "python"
                    else _non_generic_type_json_serializer
                )
                for arg in args
            ]
        )
        return any_func(
            *args_serializers,
            target_exception=(
                TypeError,
                ValueError,
                SerializationError,
            ),
        )

    args_serializers = tuple(
        [
            build_generic_type_serializer(arg, fmt=fmt)
            if is_generic_type(arg)
            else (
                _non_generic_type_python_serializer
                if fmt == "python"
                else _non_generic_type_json_serializer
            )
            for arg in args
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
            try:
                new_mapping = origin.__new__(origin)  # type: ignore[assignment]
                if isinstance(value, Mapping):
                    iterator = value.items()
                else:
                    iterator = iter(value)

                for key, item in iterator:
                    new_mapping[key_serializer(key, *args, **kwargs)] = (
                        value_serializer(item, *args, **kwargs)
                    )
                return new_mapping
            except (SerializationError, TypeError, ValueError) as exc:
                raise SerializationError(
                    f"Failed to serialize {value!r} to type {target!r}"
                ) from exc

        return mapping_serializer

    if issubclass(origin, (Sequence, Set)):
        args_count = len(args)
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
                    raise SerializationError(
                        f"Cannot serialize {value!r} to {target!r}"
                    )
                new_tuple = []
                for index, item in enumerate(value):
                    try:
                        new_tuple.append(args_serializers[index](item, *args, **kwargs))
                    except (SerializationError, TypeError, ValueError) as exc:
                        raise SerializationError(
                            f"Failed to serialize {value!r} to {target!r}"
                        ) from exc
                return origin(new_tuple)

            return tuple_serializer

        def sequence_serializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Iterable[typing.Any]:
            if not isinstance(value, Iterable):
                raise SerializationError(f"Cannot serialize {value!r} to {target!r}")

            new_sequence = []
            for item in value:
                error = None
                for serializer in args_serializers:
                    try:
                        new_sequence.append(serializer(item, *args, **kwargs))
                        break
                    except (SerializationError, TypeError, ValueError) as exc:
                        error = exc
                        continue
                else:
                    if error:
                        raise SerializationError(
                            f"Failed to serialize {value!r} to {target!r}"
                        ) from error

            return origin(new_sequence)  # type: ignore

        return sequence_serializer

    raise TypeError(
        f"Cannot build {fmt!r} serializer for generic type {target!r} with origin {origin!r} and arguments {args!r}"
    )


BUILTIN_TYPES = (
    int,
    float,
    bool,
    Set,
    Sequence,
    Mapping,
)


def _dataclass_deserializer(
    target: typing.Type[_Dataclass_co],
    /,
    value: typing.Any,
    *_: typing.Any,
    **kwargs: typing.Any,
) -> _Dataclass_co:
    """
    A deserializer function that attempts to coerce the value to the target type.

    :param value: The value to deserialize
    :param args: Additional arguments for deserialization
    :param kwargs: Additional keyword arguments for deserialization
    """
    if isinstance(value, target):
        return value
    if not isinstance(value, BUILTIN_TYPES):
        kwargs.setdefault("attributes", True)
    return deserialize(target, value, **kwargs)


def _non_generic_type_json_serializer(
    value: typing.Any, *_: typing.Any, **kwargs: typing.Any
) -> typing.Any:
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
