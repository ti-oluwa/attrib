"""Data description and validation fields."""

import enum
import functools
from types import NoneType
import uuid
import decimal
import typing
import base64
import io
import copy
import pathlib
from typing_extensions import Unpack, Self, Annotated
import annotated_types as annot
from collections import defaultdict
import collections.abc
from dataclasses import dataclass

from attrib import validators as field_validators
from attrib.exceptions import (
    FieldError,
    SerializationError,
    DeserializationError,
    ValidationError,
)
from attrib._utils import (
    iexact,
    is_valid_type,
    is_iterable_type,
    is_generic_type,
    _LRUCache,
    get_cache_key,
    make_jsonable,
    _get_itertype_adder,
    resolve_type,
    SerializerRegistry,
)
from attrib._typing import P, R, SupportsRichComparison, Validator, IterType, EMPTY


__all__ = [
    "AnyType",
    "FieldError",
    "Field",
    "Factory",
    "FieldInitKwargs",
    "Any",
    "Boolean",
    "String",
    "Float",
    "Integer",
    "Dict",
    "List",
    "Set",
    "Tuple",
    "Decimal",
    "Email",
    "Choice",
    "JSON",
    "Slug",
    "Bytes",
    "IOBase",
    "Path",
]

_T = typing.TypeVar("_T")
_V = typing.TypeVar("_V")


@typing.final
class AnyType:
    """Class to represent the Any type."""

    def __init_subclass__(cls):
        raise TypeError("AnyType cannot be subclassed.")

    def __new__(cls):
        raise TypeError("AnyType cannot be instantiated.")

    def __instancecheck__(self, instance: typing.Any) -> bool:
        return True


NonTupleFieldType: typing.TypeAlias = typing.Union[
    str,
    _T,
    typing.Type[_T],
    typing.Type[AnyType],
    typing.ForwardRef,
]
FieldType: typing.TypeAlias = typing.Union[
    NonTupleFieldType[_T],
    typing.Tuple[typing.Union[typing.ForwardRef, typing.Type[_T]], ...],
]
NonForwardRefFieldType: typing.TypeAlias = typing.Union[
    _T,
    typing.Type[_T],
    typing.Type[AnyType],
    typing.Tuple[typing.Type[_T], ...],
]

DefaultFactory = typing.Callable[[], typing.Union[_T, typing.Any]]
"""Type alias for default value factories."""
FieldSerializer: typing.TypeAlias = typing.Callable[
    [
        _T,
        typing.Union["_Field_co", typing.Any],
        typing.Optional[typing.Dict[str, typing.Any]],
    ],
    typing.Any,
]
"""
Type alias for serializers.

Takes three arguments - the value, the field instance, and optional context, and returns the serialized value.
Should raise a SerializationError if serialization fails.
"""
FieldDeserializer: typing.TypeAlias = typing.Callable[
    [
        typing.Any,
        typing.Union["_Field_co", typing.Any],
    ],
    _T,
]
"""
Type alias for deserializers.

Takes a two arguments - the value to deserialize, and the field instance.
Returns the deserialized value.
Should raise a DeserializationError if deserialization fails.
"""


def to_json_serializer(
    value: typing.Any,
    field: "Field",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> typing.Any:
    return make_jsonable(value)


def to_string_serializer(
    value: typing.Any,
    field: "Field",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> str:
    """Serialize a value to a string."""
    return str(value)


def unsupported_serializer(
    value: typing.Any,
    field: "Field",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> None:
    """Raise an error for unsupported serialization."""
    raise SerializationError(
        f"'{type(field).__name__}' does not support serialization format. "
        f"Supported formats are: {', '.join(field.serializer.serializer_map.keys())}.",
        field.effective_name,
    )


def _unsupported_serializer_factory():
    """
    Return a function that raises an error for unsupported serialization.

    To be used in defaultdict for field serializer instantiation
    """
    return unsupported_serializer


def unsupported_deserializer(value: typing.Any, field: "Field") -> None:
    """Raise an error for unsupported deserialization."""
    raise DeserializationError(
        f"'{type(field).__name__}' does not support deserialization '{value}'.",
        field.effective_name,
    )


def to_python_serializer(
    value: _T,
    field: "Field",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> _T:
    """Serialize a value to Python object."""
    return value


DEFAULT_FIELD_SERIALIZERS: typing.Dict[str, FieldSerializer] = {
    "json": to_json_serializer,
    "python": to_python_serializer,
}


def default_deserializer(
    value: typing.Any,
    field: "Field[_T]",
) -> typing.Union[_T, typing.Any]:
    """
    Deserialize a value to the specified field type.

    :param value: The value to deserialize.
    :param field: The field instance to which the value belongs.
    :return: The deserialized value.
    """
    field_type = field.field_type
    if isinstance(field_type, collections.abc.Iterable):
        for arg in field_type:  # type: ignore
            arg = typing.cast(typing.Type[_T], arg)
            try:
                deserialized = arg(value)  # type: ignore[call-arg]
                return deserialized
            except (TypeError, ValueError):
                continue
        return value

    deserialized = field_type(value)  # type: ignore[call-arg]
    deserialized = typing.cast(_T, deserialized)
    return deserialized


@typing.final
@dataclass(frozen=True, slots=True)
class Value(typing.Generic[_T]):
    """
    Wrapper for field values.
    """

    wrapped: typing.Union[_T, typing.Any]
    is_valid: typing.Literal[0, 1] = 0

    def __bool__(self) -> bool:
        return bool(self.wrapped and self.is_valid)

    def __hash__(self) -> int:
        return hash((self.wrapped, self.is_valid))


def Factory(
    factory: typing.Callable[P, R],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> typing.Callable[[], R]:
    """
    Factory function to create a callable that invokes the provided factory with the given arguments.

    :param factory: The factory function to invoke.
    :param args: Additional arguments to pass to the factory function.
    :param kwargs: Additional keyword arguments to pass to the factory function.
    :return: A callable that, when invoked, calls the factory with the provided arguments.
    """

    def factory_func() -> R:
        nonlocal factory
        return factory(*args, **kwargs)

    return factory_func


class FieldMeta(type):
    def __init__(cls, name, bases, attrs) -> NoneType:
        default_serializers = getattr(cls, "default_serializers", {})
        cls.default_serializers = {
            **DEFAULT_FIELD_SERIALIZERS,
            **default_serializers,
        }


class Field(typing.Generic[_T], metaclass=FieldMeta):
    """
    Attribute descriptor.

    Implements the `TypeAdapter` protocol.
    """

    default_serializers: typing.ClassVar[typing.Mapping[str, FieldSerializer]] = {}
    default_deserializer: typing.ClassVar[FieldDeserializer] = default_deserializer
    default_validator: typing.Optional[Validator[_T]] = None

    def __init__(
        self,
        field_type: FieldType[_T],
        default: typing.Union[_T, DefaultFactory[_T], NoneType] = EMPTY,
        lazy: bool = False,
        alias: typing.Optional[str] = None,
        allow_null: bool = False,
        required: bool = False,
        strict: bool = False,
        validator: typing.Optional[Validator[_T]] = None,
        serializers: typing.Optional[
            typing.Mapping[str, "FieldSerializer[_T, Self]"]
        ] = None,
        deserializer: typing.Optional["FieldDeserializer[Self, _T]"] = None,
        _cache_size: Annotated[
            float, annot.Interval(ge=0.5, le=3.0), annot.MultipleOf(0.5)
        ] = 1.0,
    ) -> None:
        """
        Initialize the field.

        :param field_type: The expected type for field values.
        :param default: A default value for the field to be used if no value is set, defaults to empty.
        :param lazy: If True, the field will not be validated until it is accessed.
        :param alias: Optional string for alternative field naming, defaults to None.
        :param allow_null: If True, permits the field to be set to None, defaults to False.
        :param required: If True, field values must be explicitly provided, defaults to False.
        :param strict: If True, the field will only accept values of the specified type and will not attempt to coerce them.
            Defaults to False. This may speed up validation for large data sets.
        :param validator: A validation function to apply to the field's value, defaults to None.
            NOTE: The validator should be a callable that accepts the field value and the optional field instance as arguments.
            Values returned from the validator are not used, but it should raise a FieldError if the value is invalid.
        :param serializers: A mapping of serialization formats to their respective serializer functions, defaults to None.
        :param deserializer: A deserializer function to convert the field's value to the expected type, defaults to None.
        :param _cache_size: Multiplier for the base cache size for serialized and validated values, defaults to 1.
            Base cache size is 128, so the effective cache size will be 128 * _cache_size.
        """
        assert 0.5 <= _cache_size <= 3.0, "Cache size must be between 1 and 3"

        if isinstance(field_type, str):
            self.field_type = typing.ForwardRef(field_type)
        elif is_generic_type(field_type):
            self.field_type = typing.cast(
                NonForwardRefFieldType[_T],
                typing.get_origin(field_type),
            )
        else:
            self.field_type = field_type

        self.lazy = lazy
        self.name = None
        self.alias = alias
        self.allow_null = allow_null
        self.required = required
        self.strict = strict
        _validator = validator or type(self).default_validator
        self.validator = field_validators.load(_validator)[0] if _validator else None
        serializers_map = {
            **self.default_serializers,
            **(serializers or {}),
        }
        self.serializer = SerializerRegistry(
            defaultdict(
                _unsupported_serializer_factory,
                serializers_map,
            )
        )
        self.deserializer = deserializer or type(self).default_deserializer
        self.default = default
        self._init_args = ()
        self._init_kwargs = {}
        effective_cache_size = int(128 * _cache_size)
        self._serialized_cache = _LRUCache(maxsize=effective_cache_size)
        self._validated_cache = _LRUCache(maxsize=effective_cache_size)

    def post_init_validate(self) -> None:
        """
        Validate the field after initialization.

        This method is called after the field is initialized,
        usually by the dataclass it is defined in, to perform additional validation
        to ensure that the field is correctly configured.

        Avoid modifying the field's state in this method.
        """
        if not is_valid_type(self.field_type):
            raise TypeError(f"Specified type '{self.field_type}' is not a valid type.")

        default_provided = self.default is not EMPTY
        if self.required and default_provided:
            raise FieldError("A default value is not necessary when required=True")

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance._init_args = args
        instance._init_kwargs = kwargs
        return instance

    @functools.cached_property
    def effective_name(self) -> typing.Optional[str]:
        """
        Return the effective name of the field.

        This is either the alias (if provided) or the name of the field.
        """
        return self.alias or self.name

    def get_default(self) -> typing.Union[_T, NoneType]:
        """Return the default value for the field."""
        default_value = self.default
        if default_value is EMPTY:
            return EMPTY  # type: ignore[return-value]

        if callable(default_value):
            try:
                return default_value()  # type: ignore[call-arg]
            except Exception as exc:
                raise FieldError(
                    f"An error occurred while calling the default factory for '{self.effective_name}'."
                ) from exc
        return default_value

    def bind(self, parent: typing.Type[typing.Any], name: str) -> None:
        """
        Called when the field is bound to a parent class.

        Things like assigning the field name, and performing any necessary validation
        on the class (parent) it is bound to.
        :param parent: The parent class to which the field is bound.
        :param name: The name of the field.
        """
        self.name = name
        self.field_type = typing.cast(
            NonForwardRefFieldType[_T],
            resolve_type(
                self.field_type,
                globalns=globals(),
                localns={
                    parent.__name__: parent,
                    "Self": parent,
                    "self": parent,
                },
            ),
        )

    def __set_name__(self, owner: typing.Type[typing.Any], name: str):
        """Assign the field name when the descriptor is initialized on the class."""
        self.bind(owner, name)

    def __delete__(self, instance: typing.Any):
        self.delete_value(instance)

    @typing.overload
    def __get__(
        self,
        instance: typing.Any,
        owner: typing.Optional[typing.Type[typing.Any]],
    ) -> typing.Union[_T, typing.Any]: ...

    @typing.overload
    def __get__(
        self,
        instance: typing.Optional[typing.Any],
        owner: typing.Type[typing.Any],
    ) -> Self: ...

    def __get__(
        self,
        instance: typing.Optional[typing.Any],
        owner: typing.Optional[typing.Type[typing.Any]],
    ) -> typing.Optional[typing.Union[_T, Self]]:
        """Retrieve the field value from an instance or return the default if unset."""
        if instance is None:
            return self

        field_value = self.get_value(instance)
        if not field_value.is_valid:
            # with self._lock:
            return self.set_value(instance, field_value.wrapped, True).wrapped
        return field_value.wrapped

    def __set__(self, instance: typing.Any, value: typing.Any):
        """Set and validate the field value on an instance."""
        if self.required and value is EMPTY:
            raise FieldError(
                f"'{type(instance).__name__}.{self.effective_name}' is a required field."
            )

        # with self._lock:
        cache_key = get_cache_key(value)
        if cache_key in self._serialized_cache:
            del self._serialized_cache[cache_key]
        self.set_value(instance, value, not self.lazy)

    def get_value(self, instance: typing.Any) -> Value[_T]:
        """
        Get the field value from an instance.

        :param instance: The instance to which the field belongs.
        :param name: The name of the field.
        :return: The field value gotten from the instance.
        """
        field_name = self.name
        if not field_name:
            raise FieldError(
                f"'{type(self).__name__}' on '{type(instance).__name__}' has no name. Ensure it is bound to a class."
            )

        if hasattr(instance, "__dict__"):
            return instance.__dict__[field_name]
        # For slotted classes
        slotted_name = instance.__slotted_names__[field_name]
        return object.__getattribute__(instance, slotted_name)

    def set_value(
        self,
        instance: typing.Any,
        value: typing.Any,
        validate: bool = True,
    ) -> Value[_T]:
        """
        Set the field's value on an instance, performing validation if required.

        :param instance: The instance to which the field belongs.
        :param value: The field value to set.
        :param validate: If True, validate the value before setting it.
        :return: The set field value.
        """
        field_name = self.name
        if not field_name:
            raise FieldError(
                f"'{type(self).__name__}' on '{type(instance).__name__}' has no name. Ensure it is bound to a class."
            )

        if value is EMPTY:
            field_value = Value(EMPTY, is_valid=1)
        elif validate:
            field_value = Value(
                self.validate(value, instance),
                is_valid=1,
            )
        else:
            field_value = Value(value)

        # Store directly in __dict__ to avoid recursion
        if hasattr(instance, "__dict__"):
            instance.__dict__[field_name] = field_value
        else:  # For slotted classes
            slotted_name = instance.__slotted_names__[field_name]
            object.__setattr__(instance, slotted_name, field_value)
        return field_value

    def delete_value(self, instance: typing.Any) -> None:
        """
        Delete the field's value from an instance.

        :param instance: The instance to which the field belongs.
        """
        field_name = self.name
        if not field_name:
            raise FieldError(
                f"'{type(self).__name__}' on '{type(instance).__name__}' has no name. Ensure it is bound to a class."
            )

        if hasattr(instance, "__dict__"):
            del instance.__dict__[field_name]
        else:  # For slotted classes
            slotted_name = instance.__slotted_names__[field_name]
            object.__delattr__(instance, slotted_name)

    def check_type(self, value: typing.Any) -> typing.TypeGuard[_T]:
        """Check if the value is of the expected type."""
        if self.field_type is AnyType:
            return True
        if value is None and self.allow_null:
            return True

        # field_type = typing.cast(NonForwardRefFieldType[_T], self.field_type) # Adds additional overhead since the method is called often
        return isinstance(value, self.field_type)  # type: ignore[arg-type]

    def validate(
        self,
        value: typing.Any,
        instance: typing.Optional[typing.Any],
    ) -> typing.Union[_T, typing.Any]:
        """
        Casts the value to the field's type, validates it, and runs any field validators.

        Override/extend this method to add custom validation logic.

        :param value: The value to validate.
        :param instance: The instance to which the field belongs.
        """
        if value is None and self.allow_null:
            return None

        cache_key = get_cache_key(value)
        if cache_key in self._validated_cache:
            return self._validated_cache[cache_key]

        if self.check_type(value):
            deserialized = value
        elif self.strict:
            raise ValidationError(
                f"'{type(self).__name__}', {self.effective_name!r} expected type '{self.field_type}', but got '{type(value)}'.",
            )
        else:
            deserialized = self.deserialize(value)
            if not self.check_type(deserialized):
                raise ValidationError(
                    f"'{type(self).__name__}', {self.effective_name!r} expected type '{self.field_type}', but got '{type(deserialized)}'.",
                )

        if self.validator:
            self.validator(deserialized, self, instance)

        # with self._lock:
        self._validated_cache[cache_key] = deserialized
        return deserialized

    def serialize(
        self,
        value: _T,
        fmt: str,
        context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> typing.Optional[typing.Any]:
        """
        Serialize the given value to the specified format using the field's serializer.

        :param value: The value to serialize.
        :param fmt: The serialization format.
        :param context: Additional context for serialization.
        """
        if value is None:
            return None

        cache_key = get_cache_key(value)
        if cache_key in self._serialized_cache:
            return self._serialized_cache[cache_key]

        try:
            serialiazed = self.serializer(fmt, value, self, context)
        except (ValueError, TypeError) as exc:
            raise SerializationError(
                f"Failed to serialize '{type(self).__name__}', {self.effective_name} to '{fmt}'.",
            ) from exc

        if serialiazed is not None:
            # with self._lock:
            self._serialized_cache[cache_key] = serialiazed
        return serialiazed

    def deserialize(self, value: typing.Any) -> _T:
        """
        Cast the value to the field's specified type, if necessary.

        Converts the field's value to the specified type before it is set on the instance.
        """
        field_type = typing.cast(
            typing.Union[typing.Type[_T], typing.Tuple[typing.Type[_T]]],
            self.field_type,
        )
        try:
            return self.deserializer(value, self)
        except (ValueError, TypeError) as exc:
            raise DeserializationError(
                f"Failed to deserialize value, '{value}' for {self.effective_name} to type '{field_type}'.",
            ) from exc

    COPY_EXCLUDED_ARGS: typing.Set[int] = {0}
    """
    Indices of arguments that should not be copied when copying the field.

    This is useful for arguments that are immutable or should not be copied to avoid shared state.
    """
    COPY_EXCLUDED_KWARGS: typing.Set[str] = {
        "alias",
        "lazy",
        "allow_null",
        "required",
        "validators",
        "serializers",
        "deserializer",
        "default",
        "field_type",
    }
    """
    Names of keyword arguments that should not be copied when copying the field.

    This is useful for arguments that are immutable or should not be copied to avoid shared state.
    """

    def __copy__(self):
        args = [
            (copy.copy(arg) if index not in self.COPY_EXCLUDED_ARGS else arg)
            for index, arg in enumerate(self._init_args)
        ]
        kwargs = {
            key: (copy.copy(value) if value not in self.COPY_EXCLUDED_KWARGS else value)
            for key, value in self._init_kwargs.items()
        }
        field_copy = self.__class__(*args, **kwargs)
        field_copy.name = self.name
        return field_copy


_Field_co = typing.TypeVar("_Field_co", bound=Field, covariant=True)


class FieldInitKwargs(typing.TypedDict, total=False):
    """Possible keyword arguments for initializing a field."""

    alias: typing.Optional[str]
    """Optional string for alternative field naming."""
    lazy: bool
    """If True, the field will not be validated until it is accessed."""
    allow_null: bool
    """If True, permits the field to be set to None."""
    required: bool
    """If True, the field must be explicitly provided."""
    strict: bool
    """
    If True, the field will only accept values of the specified type,
    and will not attempt to coerce them.
    """
    validator: typing.Optional[Validator]
    """A validation function to apply to the field's value."""
    serializers: typing.Optional[typing.Dict[str, FieldSerializer]]
    """A mapping of serialization formats to their respective serializer functions."""
    deserializer: typing.Optional[FieldDeserializer]
    """A deserializer function to convert the field's value to the expected type."""
    default: typing.Union[typing.Any, DefaultFactory, NoneType]
    """A default value for the field to be used if no value is set."""
    _cache_size: Annotated[int, annot.Interval(ge=1, le=3), annot.MultipleOf(1)]


class Any(Field[typing.Any]):
    """Field for handling values of any type."""

    def __init__(self, **kwargs: Unpack[FieldInitKwargs]):
        kwargs.setdefault("allow_null", True)
        super().__init__(field_type=AnyType, **kwargs)


def boolean_deserializer(value: typing.Any, field: "Boolean") -> bool:
    if value in field.TRUTHY_VALUES:
        return True
    if value in field.FALSY_VALUES:
        return False
    return bool(value)


def boolean_json_serializer(
    value: bool,
    field: "Boolean",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> bool:
    """Serialize a boolean value to JSON."""
    return value


class Boolean(Field[bool]):
    """Field for handling boolean values."""

    TRUTHY_VALUES: typing.ClassVar[typing.Set[typing.Any]] = {
        True,
        1,
        "1",
        iexact("true"),
        iexact("yes"),
    }
    FALSY_VALUES: typing.ClassVar[
        typing.Set[typing.Any]
    ] = {  # Use sets for faster lookups
        False,
        0,
        "0",
        iexact("false"),
        iexact("no"),
        iexact("nil"),
        iexact("null"),
        iexact("none"),
    }
    default_deserializer = boolean_deserializer
    default_serializers = {
        "json": boolean_json_serializer,
    }

    def __init__(self, **kwargs: Unpack[FieldInitKwargs]):
        kwargs.setdefault("allow_null", True)
        super().__init__(field_type=bool, **kwargs)


def build_min_max_value_validators(
    min_value: typing.Optional[SupportsRichComparison],
    max_value: typing.Optional[SupportsRichComparison],
) -> typing.List[Validator[typing.Any]]:
    """Construct min and max value ."""
    if min_value is None and max_value is None:
        return []
    if min_value is not None and max_value is not None and min_value >= max_value:
        raise ValueError("min_value must be less than max_value")

    validators = []
    if min_value is not None:
        validators.append(field_validators.gte(min_value))
    if max_value is not None:
        validators.append(field_validators.lte(max_value))
    return validators


class Float(Field[float]):
    """Field for handling float values."""

    def __init__(
        self,
        *,
        min_value: typing.Optional[float] = None,
        max_value: typing.Optional[float] = None,
        **kwargs: Unpack[FieldInitKwargs],
    ):
        validators = list(
            filter(
                None,
                [
                    kwargs.get("validator", None),
                    *build_min_max_value_validators(min_value, max_value),
                ],
            )
        )
        if validators:
            kwargs["validator"] = field_validators.pipe(
                *validators,
            )
        super().__init__(
            field_type=float,
            **kwargs,
        )


def integer_deserializer(
    value: typing.Any,
    field: "Integer",
) -> int:
    """
    Deserialize a value to an integer.

    :param field: The field instance to which the value belongs.
    :param value: The value to deserialize.
    :return: The deserialized integer value.
    """
    return int(value, base=field.base)


class Integer(Field[int]):
    """Field for handling integer values."""

    default_deserializer = integer_deserializer

    def __init__(
        self,
        *,
        min_value: typing.Optional[int] = None,
        max_value: typing.Optional[int] = None,
        base: Annotated[int, annot.Interval(ge=2, le=36)] = 10,
        **kwargs: Unpack[FieldInitKwargs],
    ):
        validators = list(
            filter(
                None,
                [
                    kwargs.get("validator", None),
                    *build_min_max_value_validators(min_value, max_value),
                ],
            )
        )
        if validators:
            kwargs["validator"] = field_validators.pipe(*validators)
        super().__init__(
            field_type=int,
            **kwargs,
        )
        self.base = base

    def post_init_validate(self) -> None:
        super().post_init_validate()
        if not (2 <= self.base <= 36):
            raise FieldError(
                f"Base {self.base} is not supported. Must be between 2 and 36."
            )


def build_min_max_length_validators(
    min_length: typing.Optional[int],
    max_length: typing.Optional[int],
) -> typing.List[Validator[typing.Any]]:
    """Construct min and max length validators."""
    if min_length is None and max_length is None:
        return []
    if min_length is not None and max_length is not None and min_length <= max_length:
        raise ValueError("min_length cannot be greater than max_length")

    validators = []
    if min_length is not None:
        validators.append(field_validators.min_length(min_length))
    if max_length is not None:
        validators.append(field_validators.max_length(max_length))
    return validators


class String(Field[str]):
    """Field for handling string values."""

    default_min_length: typing.ClassVar[typing.Optional[int]] = None
    """Default minimum length of values."""
    default_max_length: typing.ClassVar[typing.Optional[int]] = None
    """Default maximum length of values."""

    default_serializers = {
        "json": to_string_serializer,
    }

    def __init__(
        self,
        *,
        min_length: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        max_length: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        trim_whitespaces: bool = True,
        to_lowercase: bool = False,
        to_uppercase: bool = False,
        **kwargs: Unpack[FieldInitKwargs],
    ) -> None:
        """
        Initialize the field.

        :param min_length: The minimum length allowed for the field's value.
        :param max_length: The maximum length allowed for the field's value.
        :param trim_whitespaces: If True, leading and trailing whitespaces will be removed.
        :param kwargs: Additional keyword arguments for the field.
        """
        validators = list(
            filter(
                None,
                [
                    kwargs.get("validator", None),
                    *build_min_max_length_validators(min_length, max_length),
                ],
            )
        )
        if validators:
            kwargs["validator"] = field_validators.pipe(*validators)
        super().__init__(field_type=str, **kwargs)
        self.trim_whitespaces = trim_whitespaces
        self.to_lowercase = to_lowercase
        self.to_uppercase = to_uppercase

    def post_init_validate(self) -> None:
        super().post_init_validate()
        if self.to_lowercase and self.to_uppercase:
            raise FieldError("`to_lowercase` and `to_uppercase` cannot both be set.")

    def deserialize(self, value: typing.Any) -> str:
        deserialized = super().deserialize(value)
        if self.trim_whitespaces:
            deserialized = deserialized.strip()
        if self.to_lowercase:
            return deserialized.lower()
        if self.to_uppercase:
            return deserialized.upper()
        return deserialized


class Dict(Field[typing.Dict]):
    """Field for handling dictionary values."""

    def __init__(self, **kwargs: Unpack[FieldInitKwargs]):
        super().__init__(dict, **kwargs)


class UUID(Field[uuid.UUID]):
    """Field for handling UUID values."""

    default_serializers = {
        "json": to_string_serializer,
    }

    def __init__(self, **kwargs: Unpack[FieldInitKwargs]):
        super().__init__(field_type=uuid.UUID, **kwargs)


def iterable_python_serializer(
    value: IterType,
    field: "Iterable[IterType, _V]",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> IterType:
    """
    Serialize an iterable to a list of serialized values.

    :param value: The iterable to serialize.
    :param field: The field instance to which the iterable belongs.
    :param context: Additional context for serialization.
    :return: The serialized iterable.
    """
    field_type = field.field_type
    serialized = field_type.__new__(field_type)  # type: ignore

    for item in value:
        serialized_item = field.child.serialize(item, fmt="python", context=context)
        field.adder(serialized, serialized_item)
    return serialized


def iterable_json_serializer(
    value: IterType,
    field: "Iterable[IterType, _V]",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> typing.List[typing.Any]:
    """
    Serialize an iterable to JSON compatible format.

    :param value: The iterable to serialize.
    :param field: The field instance to which the iterable belongs.
    :param context: Additional context for serialization.
    :return: The serialized iterable.
    """
    return [field.child.serialize(item, fmt="json", context=context) for item in value]


def iterable_deserializer(
    value: typing.Any,
    field: "Iterable[IterType, _V]",
) -> IterType:
    """
    Deserialize an iterable value to the specified field type.

    :param value: The value to deserialize.
    :param field: The field instance to which the value belongs.
    :return: The deserialized value.
    """
    field_type = field.field_type
    field_type = typing.cast(typing.Type[IterType], field_type)
    deserialized = field_type.__new__(field_type)  # type: ignore

    for item in value:
        deserialized_item = field.child.deserialize(item)
        field.adder(deserialized, deserialized_item)
    return deserialized


def validate_iterable(
    value: IterType,
    field: typing.Optional["Iterable[IterType, _V]"] = None,
    instance: typing.Optional[typing.Any] = None,
) -> None:
    """
    Validate the elements of an iterable field.
    This function checks if the elements of the iterable are valid according to the child field's validation rules.
    :param value: The iterable value to validate.
    :param field: The field instance to which the iterable belongs.
    :param instance: The instance to which the field belongs.
    """
    if field is None:
        return
    for item in value:
        field.child.validate(item, instance)


class Iterable(typing.Generic[IterType, _V], Field[IterType]):
    """Base class for iterable fields."""

    default_serializers = {
        "python": iterable_python_serializer,
        "json": iterable_json_serializer,
    }
    default_deserializer = iterable_deserializer
    default_validator = validate_iterable  # type: ignore[assignment]

    def __init__(
        self,
        field_type: typing.Type[IterType],
        child: typing.Optional[Field[_V]] = None,
        *,
        size: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldInitKwargs],
    ) -> NoneType:
        """
        Initialize the field.

        :param field_type: The expected iterable type for the field.
        :param child: Optional field for validating elements in the field's value.
        :param size: Optional size constraint for the iterable.
        """
        if not is_iterable_type(field_type, exclude=(str, bytes)):
            raise TypeError(
                "Specified type must be an iterable type; excluding str or bytes."
            )

        validators = kwargs.get("validators", [])
        if size is not None:
            validators = list(
                filter(
                    None,
                    [
                        kwargs.get("validator", None),
                        field_validators.max_length(size),
                    ],
                )
            )
            if validators:
                kwargs["validator"] = field_validators.pipe(*validators)
        super().__init__(field_type=field_type, **kwargs)
        self.child = child or Any()
        self.adder = _get_itertype_adder(field_type)

    def bind(self, parent: typing.Type[typing.Any], name: str) -> NoneType:
        super().bind(parent, name)
        self.child.bind(parent, f"{name}.__child__")

    def post_init_validate(self):
        super().post_init_validate()
        if not isinstance(self.child, Field):
            raise TypeError(
                f"'child' must be a field instance , not {type(self.child).__name__}."
            )
        self.child.post_init_validate()

    def check_type(self, value: typing.Any) -> typing.TypeGuard[IterType]:
        if not super().check_type(value):
            return False

        if value and self.child.field_type is not AnyType:
            for item in value:
                if not self.child.check_type(item):
                    return False
        return True


class List(Iterable[typing.List[_V], _V]):
    """List field."""

    def __init__(
        self,
        child: typing.Optional[Field[_V]] = None,
        *,
        size: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldInitKwargs],
    ) -> NoneType:
        super().__init__(
            field_type=list,
            child=child,
            size=size,
            **kwargs,
        )


class Set(Iterable[typing.Set[_V], _V]):
    """Set field."""

    def __init__(
        self,
        child: typing.Optional[Field[_V]] = None,
        *,
        size: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldInitKwargs],
    ) -> NoneType:
        super().__init__(
            field_type=set,
            child=child,
            size=size,
            **kwargs,
        )


class Tuple(Iterable[typing.Tuple[_V], _V]):
    """Tuple field."""

    def __init__(
        self,
        child: typing.Optional[Field[_V]] = None,
        *,
        size: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldInitKwargs],
    ) -> NoneType:
        super().__init__(
            field_type=tuple,
            child=child,
            size=size,
            **kwargs,
        )


def get_quantizer(dp: int) -> decimal.Decimal:
    """Get the quantizer for the specified number of decimal places."""
    if dp < 0:
        raise ValueError("Decimal places (dp) must be a non-negative integer.")
    return decimal.Decimal(f"0.{'0' * (dp - 1)}1") if dp > 0 else decimal.Decimal("1")


class Decimal(Field[decimal.Decimal]):
    """Field for handling decimal values."""

    default_serializers = {
        "json": to_string_serializer,
    }

    def __init__(
        self,
        dp: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldInitKwargs],
    ):
        """
        Initialize the field.

        :param dp: The number of decimal places to round the field's value to.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(field_type=decimal.Decimal, **kwargs)
        if dp is not None and dp < 0:
            raise ValueError("Decimal places (dp) must be a non-negative integer.")
        self.dp = int(dp) if dp is not None else None
        self._quantizer = get_quantizer(self.dp) if self.dp is not None else None

    def deserialize(self, value) -> decimal.Decimal:
        deserialized = super().deserialize(value)
        if self.dp is not None:
            self._quantizer = typing.cast(decimal.Decimal, self._quantizer)
            return deserialized.quantize(self._quantizer)
        return deserialized


email_validator = field_validators.pattern(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    message="'{name}' must be a valid email address.",
)


class Email(String):
    """Field for handling email addresses."""

    default_validator = email_validator

    def __init__(
        self,
        *,
        min_length=None,
        max_length=None,
        trim_whitespaces=True,
        to_lowercase=True,  # Field prefers to store email values in lowercase
        to_uppercase=False,
        **kwargs,
    ):
        super().__init__(
            min_length=min_length,
            max_length=max_length,
            trim_whitespaces=trim_whitespaces,
            to_lowercase=to_lowercase,
            to_uppercase=to_uppercase,
            **kwargs,
        )


class Choice(Field[_T]):
    """Field with predefined choices for values."""

    @typing.overload
    def __init__(
        self,
        field_type: typing.Type[_T],
        *,
        choices: None = None,
        **kwargs: Unpack[FieldInitKwargs],
    ) -> None: ...

    @typing.overload
    def __init__(
        self,
        field_type: typing.Type[_T],
        *,
        choices: typing.Iterable[_T],
        **kwargs: Unpack[FieldInitKwargs],
    ) -> None: ...

    def __init__(
        self,
        field_type: typing.Type[_T],
        *,
        choices: typing.Optional[typing.Iterable[_T]] = None,
        **kwargs: Unpack[FieldInitKwargs],
    ) -> None:
        # Skip `in` check for Enum types since the value will always be an Enum member after deserialization
        if not choices and not issubclass(field_type, enum.Enum):
            raise ValueError(
                "Choices must be provided for the field. Use `choices` argument."
            )

        if choices:
            validators = list(
                filter(
                    None,
                    [
                        kwargs.get("validator", None),
                        field_validators.in_(choices),
                    ],
                )
            )
            if validators:
                kwargs["validator"] = field_validators.pipe(
                    *validators,
                )
        super().__init__(field_type=field_type, **kwargs)


def json_serializer(
    value: typing.Any,
    field: "JSON",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> typing.Any:
    """Serialize JSON data to a JSON-compatible format."""
    # Return value as is, since it is already been made JSON-compatible
    # by the deserializer.
    return value


def json_deserializer(value: typing.Any, field: Field) -> typing.Any:
    """Deserialize JSON data to the specified type."""
    return make_jsonable(value)


class JSON(Any):
    """Field for handling JSON data."""

    default_serializers = {
        "json": json_serializer,
    }
    default_deserializer = json_deserializer


slug_validator = field_validators.pattern(
    r"^[a-zA-Z0-9_-]+$",
    message="'{name}' must be a valid slug.",
)


class Slug(String):
    """Field for URL-friendly strings."""

    default_min_length = 1
    default_validator = slug_validator


def bytes_serializer(
    value: bytes,
    field: "Bytes",
    context: typing.Optional[typing.Dict[str, typing.Any]],
) -> str:
    """Serialize bytes to a string."""
    return base64.b64encode(value).decode(encoding=field.encoding)


def bytes_deserializer(
    value: typing.Any,
    field: "Bytes",
) -> bytes:
    """Deserialize an object or base64-encoded string to bytes."""
    if isinstance(value, str):
        try:
            return base64.b64decode(value.encode(encoding=field.encoding))
        except (ValueError, TypeError) as exc:
            raise DeserializationError(
                f"Invalid base64 string for bytes: {value!r}"
            ) from exc
    return bytes(value)


class Bytes(Field[bytes]):
    """Field for handling byte types or base64-encoded strings."""

    default_serializers = {
        "json": bytes_serializer,
    }
    default_deserializer = bytes_deserializer

    def __init__(
        self, encoding: str = "utf-8", **kwargs: Unpack[FieldInitKwargs]
    ) -> NoneType:
        """
        Initialize the field.

        :param encoding: The encoding to use when encoding/decoding byte strings.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(field_type=bytes, **kwargs)
        self.encoding = encoding


IOType = typing.TypeVar("IOType", bound=io.IOBase)


class IOBase(Field[IOType]):
    """Base field for handling I/O objects."""

    default_serializers = {
        "json": unsupported_serializer,
    }
    default_deserializer = unsupported_deserializer  # type: ignore


def path_deserializer(
    value: typing.Any,
    field: "Path",
) -> pathlib.Path:
    """Deserialize a value to a `pathlib.Path` object."""
    if field.resolve:
        return pathlib.Path(value).resolve(strict=False)
    return pathlib.Path(value)


class Path(Field[pathlib.Path]):
    """
    Field for handling file system paths using `pathlib.Path`.

    By default, the field will resolve the path to an absolute path.
    """

    default_serializers = {
        "json": to_string_serializer,
    }
    default_deserializer = path_deserializer

    def __init__(
        self,
        resolve: bool = False,
        **kwargs: Unpack[FieldInitKwargs],
    ):
        super().__init__(field_type=pathlib.Path, **kwargs)
        self.resolve = resolve
