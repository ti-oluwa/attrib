"""Attribute descriptors"""

import enum
import inspect
import uuid
import decimal
import typing
import base64
import io
import pathlib
from typing_extensions import Unpack, Self, Annotated, TypeAlias, TypeGuard
import annotated_types as annot
import collections.abc

from attrib import validators as field_validators
from attrib.exceptions import (
    ConfigurationError,
    FieldError,
    InvalidTypeError,
    SerializationError,
    DeserializationError,
    ValidationError,
)
from attrib._utils import (
    iexact,
    is_iterable,
    is_valid_type,
    is_iterable_type,
    make_jsonable,
    resolve_type,
    SerializerMap,
)
from attrib.types import (
    P,
    R,
    T,
    V,
    JSONValue,
    RealNumberT,
    SupportsRichComparison,
    Validator,
    IterT,
    EMPTY,
    Empty,
    Context,
)

__all__ = [
    "AnyType",
    "FieldError",
    "Field",
    "Factory",
    "FieldKwargs",
    "Any",
    "Boolean",
    "String",
    "RealNumber",
    "Float",
    "Integer",
    "Decimal",
    "Dict",
    "Iterable",
    "List",
    "Set",
    "FrozenSet",
    "Tuple",
    "Deque",
    "Email",
    "Choice",
    "JSON",
    "Slug",
    "Bytes",
    "IOBase",
    "Path",
]


@typing.final
class AnyType:
    """Type representing any type."""

    def __init_subclass__(cls):
        raise TypeError("AnyType cannot be subclassed.")

    def __new__(cls):
        raise TypeError("AnyType cannot be instantiated.")

    def __instancecheck__(self, instance: typing.Any) -> bool:
        return True

    def __subclasscheck__(self, subclass: typing.Type[typing.Any]) -> bool:
        return True


NonTupleFieldType: TypeAlias = typing.Union[
    str,
    typing.Type[T],
    typing.Type[AnyType],
    typing.ForwardRef,
]
FieldType: TypeAlias = typing.Union[
    NonTupleFieldType[T],
    typing.Tuple[typing.Union[typing.ForwardRef, typing.Type[T]], ...],
]
NonForwardRefFieldType: TypeAlias = typing.Union[
    typing.Type[T],
    typing.Type[AnyType],
    typing.Tuple[typing.Type[T], ...],
]

DefaultFactory = typing.Callable[[], typing.Union[T, typing.Any]]
"""Type alias for default value factories."""
FieldSerializer: TypeAlias = typing.Callable[[T, "FieldTco", Context], typing.Any]
"""
Type alias for serializers.

Takes three arguments - the value, the field instance, and serialization context, and returns the serialized value.
Should raise a SerializationError if serialization fails.
"""
FieldDeserializer: TypeAlias = typing.Callable[[typing.Any, "FieldTco"], T]
"""
Type alias for deserializers.

Takes two arguments - the value to deserialize, and the field instance.
Returns the deserialized value.
Should raise a DeserializationError if deserialization fails.
"""


def json_serializer(
    value: typing.Any, field: "Field[typing.Any]", context: Context
) -> JSONValue:
    return make_jsonable(value)


def string_serializer(
    value: typing.Any, field: "Field[typing.Any]", context: Context
) -> str:
    """Serialize a value to a string."""
    return str(value)


def unsupported_serializer(
    value: typing.Any, field: "Field[typing.Any]", context: Context
) -> None:
    """Raise an error for unsupported serialization."""
    raise SerializationError(
        "Unsupported serialization format.",
        input_type=type(value),
        expected_type=field.typestr,
        code="unsupported_serialization_format",
        location=[field.name],
        context={
            "serialization_formats": list(field.serializers),
        },
    )


def _unsupported_serializer_factory():
    """
    Return a function that raises an error for unsupported serialization.

    To be used in defaultdict for field serializer instantiation
    """
    return unsupported_serializer


def unsupported_deserializer(value: typing.Any, field: "Field[typing.Any]") -> None:
    """Raise an error for unsupported deserialization."""
    raise DeserializationError(
        "Cannot deserialize value.",
        input_type=type(value),
        expected_type=field.typestr,
        location=[field.name],
        code="coercion_not_supported",
    )


def no_op_serializer(value: T, field: "Field[typing.Any]", context: Context) -> T:
    """Serialize a value to Python object."""
    return value


DEFAULT_SERIALIZERS: typing.Dict[str, FieldSerializer] = {
    "json": json_serializer,
    "python": no_op_serializer,
}


def default_deserializer(
    value: typing.Any,
    field: "Field[T]",
) -> typing.Union[T, typing.Any]:
    """
    Deserialize a value to the specified field type.

    :param value: The value to deserialize.
    :param field: The field instance to which the value belongs.
    :return: The deserialized value.
    """
    field_type = field.field_type
    if isinstance(field_type, collections.abc.Iterable):
        for arg in field_type:  # type: ignore
            try:
                deserialized = arg(value)  # type: ignore[call-arg,operator]
                return deserialized
            except (TypeError, ValueError):
                continue
        raise DeserializationError(
            "Failed to deserialize value to any of the type arguments.",
            input_type=type(value),
            expected_type=field.typestr,
            location=[field.name],
        )
    deserialized = field_type(value)  # type: ignore[call-arg,operator]
    return deserialized


@typing.final
class Value(typing.NamedTuple):
    """
    Wrapper for field values.
    """

    wrapped: typing.Any
    is_valid: bool = False

    def __bool__(self) -> bool:
        return bool(self.wrapped and self.is_valid)


def Factory(
    factory: typing.Callable[P, R],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> typing.Callable[[], R]:
    """
    Creates a callable that invokes the provided factory with the given arguments.

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
    def __init__(cls, name, bases, attrs) -> None:
        defined_default_serializers = getattr(cls, "default_serializers", None)
        if defined_default_serializers is not None:
            cls.default_serializers = {
                **DEFAULT_SERIALIZERS,
                **defined_default_serializers,
            }


class Field(typing.Generic[T], metaclass=FieldMeta):
    """
    Attribute descriptor.

    Implements the `TypeAdapter` protocol.
    """

    default_serializers: typing.ClassVar[typing.Mapping[str, FieldSerializer]] = {}
    """Default serializers for the field, if any."""
    default_deserializer: typing.ClassVar[FieldDeserializer] = default_deserializer
    """Default deserializer for the field, if any."""
    default_validator: typing.Optional[Validator[T]] = None
    """Default validator for the field, if any."""

    def __init__(
        self,
        field_type: FieldType[T],
        default: typing.Union[T, DefaultFactory[T], Empty, None] = EMPTY,
        lazy: bool = False,
        alias: typing.Optional[str] = None,
        serialization_alias: typing.Optional[str] = None,
        allow_null: bool = False,
        required: bool = False,
        strict: bool = False,
        validator: typing.Optional[Validator[T]] = None,
        serializers: typing.Optional[
            typing.Mapping[str, "FieldSerializer[T, Self]"]
        ] = None,
        deserializer: typing.Optional["FieldDeserializer[Self, T]"] = None,
        always_coerce: bool = False,
        check_coerced: bool = False,
        skip_validator: bool = False,
        validate_default: bool = False,
        fail_fast: bool = False,
        hash: bool = True,
        repr: bool = True,
        eq: bool = True,
        init: bool = True,
        order: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
    ) -> None:
        """
        Initialize the field.

        :param field_type: The expected type for field values.
        :param default: A default value for the field to be used if no value is set. Defaults to `EMPTY`.
        :param lazy: If True, the field value will not be coerced and/or validated until it is accessed.
        :param alias: Optional alias for the field, used for mainly for deserialization but can also be used for serialization.
        :param serialization_alias: Optional alias for the field used during serialization.
        :param allow_null: If True, permits the field to be set to None. Defaults to False.
        :param required: If True, field values must be explicitly provided. Defaults to False.
        :param strict: If True, the field will only accept values of the specified type and will not attempt to coerce them.
            Defaults to False. This may speed up validation for large data sets.

        :param validator: A validation function to apply to the field's value, defaults to None.
            NOTE: The validator should be a callable that accepts the field value and the optional field instance as arguments.
            Values returned from the validator are not used, but it should raise a FieldError if the value is invalid.

        :param serializers: A mapping of serialization formats to their respective serializer functions. Defaults to None.
        :param deserializer: A deserializer function to convert the field's value to the expected type. Defaults to None.
        :param always_coerce: If True, the field will always attempt to coerce the value by applying the deserializer
            to the specified type, even if the value is already of that type. Defaults to False.

        :param check_coerced: If True, the field will (double) check that the value returned by the deserializer is of the expected type.
            If the value is not of the expected type, a ValidationError will be raised. Defaults to False.
            Set to True if a custom deserializer is used and the return type cannot be guaranteed to match the field type.

        :param skip_validator: If True, the field will skip validator run after deserialization. Defaults to False.
        :param validate_default: If True, the field will check that the default value is valid before setting it. Defaults to False.
        :param fail_fast: If True, the field will raise an error immediately a validation fails. Defaults to False.
        :param hash: If True, the field will be included in the hash of the class it is defined in. Defaults to True.
        :param repr: If True, the field will be included in the repr of the class it is defined in. Defaults to True.
        :param eq: If True, the field will be compared for equality when comparing instances of the class it is defined in. Defaults to True.
        :param init: If True, the field will be included as an instantiation argument for the class it is defined in. Defaults to True.
        :param order: If set, the field will be included in the ordering of instances of the class it is defined in.
            The value must be a non-negative integer, where lower values indicate higher precedence in ordering.
            That is, a field with order=0 will be ordered/compared before a field with order=1.
        """
        if not isinstance(field_type, str):
            self.field_type = field_type
        else:
            self.field_type = typing.ForwardRef(field_type)

        self.lazy = lazy
        self.name: typing.Optional[str] = None
        self.alias = alias
        self.allow_null = allow_null
        self.required = required
        self.strict = strict
        _validator = validator or type(self).default_validator
        if allow_null and _validator is not None:
            _validator = field_validators.optional(_validator)
        self.validator = field_validators.load(_validator)[0] if _validator else None
        serializers_map = {
            **self.default_serializers,
            **(serializers or {}),
        }
        self.serializers = SerializerMap(
            serializers_map, default_factory=_unsupported_serializer_factory
        )
        self.deserializer = deserializer or type(self).default_deserializer
        self.default = default
        self.always_coerce = always_coerce
        self.check_coerced = check_coerced
        self.skip_validator = skip_validator
        self._check_default = validate_default
        self.fail_fast = fail_fast
        self.serialization_alias = serialization_alias
        self.effective_name = alias
        """The name of the field as it will be used in serialization/deserialization. Do not modify this directly."""
        self.hash = hash
        self.repr = repr
        self.eq = eq
        self.init = init
        self.order = order
        self._meta: typing.Dict[str, typing.Any] = {}
        """Meta information for the field, can be used to store additional data."""
        self._slotted_name: typing.Optional[str] = None
        """The name with which the field will be stored in the instance's __slots__."""
        # We precompute the identity formats here, so that we can use it later in `asdict` so
        # We do not need to call `Field.serialize` for formats that do not change the value.
        # This should reduce overhead in function calls, for serialization formats that do not change the value.
        # Especially for function used in hot paths like `Field.serialize`.
        self._identity_formats = {
            fmt for fmt, f in self.serializers.items() if f is no_op_serializer
        }
        """Set of serialization formats that will not change the value during serialization."""

    @property
    def typestr(self) -> str:
        """
        Return the string representation of the field type.

        This is useful for debugging and introspection.
        """
        value = getattr(self.field_type, "__name__", None) or str(self.field_type)
        if self.strict:
            return f"strict[{value}]"
        return value

    def post_init(self) -> None:
        """
        Validate the field after initialization.

        This method is called after the field is initialized,
        usually by the dataclass it is defined in, to perform additional validation
        to ensure that the field is correctly configured.

        Avoid modifying the field's state in this method.
        """
        if not is_valid_type(self.field_type):  # type: ignore
            raise FieldError(
                f"{self.field_type!r} is not a valid field type.", name=self.name
            )

        default_provided = self.default is not EMPTY
        if self.required and default_provided:
            raise FieldError(
                "A default value is not necessary when required=True", name=self.name
            )

        if self.strict and self.always_coerce:
            raise FieldError(
                "Cannot set both strict=True and always_coerce=True. "
                "If strict is True, the field will not attempt to coerce values.",
                name=self.name,
            )

    def __get_type_hint__(self):
        """Return type information for the field."""
        if not is_iterable(self.field_type):
            return self.field_type
        return typing.Union[self.field_type]

    def get_default(self) -> typing.Union[T, typing.Any, None]:
        """Return the default value for the field."""
        default_value = self.default
        if default_value is EMPTY or default_value is None:
            return default_value

        if callable(default_value):
            try:
                return default_value()
            except Exception as exc:
                raise FieldError(
                    "An error occurred while calling the default factory.",
                    name=self.name,
                ) from exc
        return default_value

    def set_default(self, instance: typing.Any) -> None:
        """
        Set the default value for the field on an instance.

        :param instance: The instance to which the field belongs.
        """
        # If `_check_default` is False, it means that the default value is (assumed) valid
        # and does not need to be validated. Hence, we can set the value to not be validated now (lazy=True),
        # and also set (is_lazy_valid=True), to confirm that the value is valid and should also not be validated later (on access).
        # However, these conditions only apply if the field is not configured to always coerce input (field.always_coerce == True).

        # If `_check_default` is True, it means that the default value needs to be validated.
        # In this case, we set the value to be validated now (lazy=False). However, if the field validates lazily (field.lazy == True).
        # Then we also need to ensure that the default value set respects that and is validated later.
        default_is_valid = not self._check_default and not self.always_coerce
        lazy_default = default_is_valid or self.lazy
        self._set_value(
            instance,
            self.get_default(),
            lazy=lazy_default,
            is_lazy_valid=default_is_valid,
        )
        # If we reach here, the value has been set and is valid.
        # Hence, we set `_check_default` to False, as there is no need to check it again.
        # In the case that the we have a default factory, we are making the assumption that the
        # factory will always return a valid value.
        self._check_default = False

        # Note that 'valid' here means that the value does not need to be coerced to the field type, and
        # does not need to be run through the validator.

    def bind(
        self, parent: typing.Type[typing.Any], name: typing.Optional[str] = None
    ) -> None:
        """
        Called when the field is bound to a parent class.

        Things like assigning the field name, and performing any necessary validation
        on the class (parent) it is bound to.
        :param parent: The parent class to which the field is bound.
        :param name: The name of the field.
        """
        if self.name is not None:
            raise ConfigurationError(
                f"Field '{self.name}' is already bound to a class. "
                "Ensure that the field is not bound multiple times.",
            )

        self.name = name
        self.effective_name = self.alias or name
        slotted_names = getattr(parent, "__slotted_names__", None)
        if slotted_names and name:
            self._slotted_name = slotted_names[name]

        parent_module = inspect.getmodule(parent)
        globalns = parent_module.__dict__ if parent_module else globals()
        self.build(
            globalns=globalns,
            localns={
                parent.__name__: parent,
                "Self": parent,
                "self": parent,
            },
        )

    def build(
        self,
        globalns: typing.Optional[typing.Dict[str, typing.Any]] = None,
        localns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> None:
        """
        Build the field type, resolving any forward references.

        :param globalns: Global namespace for resolving types.
        :param localns: Local namespace for resolving types.
        """
        self.field_type = typing.cast(
            NonForwardRefFieldType[T],
            resolve_type(
                self.field_type,
                globalns=globalns,
                localns=localns,
            ),
        )

    def __set_name__(self, owner: typing.Type[typing.Any], name: str):
        """Assign the field name when the descriptor is initialized on the class."""
        self.bind(owner, name)

    def __delete__(self, instance: typing.Any) -> None:
        if self._slotted_name:
            object.__delattr__(instance, self._slotted_name)
        else:
            del instance.__dict__[self.name]

    @typing.overload
    def __get__(
        self,
        instance: typing.Optional[typing.Any],
        owner: typing.Type[typing.Any],
    ) -> Self: ...

    @typing.overload
    def __get__(
        self,
        instance: typing.Any,
        owner: typing.Optional[typing.Type[typing.Any]],
    ) -> typing.Union[T, typing.Any]: ...

    def __get__(
        self,
        instance: typing.Optional[typing.Any],
        owner: typing.Optional[typing.Type[typing.Any]],
    ) -> typing.Optional[typing.Union[T, typing.Any, Self]]:
        """Retrieve the field value from an instance or return the default if unset."""
        if not instance:
            return self

        # Check if it is a slotted class first, just in case "__dict__" was added to __slots__.
        # If not, we may mistake it for a normal class and try to access the field's value from __dict__
        # which will raise an AttributeError.
        if self._slotted_name:
            field_value = object.__getattribute__(instance, self._slotted_name)
        else:
            field_value = instance.__dict__[self.name]

        if field_value.is_valid:
            return field_value.wrapped
        return self._set_value(instance, value=field_value.wrapped, lazy=False).wrapped

    def __set__(self, instance: typing.Any, value: typing.Any):
        """Set and validate the field value on an instance."""
        self._set_value(instance, value, lazy=self.lazy)
        field_set: typing.Set = instance.__fields_set__  # type: ignore[attr-defined]
        field_set.add(self.name)

    def _set_value(
        self,
        instance: typing.Any,
        value: typing.Any,
        lazy: bool = False,
        is_lazy_valid: bool = False,
    ) -> Value:
        """
        Set the field's value on an instance, performing validation if required.

        :param instance: The instance to which the field belongs.
        :param value: The field value to set.
        :param lazy: If True, the value is not coerced or validated. It is set as is.
        :param is_lazy_valid: The validity of the value when lazy is True
        :return: The set field value.
        """
        if self.required and value is EMPTY:
            raise ValidationError(
                "Value is required but not provided.",
                parent_name=type(instance).__name__ if instance else None,
                input_type=type(value),
                location=[self.name],
                expected_type=self.typestr,
                code="missing_value",
            )

        if value is EMPTY:
            field_value = Value(EMPTY, is_valid=True)
        elif lazy:
            field_value = Value(value, is_valid=is_lazy_valid)
        else:
            deserialized = self.deserialize(value, instance)
            self.validate(deserialized, instance)
            field_value = Value(deserialized, is_valid=True)

        # Check if it is a slotted class first, just in case "__dict__" was added to __slots__.
        # If not, we may mistake it for a normal class and then set the field's value in __dict__,
        # beating the purpose of using slots.
        if self._slotted_name:
            object.__setattr__(instance, self._slotted_name, field_value)
        else:
            # Store directly in __dict__ to avoid recursion
            instance.__dict__[self.name] = field_value
        return field_value

    def check_type(self, value: typing.Any) -> TypeGuard[T]:
        """Check if the value is of the expected type."""
        if self.field_type is AnyType or (self.allow_null and value is None):
            return True
        return isinstance(value, self.field_type)  # type: ignore[arg-type]

    def deserialize(
        self,
        value: typing.Union[T, typing.Any],
        instance: typing.Optional[typing.Any] = None,
    ) -> typing.Optional[T]:
        """
        Cast the value to the field's specified type, if necessary.

        Converts the field's value to the specified type before it is set on the instance.
        """
        if value is None and self.allow_null:
            return None

        if not self.always_coerce and self.check_type(value):
            return value
        elif self.strict:
            raise InvalidTypeError(
                "Input value is not of the expected type.",
                parent_name=type(instance).__name__ if instance else None,
                input_type=type(value),
                location=[self.name],
                expected_type=self.typestr,
                code="invalid_type",
            )
        try:
            deserialized = self.deserializer(value, self)
        except (ValueError, TypeError, DeserializationError) as exc:
            raise DeserializationError.from_exception(
                exc,
                message="Failed to deserialize value.",
                parent_name=type(instance).__name__ if instance else None,
                input_type=type(value),
                expected_type=self.typestr,
                location=[self.name],
            ) from exc

        if self.check_coerced and not self.check_type(deserialized):
            raise InvalidTypeError(
                "Coerced value is not of the expected type.",
                parent_name=type(instance).__name__ if instance else None,
                input_type=type(deserialized),
                expected_type=self.typestr,
                location=[self.name],
                code="invalid_type",
            )
        return deserialized

    def validate(
        self,
        value: typing.Union[T, typing.Any],
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Validates the field's value. Runs any field validators.

        Override/extend this method to add custom validation logic.

        :param value: The value to validate.
        :param instance: The instance to which the field belongs.
        """
        if self.skip_validator or self.validator is None:
            return
        try:
            self.validator(
                value,
                self,
                instance,
                fail_fast=self.fail_fast,
            )
        except (ValueError, ValidationError) as exc:
            raise ValidationError.from_exception(
                exc,
                parent_name=type(instance).__name__ if instance else None,
                input_type=type(value),
                expected_type=self.typestr,
                location=[self.name],
            ) from exc
        return None

    def serialize(
        self, value: typing.Union[T, typing.Any], fmt: str, context: Context
    ) -> typing.Optional[typing.Any]:
        """
        Serialize the given value to the specified format using the field's serializer.

        :param value: The value to serialize.
        :param fmt: The serialization format.
        :param context: Additional context for serialization.
        """
        # If the serializer for the format is the default no-Op Python serializer,
        # we return the value as is. The default serializer just returns the value as is,
        # calling it is extra overhead especially in hot paths.
        if (fmt_serializer := self.serializers[fmt]) is no_op_serializer:
            return value

        try:
            return fmt_serializer(value, self, context)
        except (ValueError, TypeError, SerializationError) as exc:
            raise SerializationError.from_exception(
                exc,
                input_type=type(value),
                expected_type=self.typestr,
                location=[self.name],
            ) from exc


FieldTco = typing.TypeVar("FieldTco", bound=Field, covariant=True)


class FieldKwargs(typing.TypedDict, total=False):
    """Possible keyword arguments for initializing a field."""

    alias: typing.Optional[str]
    """Optional alias for the field, used mainly for deserialization but can also be used for serialization."""
    serialization_alias: typing.Optional[str]
    """Optional alias for the field used during serialization."""
    lazy: bool
    """If True, the field will not be coerced and/or validated until it is accessed."""
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
    default: typing.Union[typing.Any, DefaultFactory, None]
    """A default value for the field to be used if no value is set."""
    always_coerce: bool
    """If True, the field will always attempt to coerce the value by applying the deserializer."""
    check_coerced: bool
    """
    If True, the field will (double) check that the value returned by the deserializer is of the expected type.
    If the value is not of the expected type, a ValidationError will be raised. Defaults to False.

    Set to True if a custom deserializer is used and the return type cannot be guaranteed to match the field type.
    """
    skip_validator: bool
    """If True, the field will skip validator run after deserialization."""
    validate_default: bool
    """If True, the field will check that the default value is valid before setting it."""
    fail_fast: bool
    """If True, the field will raise an error immediately a validation fails."""
    hash: bool
    """If True, the field will be included in the hash of the class it is defined in."""
    repr: bool
    """If True, the field will be included in the repr of the class it is defined in."""
    eq: bool
    """If True, the field will be compared for equality when comparing instances of the class it is defined in."""
    init: bool
    """If True, the field will be included as an instantiation argument for the class it is defined in."""
    order: typing.Optional[Annotated[int, annot.Ge(0)]]
    """
    If set, the field will be included in the ordering of instances of the class it is defined in.
    The value must be a non-negative integer, where lower values indicate higher precedence in ordering.
    That is, a field with order=0 will be ordered/compared before a field with order=1.
    """


class Any(Field[typing.Any]):
    """Field for handling values of any type."""

    def __init__(self, **kwargs: Unpack[FieldKwargs]):
        kwargs.setdefault("allow_null", True)
        super().__init__(field_type=AnyType, **kwargs)


def boolean_deserializer(value: typing.Any, field: "Boolean") -> bool:
    if value in field.TRUTHY_VALUES:
        return True
    if value in field.FALSY_VALUES:
        return False
    return bool(value)


class Boolean(Field[bool]):
    """Field for handling boolean values."""

    TRUTHY_VALUES: typing.ClassVar[typing.Set[typing.Any]] = {
        True,
        1,
        "1",
        iexact("true"),
        iexact("yes"),
    }
    FALSY_VALUES: typing.ClassVar[typing.Set[typing.Any]] = {
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
        "json": no_op_serializer,
    }

    def __init__(self, **kwargs: Unpack[FieldKwargs]) -> None:
        kwargs.setdefault("allow_null", True)
        super().__init__(field_type=bool, **kwargs)


def build_min_max_value_validators(
    min_value: typing.Optional[SupportsRichComparison],
    max_value: typing.Optional[SupportsRichComparison],
) -> typing.List[Validator[typing.Any]]:
    """Construct min and max value validators."""
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


class RealNumber(Field[RealNumberT]):
    """Field for handling real number values."""

    default_serializers = {
        "json": no_op_serializer,
    }

    def __init__(
        self,
        field_type: FieldType[RealNumberT],
        *,
        min_value: typing.Optional[RealNumberT] = None,
        max_value: typing.Optional[RealNumberT] = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
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
        super().__init__(field_type, **kwargs)


# For some reason, the type checker flags `float` as not being a valid subtype of `RealNumberT`.
class Float(RealNumber[float]):  # type: ignore[misc]
    """Field for handling float values."""

    def __init__(
        self,
        *,
        min_value: typing.Optional[float] = None,
        max_value: typing.Optional[float] = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        super().__init__(
            field_type=float, min_value=min_value, max_value=max_value, **kwargs
        )


def integer_deserializer(value: typing.Any, field: "Integer") -> int:
    """
    Deserialize a value to an integer.

    :param field: The field instance to which the value belongs.
    :param value: The value to deserialize.
    :return: The deserialized integer value.
    """
    return int(value, base=field.base)


class Integer(RealNumber[int]):  # type: ignore[misc]
    """Field for handling integer values."""

    default_deserializer = integer_deserializer

    def __init__(
        self,
        *,
        min_value: typing.Optional[int] = None,
        max_value: typing.Optional[int] = None,
        base: Annotated[int, annot.Interval(ge=2, le=36)] = 10,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        super().__init__(
            field_type=int, min_value=min_value, max_value=max_value, **kwargs
        )
        self.base = base

    def post_init(self) -> None:
        super().post_init()
        if not (2 <= self.base <= 36):
            raise FieldError(
                f"Base {self.base} is not supported. Must be between 2 and 36.",
                name=self.name,
            )


def get_quantizer(dp: int) -> decimal.Decimal:
    """Get the quantizer for the specified number of decimal places."""
    if dp < 0:
        raise ValueError("Decimal places (dp) must be a non-negative integer.")
    return decimal.Decimal(f"0.{'0' * (dp - 1)}1") if dp > 0 else decimal.Decimal("1")


class Decimal(RealNumber[decimal.Decimal]):  # type: ignore[misc]
    """Field for handling decimal values."""

    default_serializers = {
        "json": string_serializer,
    }

    def __init__(
        self,
        dp: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        min_value: typing.Optional[decimal.Decimal] = None,
        max_value: typing.Optional[decimal.Decimal] = None,
        **kwargs: Unpack[FieldKwargs],
    ):
        """
        Initialize the field.

        :param dp: The number of decimal places to round the field's value to.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(
            field_type=decimal.Decimal,
            min_value=min_value,
            max_value=max_value,
            **kwargs,
        )
        if dp is not None and dp < 0:
            raise ValueError("Decimal places (dp) must be a non-negative integer.")
        self.dp = int(dp) if dp is not None else None
        self._quantizer = get_quantizer(self.dp) if self.dp is not None else None

    def deserialize(
        self,
        value: typing.Union[T, typing.Any],
        instance: typing.Optional[typing.Any] = None,
    ) -> typing.Optional[decimal.Decimal]:
        deserialized = super().deserialize(value, instance)
        if deserialized and self.dp is not None:
            return deserialized.quantize(self._quantizer)  # type: ignore[return-value]
        return deserialized


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
        "json": string_serializer,
    }

    def __init__(
        self,
        *,
        min_length: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        max_length: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        trim_whitespaces: bool = True,
        to_lowercase: bool = False,
        to_uppercase: bool = False,
        **kwargs: Unpack[FieldKwargs],
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

    def post_init(self) -> None:
        super().post_init()
        if self.to_lowercase and self.to_uppercase:
            raise FieldError(
                "`to_lowercase` and `to_uppercase` cannot both be set to True.",
                name=self.name,
            )

    def deserialize(
        self,
        value: typing.Union[T, typing.Any],
        instance: typing.Optional[typing.Any] = None,
    ) -> typing.Optional[str]:
        deserialized = super().deserialize(value, instance)
        if not deserialized:
            return deserialized

        if self.trim_whitespaces:
            deserialized = deserialized.strip()

        if self.to_lowercase:
            return deserialized.lower()
        elif self.to_uppercase:
            return deserialized.upper()
        return deserialized


class Dict(Field[typing.Dict]):
    """Field for handling dictionary values."""

    def __init__(self, **kwargs: Unpack[FieldKwargs]):
        super().__init__(dict, **kwargs)


class UUID(Field[uuid.UUID]):
    """Field for handling UUID values."""

    default_serializers = {
        "json": string_serializer,
    }

    def __init__(self, **kwargs: Unpack[FieldKwargs]):
        super().__init__(field_type=uuid.UUID, **kwargs)


def iterable_python_serializer(
    value: typing.Iterable[V],
    field: "Iterable[typing.Iterable[V], V]",
    context: Context,
) -> typing.Iterable[typing.Any]:
    """
    Serialize an iterable to a list of serialized values.

    :param value: The iterable to serialize.
    :param field: The field instance to which the iterable belongs.
    :param context: Additional context for serialization.
    :return: The serialized iterable.
    """
    serialized = []
    child_field = field.child
    child_serializer = child_field.serialize
    fail_fast = field.fail_fast

    error = None
    for index, item in enumerate(value):
        if "python" in child_field._identity_formats:
            serialized.append(item)
            continue

        try:
            serialized_item = child_serializer(item, "python", context)
        except SerializationError as exc:
            child_typestr = child_field.typestr
            input_type = type(item)
            if fail_fast:
                raise SerializationError.from_exception(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                ) from exc
            if error is None:
                error = SerializationError.from_exception(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                )
                continue
            error.add(
                exc,
                input_type=input_type,
                expected_type=child_typestr,
                location=[index],
            )
            continue

        if error:
            raise error
        serialized.append(serialized_item)

    if error:
        raise error
    return serialized if field.field_type is list else field.field_type(serialized)  # type: ignore[return-value]


def iterable_json_serializer(
    value: typing.Iterable[V],
    field: "Iterable[typing.Iterable[V], V]",
    context: Context,
) -> typing.List[typing.Any]:
    """
    Serialize an iterable to JSON compatible format.

    :param value: The iterable to serialize.
    :param field: The field instance to which the iterable belongs.
    :param context: Additional context for serialization.
    :return: The serialized iterable.
    """
    serialized = []
    child_field = field.child
    child_serializer = child_field.serialize
    fail_fast = field.fail_fast

    error = None
    for index, item in enumerate(value):
        if "json" in child_field._identity_formats:
            serialized.append(item)
            continue

        try:
            serialized_item = child_serializer(item, "json", context)
        except SerializationError as exc:
            child_typestr = child_field.typestr
            input_type = type(item)
            if fail_fast:
                raise SerializationError.from_exception(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                ) from exc
            if error is None:
                error = SerializationError.from_exception(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                )
                continue
            error.add(
                exc,
                input_type=input_type,
                expected_type=child_typestr,
                location=[index],
            )
            continue

        if error:
            raise error
        serialized.append(serialized_item)

    if error:
        raise error
    return serialized


def iterable_deserializer(
    value: typing.Iterable[typing.Any], field: "Iterable[typing.Iterable[V], V]"
) -> typing.Iterable[V]:
    """
    Deserialize an iterable value to the specified field type.

    :param value: The value to deserialize.
    :param field: The field instance to which the value belongs.
    :return: The deserialized value.
    """
    deserialized = []
    child_field = field.child
    child_deserializer = child_field.deserialize
    fail_fast = field.fail_fast

    error = None
    for index, item in enumerate(value):
        try:
            deserialized_item = child_deserializer(item)
        except DeserializationError as exc:
            child_typestr = child_field.typestr
            input_type = type(item)
            if fail_fast:
                raise DeserializationError.from_exception(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                ) from exc
            if error is None:
                error = DeserializationError.from_exception(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                )
                continue
            error.add(
                exc,
                input_type=input_type,
                expected_type=child_typestr,
                location=[index],
            )
            continue

        if error:
            raise error
        deserialized.append(deserialized_item)

    if error:
        raise error
    return (
        deserialized if field.field_type is list else field.field_type(deserialized)  # type: ignore[return-value]
    )


def validate_iterable(
    value: typing.Iterable[V],
    field: typing.Optional["Iterable[typing.Iterable[V], V]"] = None,
    instance: typing.Optional[typing.Any] = None,
    *args: typing.Any,
    **kwargs: typing.Any,
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

    child_field = field.child
    child_validator = child_field.validate
    error = None
    fail_fast = field.fail_fast

    for index, item in enumerate(value):
        try:
            child_validator(item, instance)
        except ValidationError as exc:
            child_typestr = child_field.typestr
            input_type = type(item)
            if fail_fast:
                raise ValidationError.from_exception(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                ) from exc
            if error is None:
                error = ValidationError.from_exception(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                )
                continue
            error.add(
                exc,
                input_type=input_type,
                expected_type=child_typestr,
                location=[index],
            )

    if error:
        raise error


_GENERIC_ITER_MAP: typing.Dict[typing.Type[typing.Iterable[typing.Any]], typing.Any] = {
    list: typing.List,
    set: typing.Set,
    tuple: typing.Tuple,
    collections.deque: typing.Deque,
    frozenset: typing.FrozenSet,
    collections.abc.MutableSet: typing.MutableSet,
}


class Iterable(typing.Generic[IterT, V], Field[IterT]):
    """Base class for iterable fields."""

    default_serializers = {
        "python": iterable_python_serializer,
        "json": iterable_json_serializer,
    }
    default_deserializer = iterable_deserializer
    default_validator = validate_iterable  # type: ignore[assignment]

    def __init__(
        self,
        field_type: typing.Type[IterT],
        child: typing.Optional[Field[V]] = None,
        *,
        size: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
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

    @property
    def typestr(self) -> str:
        value = f"{getattr(self.field_type, '__name__', None) or str(self.field_type)}[{self.child.typestr}]"
        if self.strict:
            return f"strict[{value}]"
        return value

    def __get_type_hint__(self):
        """Return type information for the field."""
        return _GENERIC_ITER_MAP[self.field_type][self.child.__get_type_hint__()]  # type: ignore[return-value]

    def bind(
        self, parent: typing.Type[typing.Any], name: typing.Optional[str] = None
    ) -> None:
        super().bind(parent, name)
        self.child.bind(parent)

    def post_init(self) -> None:
        super().post_init()
        if not isinstance(self.child, Field):
            raise TypeError(
                f"'child' must be a field instance , not {type(self.child).__name__}."
            )
        self.child.post_init()

    def check_type(self, value: typing.Any) -> TypeGuard[IterT]:
        if not super().check_type(value):
            return False

        child_field = self.child
        if value and child_field is not AnyType:
            for item in value:
                if not child_field.check_type(item):
                    return False
        return True


class List(Iterable[typing.List[V], V]):
    """List field."""

    def __init__(
        self,
        child: typing.Optional[Field[V]] = None,
        *,
        size: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        super().__init__(field_type=list, child=child, size=size, **kwargs)


class Set(Iterable[typing.MutableSet[V], V]):
    """Set field."""

    def __init__(
        self,
        child: typing.Optional[Field[V]] = None,
        *,
        size: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        super().__init__(
            field_type=collections.abc.MutableSet, child=child, size=size, **kwargs
        )


class FrozenSet(Iterable[typing.FrozenSet[V], V]):
    """Set field."""

    def __init__(
        self,
        child: typing.Optional[Field[V]] = None,
        *,
        size: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        super().__init__(field_type=frozenset, child=child, size=size, **kwargs)


class Tuple(Iterable[typing.Tuple[V], V]):
    """Tuple field."""

    def __init__(
        self,
        child: typing.Optional[Field[V]] = None,
        *,
        size: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        super().__init__(field_type=tuple, child=child, size=size, **kwargs)


class Deque(Iterable[typing.Deque[V], V]):
    """Deque field."""

    def __init__(
        self,
        child: typing.Optional[Field[V]] = None,
        *,
        size: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        super().__init__(field_type=collections.deque, child=child, size=size, **kwargs)


email_validator = field_validators.pattern(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    message="Value must be a valid email address.",
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


class Choice(Field[T]):
    """Field with predefined choices for values."""

    @typing.overload
    def __init__(
        self,
        field_type: typing.Type[T],
        *,
        choices: None = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None: ...

    @typing.overload
    def __init__(
        self,
        field_type: typing.Type[T],
        *,
        choices: typing.Iterable[T],
        **kwargs: Unpack[FieldKwargs],
    ) -> None: ...

    def __init__(
        self,
        field_type: typing.Type[T],
        *,
        choices: typing.Optional[typing.Iterable[T]] = None,
        **kwargs: Unpack[FieldKwargs],
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


def json_deserializer(value: typing.Any, field: Field[typing.Any]) -> JSONValue:
    """Deserialize JSON data to the specified type."""
    return make_jsonable(value)


class JSON(Field[JSONValue]):
    """Field for handling JSON data."""

    default_serializers = {
        "json": no_op_serializer,
    }
    default_deserializer = json_deserializer

    def __init__(
        self,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        super().__init__(field_type=AnyType, **kwargs)

    @property
    def typestr(self) -> str:
        value = "json"
        if self.strict:
            return f"strict[{value}]"
        return value


slug_validator = field_validators.pattern(
    r"^[a-zA-Z0-9_-]+$",
    message="Value must be a valid slug.",
)


class Slug(String):
    """Field for URL-friendly strings."""

    default_min_length = 1
    default_validator = slug_validator


def bytes_serializer(value: bytes, field: "Bytes", context: Context) -> str:
    """Serialize bytes to a string."""
    return base64.b64encode(value).decode(encoding=field.encoding)


def bytes_deserializer(value: typing.Any, field: "Bytes") -> bytes:
    """Deserialize an object or base64-encoded string to bytes."""
    if isinstance(value, str):
        try:
            return base64.b64decode(value.encode(encoding=field.encoding))
        except (ValueError, TypeError) as exc:
            raise DeserializationError.from_exception(
                exc,
                message="Invalid base64 string for bytes",
                input_type=type(value),
                expected_type=field.typestr,
                location=[field.name],
            )
    return bytes(value)


class Bytes(Field[bytes]):
    """Field for handling byte types or base64-encoded strings."""

    default_serializers = {
        "json": bytes_serializer,
    }
    default_deserializer = bytes_deserializer

    def __init__(self, encoding: str = "utf-8", **kwargs: Unpack[FieldKwargs]) -> None:
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


def path_deserializer(value: typing.Any, field: "Path") -> pathlib.Path:
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
        "json": string_serializer,
    }
    default_deserializer = path_deserializer

    def __init__(
        self,
        resolve: bool = False,
        **kwargs: Unpack[FieldKwargs],
    ):
        super().__init__(field_type=pathlib.Path, **kwargs)
        self.resolve = resolve
