import inspect
import typing
import functools
from collections.abc import Mapping, MutableMapping, Sequence, Set
from collections import defaultdict

from attrib._typing import Validator, T, Serializer, Deserializer
from attrib._utils import (
    is_generic_type,
    is_iterable_type,
    is_mapping_type,
    is_iterable,
    make_jsonable,
    SerializerRegistry,
    _unsupported_serializer_factory,
    any_func,
)
from attrib.exceptions import DeserializationError, SerializationError, ValidationError
from attrib.validators import Pipeline, Or, instance_of, iterable, mapping
from attrib.serializers import serialize
from attrib.dataclass import Dataclass, deserialize, _Dataclass_co


@typing.final
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

    adapter = TypeAdapter(
        name="StrictInt",
        validators=[instance_of(int)],
        serializers={
            "json": lambda value, *args, **kwargs: value,
            "python": lambda value, *args, **kwargs: value,
        },
        deserializer=lambda value, *args, **kwargs: int(value),
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

    __slots__ = ("name", "validator", "serializer", "deserializer")

    def __init__(
        self,
        name: typing.Optional[str] = None,
        /,
        *,
        deserializer: typing.Optional[Deserializer[T]] = None,
        validators: typing.Optional[typing.Iterable[Validator[T]]] = None,
        serializers: typing.Optional[
            typing.Mapping[str, Serializer[typing.Any]]
        ] = None,
    ) -> None:
        """
        Initialize the adapter.

        :param name: The name of the adapted type
        :param validators: An iterable of value validators
        :param serializers: A mapping of serialization formats to their respective serializer functions
        :param deserializer: A function to coerce the value to a specific type
        """
        self.name = name
        self.validator = Pipeline(tuple(validators)) if validators else None
        self.serializer = SerializerRegistry(
            defaultdict(_unsupported_serializer_factory, serializers or {}),
        )
        self.deserializer = deserializer

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
        fmt: str = "python",
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
        if not self.deserializer:
            raise DeserializationError(
                f"Cannot deserialize value. '{self.name or type(self).__name__}' was not initialized with a deserializer"
            )
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
        self.validate(deserialized, *args, **kwargs)
        return deserialized

    def __instancecheck__(self, value: typing.Any) -> bool:
        """
        Check if the value is an instance of the adapted type.

        :param value: The value to check
        :return: True if the value is an instance of the adapted type, False otherwise
        """
        try:
            self.validate(value)
        except ValidationError:
            return False
        return True

    def __str__(self) -> str:
        return self.name or repr(self)

    def __repr__(self) -> str:
        """
        Return a string representation of the adapter.

        :return: A string representation of the adapter
        """
        return f"{self.__class__.__name__}({self.name or 'Unknown'})"


@functools.lru_cache
def _build_non_generic_type_deserializer(
    type_: typing.Type[T],
    *,
    strict: bool = False,
) -> Deserializer:
    """
    Build a deserializer for a non-generic type.

    :param type_: The target type to adapt
    :param strict: Whether to enforce strict type checking and not attempt type coercion.
    :return: A function that attempts to coerce the value to the target type
    """

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
        if strict:
            raise DeserializationError(
                f"Cannot deserialize {value!r} to {type_!r} without coercion. Set strict=False to allow coercion."
            )

        if issubclass(type_, Dataclass):
            return _dataclass_deserializer(type_, value, **kwargs)

        if issubclass(type_, type(None)) and value is not None:
            raise DeserializationError(
                f"Cannot deserialize {value!r}. Expected value to be None"
            )

        try:
            return type_(value)  # type: ignore[call-arg]
        except (ValueError, TypeError) as exc:
            raise DeserializationError(
                f"Cannot deserialize {value!r} to {type_!r}"
            ) from exc

    return deserializer


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
    value: typing.Any,
    *_: typing.Any,
    **kwargs: typing.Any,
) -> _Dataclass_co:
    """
    Deserialize a value to a dataclass instance.

    :param target: The target dataclass type
    :param value: The value to deserialize
    :param args: Additional arguments for deserialization
    :param kwargs: Additional keyword arguments for deserialization
    :return: An instance of the target dataclass
    """
    if isinstance(value, target):
        return value
    if not isinstance(value, BUILTIN_TYPES):
        kwargs.setdefault("attributes", True)
    return deserialize(target, value, **kwargs)


@functools.lru_cache
def _build_generic_type_deserializer(
    target: typing.Type[T], *, strict: bool = False
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
                _build_generic_type_deserializer(arg, strict=strict)
                if is_generic_type(arg)
                else _build_non_generic_type_deserializer(arg, strict=strict)
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
            _build_generic_type_deserializer(origin, strict=strict)
            if is_generic_type(origin)
            else _build_non_generic_type_deserializer(origin, strict=strict)
        )

    args_deserializers = tuple(
        [
            _build_generic_type_deserializer(arg, strict=strict)
            if is_generic_type(arg)
            else _build_non_generic_type_deserializer(arg, strict=strict)
            for arg in args
        ]
    )
    if not inspect.isclass(origin):
        return any_func(
            *args_deserializers,
            target_exception=(
                TypeError,
                ValueError,
                DeserializationError,
            ),
        )

    if is_mapping_type(origin):
        if len(args) != 2:
            raise TypeError(
                f"Cannot build deserializer for mapping type {target!r} with {len(args_deserializers)} arguments. Expected 2."
            )
        key_deserializer = args_deserializers[0]
        value_deserializer = args_deserializers[1]
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

    if is_iterable_type(origin, exclude=(str, bytes, dict)) or issubclass(
        origin, Sequence
    ):

        def iterable_deserializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Iterable[typing.Any]:
            if not is_iterable(value):
                raise DeserializationError(
                    f"Cannot deserialize {value!r} to {target!r}"
                )

            new_iterable = []
            for item in value:
                error = None
                for deserializer in args_deserializers:
                    try:
                        new_iterable.append(deserializer(item, *args, **kwargs))
                        break
                    except (TypeError, ValueError, DeserializationError) as exc:
                        error = exc
                        continue
                else:
                    if error:
                        raise DeserializationError(
                            f"Failed to deserialize {value!r} to {target!r}"
                        ) from error

            if origin is not list:
                return origin(new_iterable)  # type: ignore
            return new_iterable

        return iterable_deserializer

    raise TypeError(
        f"Cannot build deserializer for generic type {target!r} with origin {origin!r} and arguments {args!r}"
    )


@functools.lru_cache
def _build_generic_type_validator(
    target: typing.Type[T],
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
                _build_generic_type_validator(arg)
                if is_generic_type(arg)
                else instance_of(arg)
                for arg in args
            )
        )
    elif origin and not args:
        return (
            _build_generic_type_validator(origin)
            if is_generic_type(origin)
            else instance_of(origin)
        )

    args_validators = tuple(
        [
            _build_generic_type_validator(arg)
            if is_generic_type(arg)
            else instance_of(arg)
            for arg in args
        ]
    )
    # If the origin is not a class, we can just build an Or validator
    # from the arguments validators.
    if not inspect.isclass(origin):
        return Or(args_validators)

    if is_mapping_type(origin):
        if len(args) != 2:
            raise TypeError(
                f"Cannot build validator for mapping type {target!r} with {len(args)} arguments. Expected 2."
            )
        key_validator, value_validator = args_validators
        return mapping(key_validator, value_validator)

    if is_iterable_type(origin, exclude=(str, bytes, dict)) or issubclass(
        origin, Sequence
    ):
        return iterable(Or(args_validators))

    raise TypeError(
        f"Cannot build validator for generic type {target!r} with origin {origin!r} and arguments {args!r}"
    )


@functools.lru_cache
def _build_generic_type_serializer(
    target: typing.Type[T],
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
                _build_generic_type_serializer(arg, fmt=fmt)
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
            _build_generic_type_serializer(origin, fmt=fmt)
            if is_generic_type(origin)
            else (
                _non_generic_type_python_serializer
                if fmt == "python"
                else _non_generic_type_json_serializer
            )
        )

    args_serializers = tuple(
        [
            _build_generic_type_serializer(arg, fmt=fmt)
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
        return any_func(
            *args_serializers,
            target_exception=(
                TypeError,
                ValueError,
                SerializationError,
            ),
        )

    if is_mapping_type(origin):
        if len(args) != 2:
            raise TypeError(
                f"Cannot build {fmt!r} serializer for mapping type {target!r} with {len(args_serializers)} arguments. Expected 2."
            )
        key_serializer = args_serializers[0]
        value_serializer = args_serializers[1]
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

    if is_iterable_type(origin, exclude=(str, bytes, dict)) or issubclass(
        origin, Sequence
    ):

        def iterable_serializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Iterable[typing.Any]:
            if not is_iterable(value):
                raise SerializationError(f"Cannot serialize {value!r} to {target!r}")

            new_iterable = []
            for item in value:
                error = None
                for serializer in args_serializers:
                    try:
                        new_iterable.append(serializer(item, *args, **kwargs))
                        break
                    except (SerializationError, TypeError, ValueError) as exc:
                        error = exc
                        continue
                else:
                    if error:
                        raise SerializationError(
                            f"Failed to serialize {value!r} to {target!r}"
                        ) from error

            if origin is not list:
                return origin(new_iterable)  # type: ignore
            return new_iterable

        return iterable_serializer

    raise TypeError(
        f"Cannot build {fmt!r} serializer for generic type {target!r} with origin {origin!r} and arguments {args!r}"
    )


def _build_generic_type_adapter(
    target: T,
    /,
    *,
    name: typing.Optional[str] = None,
    strict: bool = False,
    validators: typing.Optional[typing.Iterable[Validator[T]]] = None,
    serializers: typing.Optional[typing.Mapping[str, Serializer[typing.Any]]] = None,
    deserializer: typing.Optional[Deserializer[T]] = None,
) -> TypeAdapter[T]:
    """
    Build an adapter for a generic type.

    :param target: The target type to adapt
    :param name: The name of the adapted type
    :param strict: Whether to enforce strict validation and not attempt type coercion.
    :param validators: An iterable of value validators
    :param serializers: A mapping of serialization formats to their respective serializer functions
    :param deserializer: A function to coerce the value to a specific type
    :return: An instance of `TypeAdapter` for the target type
    """
    all_validators = [
        *(validators or []),
        _build_generic_type_validator(target),
    ]
    all_serializers = {
        **(serializers or {}),
    }
    if "json" not in all_serializers:
        all_serializers["json"] = _build_generic_type_serializer(target, fmt="json")
    if "python" not in all_serializers:
        all_serializers["python"] = _build_generic_type_serializer(target, fmt="python")

    if not deserializer:
        return TypeAdapter(
            name or repr(target),
            validators=all_validators,
            serializers=all_serializers,
            deserializer=_build_generic_type_deserializer(target, strict=strict),
        )
    return TypeAdapter(
        name or repr(target),
        validators=all_validators,
        serializers=all_serializers,
        deserializer=deserializer,
    )


def _build_non_generic_type_adapter(
    target: typing.Type[T],
    /,
    *,
    name: typing.Optional[str] = None,
    strict: bool = False,
    validators: typing.Optional[typing.Iterable[Validator[T]]] = None,
    serializers: typing.Optional[typing.Mapping[str, Serializer[typing.Any]]] = None,
    deserializer: typing.Optional[Deserializer[T]] = None,
) -> TypeAdapter[T]:
    """
    Build an adapter for a non-generic type.

    :param target: The target type to adapt
    :param name: The name of the adapted type
    :param strict: Whether to enforce strict type checking and not attempt type coercion.
    :param validators: An iterable of value validators
    :param serializers: A mapping of serialization formats to their respective serializer functions
    :param deserializer: A function to coerce the value to a specific type
    :return: An instance of `TypeAdapter` for the target type
    """
    all_validators = [
        *(validators or []),
        instance_of(target),
    ]
    all_serializers = {
        "json": _non_generic_type_json_serializer,
        "python": _non_generic_type_python_serializer,
        **(serializers or {}),
    }
    return TypeAdapter(
        name or repr(target),
        validators=all_validators,
        serializers=all_serializers,
        deserializer=deserializer
        or _build_non_generic_type_deserializer(target, strict=strict),
    )


def _build_dataclass_adapter(
    target: typing.Type[_Dataclass_co],
    /,
    *,
    name: typing.Optional[str] = None,
    validators: typing.Optional[typing.Iterable[Validator[_Dataclass_co]]] = None,
    serializers: typing.Optional[typing.Mapping[str, Serializer[typing.Any]]] = None,
    deserializer: typing.Optional[Deserializer[_Dataclass_co]] = None,
) -> TypeAdapter[_Dataclass_co]:
    """
    Build a dataclass type adapter for the target type.

    :param target: The target type to adapt
    :param name: The name of the adapted type
    :param validators: An iterable of value validators
    :param serializers: A mapping of serialization formats to their respective serializer functions
    :param deserializer: A function to coerce the value to a specific type
    :return: An instance of `TypeAdapter` for the target type
    """
    all_validators = [
        *(validators or []),
        instance_of(target),
    ]
    all_serializers = {
        "json": lambda value, *_, **kwargs: serialize(
            value,
            fmt="json",
            **kwargs,
        ),
        "python": lambda value, *_, **kwargs: serialize(
            value,
            fmt="python",
            **kwargs,
        ),
        **(serializers or {}),
    }
    if not deserializer:
        return TypeAdapter(
            name or repr(target),
            validators=all_validators,
            serializers=all_serializers,
            deserializer=lambda value, *args, **kwargs: _dataclass_deserializer(
                target, value, *args, **kwargs
            ),
        )
    return TypeAdapter(
        name or repr(target),
        validators=all_validators,
        serializers=all_serializers,
        deserializer=deserializer,
    )


@typing.overload
def build_adapter(
    target: typing.Type[T],
    /,
    *,
    name: typing.Optional[str] = ...,
    strict: bool = ...,
    validators: typing.Optional[typing.Iterable[Validator[T]]] = ...,
    serializers: typing.Optional[typing.Mapping[str, Serializer[typing.Any]]] = ...,
    deserializer: typing.Optional[Deserializer[T]] = ...,
) -> TypeAdapter[T]: ...


@typing.overload
def build_adapter(
    target: typing.Type[_Dataclass_co],
    /,
    *,
    name: typing.Optional[str] = ...,
    validators: typing.Optional[typing.Iterable[Validator[_Dataclass_co]]] = ...,
    serializers: typing.Optional[typing.Mapping[str, Serializer[typing.Any]]] = ...,
    deserializer: typing.Optional[Deserializer[_Dataclass_co]] = ...,
) -> TypeAdapter[_Dataclass_co]: ...


@typing.overload
def build_adapter(
    target: T,
    /,
    *,
    name: typing.Optional[str] = ...,
    strict: bool = ...,
    validators: typing.Optional[typing.Iterable[Validator[T]]] = ...,
    serializers: typing.Optional[typing.Mapping[str, Serializer[typing.Any]]] = ...,
    deserializer: typing.Optional[Deserializer[T]] = ...,
) -> TypeAdapter[T]: ...


def build_adapter(
    target: typing.Union[T, typing.Type[T], typing.Type[_Dataclass_co]],
    /,
    *,
    name: typing.Optional[str] = None,
    strict: bool = False,
    validators: typing.Optional[typing.Iterable[Validator]] = None,
    serializers: typing.Optional[typing.Mapping[str, Serializer[typing.Any]]] = None,
    deserializer: typing.Optional[Deserializer] = None,
) -> TypeAdapter[typing.Any]:
    """
    Build a type adapter for the target type.

    :param target: The target type to adapt
    :param name: The name of the adapted type

    :param strict: Whether to enforce strict type checking and not attempt type coercion. This value only affects the deserialization process.

    :param validators: An iterable of custom value validators
        (e.g., `attrib.validators.instance_of`, `attrib.validators.iterable`, etc.)
        to validate the value after deserialization.
        These validators are applied in the order they are provided, after which
        the validator generated from the target type is applied.

    :param serializers: A mapping of serialization formats to their respective custom serializer functions
        If not provided, serializers for JSON and Python formats are generated for the target type automatically.
        Provided serializers will precede the generated ones.

    :param deserializer: A custom function to coerce any value to the target type.
        If not provided, a default deserializer is generated for the target type.
    :return: An instance of `TypeAdapter` for the target type
    """
    if is_generic_type(target):
        return _build_generic_type_adapter(
            target,
            name=name,
            strict=strict,
            validators=validators,
            serializers=serializers,
            deserializer=deserializer,
        )

    if not isinstance(target, type):
        raise TypeError("Adapter target must be a type")

    if issubclass(target, Dataclass):
        return _build_dataclass_adapter(
            target,
            name=name,
            validators=validators,
            serializers=serializers,
            deserializer=deserializer,
        )
    return _build_non_generic_type_adapter(
        target,
        name=name,
        strict=strict,
        validators=validators,
        serializers=serializers,
        deserializer=deserializer,
    )
