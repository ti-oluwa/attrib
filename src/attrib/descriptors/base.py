"""Attribute descriptors"""

import base64
import collections.abc
import decimal
import functools
import inspect
import io
import pathlib
import typing
import uuid

import annotated_types as annot
from typing_extensions import Annotated, Self, TypeAlias, TypeGuard, Unpack

from attrib import validators as field_validators
from attrib._utils import (
    iexact,
    is_enum_type,
    is_iterable,
    is_iterable_type,
    is_valid_type,
    json_deserializer,
    json_serializer,
    no_op_serializer,
    resolve_type,
    string_serializer,
)
from attrib.adapters.base import TypeAdapter
from attrib.exceptions import (
    ConfigurationError,
    DeserializationError,
    FieldError,
    InvalidTypeError,
    SerializationError,
    ValidationError,
)
from attrib.types import (
    EMPTY,
    AnyType,
    Context,
    Deserializer,
    Empty,
    IterT,
    JSONValue,
    NoneType,
    P,
    R,
    RealNumberT,
    Serializer,
    SupportsRichComparison,
    T,
    V,
    Validator,
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
    "Email",
    "Choice",
    "Slug",
    "Char",
    "Character",
    "Number",
    "Float",
    "Integer",
    "Decimal",
    "Iterable",
    "List",
    "Set",
    "FrozenSet",
    "Deque",
    "JSONObject",
    "Bytes",
    "IOBase",
    "Path",
]


NonTupleFieldType: TypeAlias = typing.Union[
    str,
    T,
    typing.Type[T],
    typing.Type[AnyType],
    typing.ForwardRef,
]
FieldType: TypeAlias = typing.Union[
    NonTupleFieldType[T],
    typing.Tuple[typing.Union[typing.ForwardRef, typing.Type[T]], ...],
    TypeAdapter[T],
]
NonForwardRefFieldType: TypeAlias = typing.Union[
    typing.Type[T],
    typing.Type[AnyType],
    typing.Tuple[typing.Type[T], ...],
]

DefaultFactory = typing.Callable[[], typing.Union[T, typing.Any]]
"""Type alias for default value factories."""


def unsupported_field_serializer(
    value: typing.Any, field: "Field[typing.Any]", _: Context
) -> None:
    """Raise an error for unsupported field serialization."""
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


def unsupported_field_deserializer(value: typing.Any, field: "Field[T]") -> T:
    """Raise an error for unsupported field deserialization."""
    raise DeserializationError(
        "Cannot deserialize value.",
        input_type=type(value),
        expected_type=field.typestr,
        location=[field.name],
        code="coercion_not_supported",
    )


DEFAULT_SERIALIZERS: typing.Dict[str, Serializer[typing.Any]] = {
    "json": json_serializer,
    "python": no_op_serializer,
}


def default_field_deserializer(
    value: typing.Any, field: "Field[T]"
) -> typing.Union[T, typing.Any]:
    """
    Deserialize a value to the specified field type.

    :param value: The value to deserialize.
    :param field: The field instance to which the value belongs.
    :return: The deserialized value.
    """
    if field._allow_any_type:
        return value

    field_type = field.field_type
    if field._type_is_union and not field._type_is_enum:
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

    default_serializers: typing.Mapping[str, Serializer[T]] = {}
    """Default serializers for the field, if any."""
    default_deserializer: Deserializer[T] = default_field_deserializer
    """Default deserializer for the field, if any."""
    default_validator: typing.Optional[Validator[T]] = None
    """Default validator for the field, if any."""

    def __init__(
        self,
        field_type: FieldType[T],
        default: typing.Union[T, DefaultFactory[T], Empty, None] = EMPTY,
        alias: typing.Optional[str] = None,
        serialization_alias: typing.Optional[str] = None,
        allow_null: bool = False,
        required: bool = False,
        strict: bool = False,
        validator: typing.Optional[Validator[T]] = None,
        serializers: typing.Optional[typing.Mapping[str, Serializer[T]]] = None,
        deserializer: typing.Optional[Deserializer[T]] = None,
        always_coerce: bool = False,
        skip_validator: bool = False,
        validate_default: bool = False,
        fail_fast: bool = False,
        hash: bool = False,
        repr: bool = True,
        eq: bool = True,
        init: bool = True,
        order: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
    ) -> None:
        """
        Initialize the field.

        :param field_type: The expected type for field values.
        :param default: A default value for the field to be used if no value is set. Defaults to `EMPTY`.
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
        :param always_coerce: If True, the field will always attempt to coerce the value to the specified type,
            even if the value is already of that type. Defaults to False. This is useful when
            when constant 'transformation' and not just 'type checking' is desired during deserialization.

        :param skip_validator: If True, the field will skip validator run after deserialization. Defaults to False.
        :param validate_default: If True, the field will check that the default value is valid before setting it. Defaults to False.
        :param fail_fast: If True, the field will raise an error immediately a validation fails. Defaults to False.
        :param hash: If True, the field will be included in the hash of the class it is defined in. Defaults to False.
        :param repr: If True, the field will be included in the repr of the class it is defined in. Defaults to True.
        :param eq: If True, the field will be compared for equality when comparing instances of the class it is defined in. Defaults to True.
        :param init: If True, the field will be included as an instantiation argument for the class it is defined in. Defaults to True.
        :param order: If set, the field will be included in the ordering of instances of the class it is defined in.
            The value must be a non-negative integer, where lower values indicate higher precedence in ordering.
            That is, a field with order=0 will be ordered/compared before a field with order=1.
        """
        default_deserializer = type(self).default_deserializer
        validators = []
        if type(self).default_validator is not None:
            validators.append(type(self).default_validator)
        if validator is not None:
            validators.append(validator)

        serializers_map = dict(self.default_serializers)
        self._uses_type_adapter = False
        if isinstance(field_type, TypeAdapter):
            self.field_type = field_type
            self._uses_type_adapter = True
            # Custom serializers/deserializers are not supported for TypeAdapter fields
            # they should be passed to the TypeAdapter itself.
            if serializers is not None:
                raise ConfigurationError(
                    "Custom serializers are not supported for TypeAdapter fields.",
                    "Pass custom serializers to the TypeAdapter instead.",
                )
            if deserializer is not None:
                raise ConfigurationError(
                    "Custom deserializers are not supported for TypeAdapter fields.",
                    "Pass custom deserializer to the TypeAdapter instead.",
                )
            if field_type._is_built:
                default_deserializer = field_type.deserializer
                if field_type.validator:
                    validators.append(field_type.validator)
                serializers_map.update(field_type.serializers)

        elif not isinstance(field_type, str):
            self.field_type = field_type
        else:
            self.field_type = typing.ForwardRef(field_type)

        self.name: typing.Optional[str] = None
        self.alias = alias
        self.allow_null = allow_null
        self.required = required
        self.strict = strict
        self.validator = field_validators.pipe(*validators) if validators else None
        self.serializers = {
            **serializers_map,
            **(serializers or {}),
        }
        self.deserializer = deserializer or default_deserializer
        self.default = default
        self.always_coerce = always_coerce
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
        self._identity_formats = {}
        """Set of serialization formats that will not change the value during serialization."""
        self._typestr: str = "<unknown>"
        """The string representation of the field type."""
        self._serialization_keys: typing.Dict[bool, str] = {}
        """A cache for serialization keys based on by_alias flag."""
        self._type_cache = {}
        """Cache for resolved types."""

        # Precomputation flags
        self._allow_any_type = False
        self._default_is_factory = False
        self._default_is_valid = False
        self._type_is_union = False
        self._type_is_enum = False
        self._can_use_identity_type_check = False
        self._has_validator = False
        self._is_slotted = False

    @property
    def typestr(self) -> str:
        """
        Return the string representation of the field type.

        This is useful for debugging and introspection.
        """
        return self._typestr  # type: ignore

    def get_typestr(self) -> str:
        """
        Return the string representation of the field type.

        This is useful for debugging and introspection.
        """
        value = getattr(self.field_type, "__name__", None) or str(self.field_type)
        if self.strict:
            value = f"strict[{value}]"
        return value

    def _update_identity_formats(self) -> None:
        """Update the identity formats set. Must be called ONCE the field type is built and all serializers are known."""
        self._identity_formats = {
            fmt for fmt, f in self.serializers.items() if f is no_op_serializer
        }

    def _compute_type_flags(self) -> None:
        """Compute type-related flags. Used when the field type is changed."""
        self._allow_any_type = (
            self.field_type is AnyType or self.field_type is typing.Any
        )
        self._type_is_union = is_iterable(self.field_type)
        self._type_is_enum = (
            is_enum_type(self.field_type) if not self._allow_any_type else False
        )
        self._can_use_identity_type_check = (
            self._uses_type_adapter is False and self._type_is_union is False
        )

    def _compute_validator_flags(self) -> None:
        """Compute validator-related flags. Used when the validator is changed."""
        self._has_validator = self.validator is not None and not self.skip_validator

    def _compute_default_flags(self) -> None:
        """Compute default-related flags. Used when the default value is changed."""
        self._default_is_factory = callable(self.default)
        # If `_check_default` is False, the default value is assumed valid and doesn't need validation.
        # However, this only applies if the field is not configured to always coerce input.
        # If `_check_default` is True, the default value needs to be validated.
        self._default_is_valid = (
            self._check_default is False
            and self.always_coerce is False
            and self.required is False
        )

    def _compute_slotted_flag(self) -> None:
        """Compute whether the field is slotted. To be called after binding the field to a parent class."""
        self._is_slotted = self._slotted_name is not None

    def __post_init__(self) -> None:
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

        has_default = self.default is not EMPTY
        if self.required and has_default:
            raise FieldError(
                "A default value is not necessary when required=True", name=self.name
            )
        if self.strict and self.always_coerce:
            raise FieldError(
                "Cannot set both strict=True and always_coerce=True. "
                "If strict is True, the field will not attempt to coerce values.",
                name=self.name,
            )
        if has_default and self.default is None and not self.allow_null:
            raise FieldError(
                "Field default cannot be None when `allow_null=False`", name=self.name
            )
        self._typestr = self.get_typestr()
        self._compute_type_flags()
        self._compute_validator_flags()
        self._compute_default_flags()

    def __get_type_hint__(self):
        """Return type information for the field."""
        if self._allow_any_type:
            return typing.Any

        type_list = []
        if self._uses_type_adapter:
            type_list.append(self.field_type.adapted)  # type: ignore
        elif self._type_is_union and not self._type_is_enum:
            type_list.extend(self.field_type)  # type: ignore
        else:
            type_list.append(self.field_type)

        if len(type_list) == 1:
            typ = type_list[0]
        else:
            typ = typing.Union[type_list]
        if self.allow_null:
            typ = typing.Optional[typ]
        return typ

    def get_default(self) -> typing.Union[T, typing.Any, None]:
        """Return the default value for the field."""
        if self._default_is_factory:
            try:
                return self.default()  # type: ignore
            except Exception as exc:
                raise FieldError(
                    "An error occurred while calling the default factory.",
                    name=self.name,
                ) from exc
        return self.default

    def set_default(self, instance: typing.Any) -> None:
        """
        Set the default value for the field on an instance.

        :param instance: The instance to which the field belongs.
        """
        self._set_value(
            instance,
            value=self.get_default(),
            is_valid=self._default_is_valid,
        )
        if self._check_default:
            # Since we've checked the default so we don't need to check it again.
            # However, if `always_coerce` is True, we cannot assume the default is valid.
            # Also, if the field is required, the default may not be valid. Lastly,
            # if the default is a factory, we cannot assume the default is valid.
            # We have to re-evaluate the validity of the default in these cases.
            self._check_default = False
            self._default_is_valid = (
                self.always_coerce is False
                and self.required is False
                and not self._default_is_factory
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
        field_type = self.field_type
        if isinstance(field_type, TypeAdapter) and not field_type._is_built:
            field_type.build(globalns=globalns, localns=localns)
            self.serializers.update(field_type.serializers)  # type: ignore
            self.deserializer = typing.cast(Deserializer[T], field_type.deserializer)
            if self.validator is not None and field_type.validator is not None:
                self.validator = field_validators.pipe(
                    self.validator,  # type: ignore
                    field_type.validator,  # type: ignore
                )
            elif field_type.validator is not None:
                self.validator = field_type.validator

            # Use already resolved type of the `TypeAdapter`
            self.field_type = field_type
        else:
            self.field_type = typing.cast(
                NonForwardRefFieldType[T],
                resolve_type(
                    field_type,
                    globalns=globalns,
                    localns=localns,
                ),
            )

        # Re-compute type and validator flags as the field's type and validator may have changed
        self._compute_type_flags()
        self._compute_validator_flags()
        # We precompute the identity formats here, so that we can use it later in `asdict` so
        # We do not need to call `Field.serialize` for formats that do not change the value.
        # This should reduce overhead in function calls, for serialization formats that do not change the value.
        # Especially for function used in hot paths like `Field.serialize`.
        self._update_identity_formats()

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

        # Pre-compute serialization keys for both `by_alias` modes now that we have the name
        # For `by_alias=False`, we use the field's actual name
        # For `by_alias=True`, use `serialization_alias` if set, otherwise `effective_name` (which is alias or name)
        self._serialization_keys[False] = self.name  # type: ignore
        self._serialization_keys[True] = self.serialization_alias or self.effective_name  # type: ignore

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
        # Pre-compute slotted flag now that we have the slotted name
        self._compute_slotted_flag()

    def __set_name__(self, owner: typing.Type[typing.Any], name: str):
        """Bind the field to the owner class."""
        self.bind(owner, name)

    def __delete__(self, instance: typing.Any) -> None:
        if self._is_slotted:
            object.__delattr__(instance, self._slotted_name)  # type: ignore[arg-type]
        else:
            del instance.__dict__[self.name]

    @typing.overload
    def __get__(
        self,
        instance: None,
        owner: typing.Type[typing.Any],
    ) -> Self: ...

    @typing.overload
    def __get__(
        self,
        instance: typing.Any,
        owner: typing.Optional[typing.Type[typing.Any]],
    ) -> T: ...

    def __get__(
        self,
        instance: typing.Optional[typing.Any],
        owner: typing.Optional[typing.Type[typing.Any]],
    ) -> typing.Union[T, Self, None, Empty]:
        """Retrieve the field value from an instance or return the default if unset."""
        if instance is None:
            return self

        if self._is_slotted:
            return object.__getattribute__(instance, self._slotted_name)  # type: ignore[arg-type]
        return instance.__dict__[self.name]

    def __set__(self, instance: typing.Any, value: typing.Any) -> None:
        """Set and validate the field value on an instance."""
        validated = self._coerce_and_validate(instance, value)
        if self._is_slotted:
            object.__setattr__(instance, self._slotted_name, validated)  # type: ignore[arg-type]
        else:
            instance.__dict__[self.name] = validated

        # Values where set explicitly, so we mark them as such
        field_set: typing.Set = instance.__fields_set__  # type: ignore[attr-defined]
        field_set.add(self.name)

    def check_type(self, value: typing.Any) -> TypeGuard[T]:
        """Check if the value is of the expected type."""
        if self._allow_any_type:
            return True

        value_type = type(value)
        if value_type in self._type_cache:
            return self._type_cache[value_type]

        if self.allow_null and value_type is NoneType:
            self._type_cache[value_type] = True
            return True

        field_type = self.field_type
        if self._can_use_identity_type_check and value_type is field_type:
            self._type_cache[value_type] = True
            return True

        is_type = isinstance(value, field_type)  # type: ignore[arg-type]
        if not self._uses_type_adapter:
            self._type_cache[value_type] = is_type
        return is_type

    def _coerce_and_validate(
        self, instance: typing.Any, value: typing.Any
    ) -> typing.Union[T, None, Empty]:
        """
        Validate and coerce value.

        Orchestrates the coercion and validation of a field value,
        taking into consideration the field's configuration too.

        :param instance: The instance to which the field belongs.
        :param value: The field value to validate and coerce.
        :return: The validated and coerced value.
        """
        is_empty = value is EMPTY
        if is_empty and self.required:
            raise ValidationError(
                "Value is required but not provided.",
                parent_name=type(instance).__name__ if instance else None,
                input_type=type(value),
                location=[self.name],
                expected_type=self.typestr,
                code="missing_value",
            )

        elif is_empty:
            return EMPTY

        if self.allow_null and value is None:
            return None

        deserialized = self.deserialize(value, instance)
        self.validate(deserialized, instance)
        return deserialized

    def _set_value(
        self,
        instance: typing.Any,
        value: typing.Any,
        is_valid: bool = False,
    ) -> typing.Union[T, typing.Any]:
        """
        Set the field's value on an instance, performing validation if required.

        :param instance: The instance to which the field belongs.
        :param value: The field value to set.
        :param is_valid: The validity of the value. If True, skip coercion and validation. Defaults to False.
        :return: The value that was set.
        """
        if is_valid:
            validated = value
        else:
            validated = self._coerce_and_validate(instance, value)

        if self._slotted_name:
            object.__setattr__(instance, self._slotted_name, validated)
        else:
            instance.__dict__[self.name] = validated
        return validated

    def deserialize(
        self,
        value: typing.Union[T, typing.Any],
        instance: typing.Optional[typing.Any] = None,
    ) -> typing.Optional[T]:
        """
        Cast the value to the field's specified type, if necessary.

        Converts the field's value to the specified type before it is set on the instance.
        """
        # Skip type check if `always_coerce` is True. Just coerce directly.
        if self.always_coerce:
            try:
                return self.deserializer(value, self)  # type: ignore[call-arg]
            except (ValueError, TypeError, DeserializationError) as exc:
                raise DeserializationError.from_exc(
                    exc,
                    message="Failed to deserialize value.",
                    parent_name=type(instance).__name__ if instance else None,
                    input_type=type(value),
                    expected_type=self.typestr,
                    location=[self.name],
                ) from exc

        # Check if already correct type
        if self.check_type(value):
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

        # Coerce to correct type
        try:
            return self.deserializer(value, self)  # type: ignore[call-arg]
        except (ValueError, TypeError, DeserializationError) as exc:
            raise DeserializationError.from_exc(
                exc,
                message="Failed to deserialize value.",
                parent_name=type(instance).__name__ if instance else None,
                input_type=type(value),
                expected_type=self.typestr,
                location=[self.name],
            ) from exc

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
        if not self._has_validator:
            return
        try:
            self.validator(  # type: ignore
                value,
                self,  # type: ignore[arg-type]
                instance,
                fail_fast=self.fail_fast,
            )
        except (ValueError, ValidationError) as exc:
            raise ValidationError.from_exc(
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
        try:
            return self.serializers[fmt](value, self, context)
        except (ValueError, TypeError, SerializationError) as exc:
            raise SerializationError.from_exc(
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
    serializers: typing.Optional[typing.Dict[str, Serializer[typing.Any]]]
    """A mapping of serialization formats to their respective serializer functions."""
    deserializer: typing.Optional[Deserializer[typing.Any]]
    """A deserializer function to convert the field's value to the expected type."""
    default: typing.Union[typing.Any, DefaultFactory, None]
    """A default value for the field to be used if no value is set."""
    always_coerce: bool
    """
    If True, the field will always attempt to coerce the value to the specified type, 
    even if the value is already of that type.
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


class BooleanFieldMeta(FieldMeta):
    """COnvert truthy and falsy values to lowercase bitwise for comparison."""

    def __init__(cls, name, bases, attrs) -> None:
        truthy = getattr(cls, "truthy", None)
        if truthy is not None:
            cls.truthy = {iexact(v) for v in truthy}
        super().__init__(name, bases, attrs)


def boolean_field_deserializer(value: typing.Any, field: "Boolean") -> bool:
    if isinstance(value, str) and iexact(value) in field.truthy:
        return True
    return bool(value)


class Boolean(Field[bool], metaclass=BooleanFieldMeta):
    """Field for handling boolean values."""

    truthy: typing.Set[typing.Any] = {"1", "true", "yes", "t", "y"}
    default_deserializer = boolean_field_deserializer
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

    if min_value is not None and max_value is not None:
        return [field_validators.range_(min_value, max_value)]

    validators = []
    if min_value is not None:
        validators.append(field_validators.gte(min_value))
    if max_value is not None:
        validators.append(field_validators.lte(max_value))
    return validators


class Number(Field[RealNumberT]):
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


class Float(Number[float]):
    """Field for handling float values."""

    def __init__(
        self,
        *,
        min_value: typing.Optional[float] = None,
        max_value: typing.Optional[float] = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        super().__init__(
            field_type=float,
            min_value=min_value,
            max_value=max_value,
            **kwargs,
        )


def integer_field_deserializer(value: typing.Any, field: "Integer") -> int:
    """
    Deserialize a value to an integer.

    :param field: The field instance to which the value belongs.
    :param value: The value to deserialize.
    :return: The deserialized integer value.
    """
    return int(value, base=field.base)


class Integer(Number[int]):
    """Field for handling integer values."""

    default_deserializer = integer_field_deserializer

    def __init__(
        self,
        *,
        min_value: typing.Optional[int] = None,
        max_value: typing.Optional[int] = None,
        base: Annotated[int, annot.Interval(ge=2, le=36)] = 10,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        super().__init__(
            field_type=int,
            min_value=min_value,
            max_value=max_value,
            **kwargs,
        )
        self.base = base

    def __post_init__(self) -> None:
        super().__post_init__()
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


class Decimal(Number[decimal.Decimal]):
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
        if deserialized is not None and self.dp is not None:
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


@functools.lru_cache(maxsize=50)
def _build_string_formatter(
    trim_whitespaces: bool, to_lowercase: bool, to_uppercase: bool
) -> typing.Callable[[str], str]:
    """Build a string formatter function based on the specified options."""
    if trim_whitespaces and to_lowercase:
        return lambda s: s.strip().lower()
    if trim_whitespaces and to_uppercase:
        return lambda s: s.strip().upper()
    if trim_whitespaces:
        return lambda s: s.strip()
    if to_lowercase:
        return lambda s: s.lower()
    if to_uppercase:
        return lambda s: s.upper()
    return lambda s: s


class String(Field[str]):
    """Field for handling string values."""

    default_min_length: typing.Optional[int] = None
    """Default minimum length of values."""
    default_max_length: typing.Optional[int] = None
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
                    *build_min_max_length_validators(
                        min_length=min_length or type(self).default_min_length,
                        max_length=max_length or type(self).default_max_length,
                    ),
                ],
            )
        )
        if validators:
            kwargs["validator"] = field_validators.pipe(*validators)
        super().__init__(field_type=str, **kwargs)
        self.trim_whitespaces = trim_whitespaces
        self.to_lowercase = to_lowercase
        self.to_uppercase = to_uppercase
        if trim_whitespaces or to_lowercase or to_uppercase:
            self._formatter = _build_string_formatter(
                trim_whitespaces=trim_whitespaces,
                to_lowercase=to_lowercase,
                to_uppercase=to_uppercase,
            )
        else:
            self._formatter = None

    def __post_init__(self) -> None:
        super().__post_init__()
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
        if not deserialized or self._formatter is None:
            return deserialized
        return self._formatter(deserialized)


class Character(String):
    """Field for handling single character string values."""

    default_validator = field_validators.max_length(1)


Char = Character


slug_validator = field_validators.pattern(
    r"^[a-zA-Z0-9_-]+$",
    message="Value must be a valid slug.",
)


class Slug(String):
    """Field for URL-friendly strings."""

    default_min_length = 1
    default_validator = slug_validator


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
        min_length: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        max_length: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        trim_whitespaces: bool = True,
        to_lowercase: bool = True,  # Prefer to store email values in lowercase
        to_uppercase: bool = False,
        **kwargs: Unpack[FieldKwargs],
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
        is_enum_choice = is_enum_type(field_type)
        if not choices and not is_enum_choice:
            raise ValueError(
                "Choices must be provided for the field. Use `choices` argument."
            )

        if choices and not is_enum_choice:
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


class UUID(Field[uuid.UUID]):
    """Field for handling UUID values."""

    default_serializers = {
        "json": string_serializer,
    }

    def __init__(self, **kwargs: Unpack[FieldKwargs]):
        super().__init__(field_type=uuid.UUID, **kwargs)


def iterable_field_python_serializer(
    value: typing.Iterable[V],
    field: "Iterable[typing.Iterable[V], V]",
    context: Context,
) -> typing.Iterable[typing.Any]:
    """
    Serialize an iterable.

    :param value: The iterable to serialize.
    :param field: The field instance to which the iterable belongs.
    :param context: Additional context for serialization.
    :return: The serialized iterable.
    """
    if "python" in field._identity_formats:
        return value

    serialized = []
    child_field = field.child
    child_serializer = child_field.serialize
    fail_fast = field.fail_fast

    error: typing.Optional[SerializationError] = None
    for index, item in enumerate(value):
        try:
            serialized_item = child_serializer(item, "python", context)
        except SerializationError as exc:
            child_typestr = child_field.typestr
            input_type = type(item)
            if fail_fast:
                raise SerializationError.from_exc(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                ) from exc
            if error is None:
                error = SerializationError.from_exc(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                )
            else:
                error.merge(
                    SerializationError.from_exc(
                        exc,
                        input_type=input_type,
                        expected_type=child_typestr,
                        location=[index],
                    )
                )
        else:
            serialized.append(serialized_item)

    if error is not None:
        raise error
    field_type = field.field_type
    if field_type is list:
        return serialized
    return field_type(serialized)  # type: ignore[return-value]


def iterable_field_json_serializer(
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
    if "json" in field._identity_formats:
        return list(value)

    serialized = []
    child_field = field.child
    child_serializer = child_field.serialize
    fail_fast = field.fail_fast

    error: typing.Optional[SerializationError] = None
    for index, item in enumerate(value):
        try:
            serialized_item = child_serializer(item, "json", context)
        except SerializationError as exc:
            child_typestr = child_field.typestr
            input_type = type(item)
            if fail_fast:
                raise SerializationError.from_exc(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                ) from exc

            if error is None:
                error = SerializationError.from_exc(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                )
            else:
                error.merge(
                    SerializationError.from_exc(
                        exc,
                        input_type=input_type,
                        expected_type=child_typestr,
                        location=[index],
                    )
                )
        else:
            serialized.append(serialized_item)

    if error is not None:
        raise error
    return serialized


def iterable_field_deserializer(
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

    error: typing.Optional[DeserializationError] = None
    for index, item in enumerate(value):
        try:
            deserialized_item = child_deserializer(item)
        except DeserializationError as exc:
            child_typestr = child_field.typestr
            input_type = type(item)
            if fail_fast:
                raise DeserializationError.from_exc(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                ) from exc

            if error is None:
                error = DeserializationError.from_exc(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                )
            else:
                error.merge(
                    DeserializationError.from_exc(
                        exc,
                        input_type=input_type,
                        expected_type=child_typestr,
                        location=[index],
                    )
                )
        else:
            deserialized.append(deserialized_item)

    if error is not None:
        raise error

    field_type = field.field_type
    if field_type is list:
        return deserialized
    return field_type(deserialized)  # type: ignore[return-value]


def iterable_field_validator(
    value: typing.Iterable[V],
    field: typing.Optional["Iterable[typing.Iterable, V]"] = None,
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
        return None

    child_field = field.child
    child_validator = child_field.validate
    error: typing.Optional[ValidationError] = None
    fail_fast = field.fail_fast

    for index, item in enumerate(value):
        try:
            child_validator(item, instance)
        except ValidationError as exc:
            child_typestr = child_field.typestr
            input_type = type(item)
            if fail_fast:
                raise ValidationError.from_exc(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                ) from exc

            if error is None:
                error = ValidationError.from_exc(
                    exc,
                    input_type=input_type,
                    expected_type=child_typestr,
                    location=[index],
                )
            else:
                error.merge(
                    ValidationError.from_exc(
                        exc,
                        input_type=input_type,
                        expected_type=child_typestr,
                        location=[index],
                    )
                )

    if error is not None:
        raise error


_GENERIC_ITER_TYPES: typing.Dict[
    typing.Type[typing.Iterable[typing.Any]], typing.Any
] = {
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
        "python": iterable_field_python_serializer,
        "json": iterable_field_json_serializer,
    }
    default_deserializer = iterable_field_deserializer  # type: ignore
    default_validator = iterable_field_validator  # type: ignore

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

    def get_typestr(self) -> str:
        if self._typestr is not None:
            return self._typestr
        value = f"{getattr(self.field_type, '__name__', None) or str(self.field_type)}[{self.child.typestr}]"
        if self.strict:
            value = f"strict[{value}]"
        self._typestr = value
        return value

    def __get_type_hint__(self):
        """Return type information for the field."""
        return _GENERIC_ITER_TYPES[self.field_type][self.child.__get_type_hint__()]  # type: ignore[return-value]

    def bind(
        self, parent: typing.Type[typing.Any], name: typing.Optional[str] = None
    ) -> None:
        super().bind(parent, name)
        self.child.bind(parent)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.child, Field):
            raise TypeError(
                f"'child' must be a field instance , not {type(self.child).__name__}."
            )
        self.child.__post_init__()

    def check_type(self, value: typing.Any) -> TypeGuard[IterT]:
        """Check if value is correct iterable type with correct item types."""
        if not super().check_type(value):
            return False

        if not value:
            return True
        elif self.child.field_type is AnyType:
            return True

        check_child = self.child.check_type
        for item in value:
            if not check_child(item):
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
        super().__init__(
            field_type=list,
            child=child,
            size=size,
            **kwargs,
        )


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
            field_type=set,
            child=child,
            size=size,
            **kwargs,
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
        super().__init__(
            field_type=frozenset,
            child=child,
            size=size,
            **kwargs,
        )


class Deque(Iterable[typing.Deque[V], V]):
    """Deque field."""

    def __init__(
        self,
        child: typing.Optional[Field[V]] = None,
        *,
        size: typing.Optional[Annotated[int, annot.Ge(0)]] = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        super().__init__(
            field_type=collections.deque,
            child=child,
            size=size,
            **kwargs,
        )


class JSONObject(Field[JSONValue]):
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

    def get_typestr(self) -> str:
        if self._typestr is not None:
            return self._typestr

        value = "json"
        if self.strict:
            value = f"strict[{value}]"
        self._typestr = value
        return value


def bytes_serializer(value: bytes, field: "Bytes", context: Context) -> str:
    """Serialize bytes to a string."""
    return base64.b64encode(value).decode(encoding=field.encoding)


def bytes_deserializer(value: typing.Any, field: "Bytes") -> bytes:
    """Deserialize an object or base64-encoded string to bytes."""
    if isinstance(value, str):
        try:
            return base64.b64decode(value.encode(encoding=field.encoding))
        except (ValueError, TypeError) as exc:
            raise DeserializationError.from_exc(
                exc,
                message="Invalid base64 string for bytes",
                input_type=type(value),
                expected_type=field.typestr,
                location=[field.name],
            ) from exc
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
        "json": unsupported_field_serializer,
    }
    default_deserializer = unsupported_field_deserializer


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
