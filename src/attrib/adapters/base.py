import inspect
import typing

from attrib._utils import is_generic_type, resolve_type
from attrib.exceptions import DeserializationError, ValidationError
from attrib.types import Deserializer, SerializerMap, T, Validator
from attrib.validators import instance_of

__all__ = ["TypeAdapter"]


@typing.final
class TypeAdapter(typing.Generic[T]):
    """
    Concrete `TypeAdapter` implementation.

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
        "_type_validator",
        "serializers",
        "deserializer",
        "strict",
        "_is_built",
        "_can_cache_type",
        "_type_cache",
    )

    def __init__(
        self,
        adapted: typing.Union[typing.Type[T], T],
        /,
        *,
        name: typing.Optional[str] = None,
        deserializer: typing.Optional[Deserializer[typing.Union[T, typing.Any]]] = None,
        validator: typing.Optional[Validator[typing.Union[T, typing.Any]]] = None,
        serializers: typing.Optional[SerializerMap] = None,
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
        self._type_validator: typing.Optional[
            Validator[typing.Union[T, typing.Any]]
        ] = None
        self.deserializer = deserializer
        self.serializers = serializers or {}
        self.strict = strict
        self._is_built = False
        self._can_cache_type = True
        self._type_cache: typing.Dict[typing.Type[typing.Any], bool] = {}
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
        from attrib.adapters._concrete import (
            build_concrete_type_deserializer,
            build_concrete_type_serializers_map,
            build_dataclass_serializers_map,
        )
        from attrib.adapters._generics import (
            build_generic_type_deserializer,
            build_generic_type_serializers_map,
            build_generic_type_validator,
        )
        from attrib.dataclasses import Dataclass

        if self._is_built:
            raise RuntimeError(
                f"Adapter {self.name or repr(self)} is already built. "
                "You cannot build it again."
            )

        self._is_built = True
        if globalns is None:
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
            self._can_cache_type = False  # Should not cache generic types
            if (
                len(self.serializers) < 2
            ):  # Should contain at least "python" and "json" serializers
                self.serializers = build_generic_type_serializers_map(
                    self.adapted, serializers=self.serializers, depth=depth
                )

            if self._type_validator is None:
                self._type_validator = build_generic_type_validator(
                    self.adapted, depth=depth
                )

            if self.deserializer is None:
                self.deserializer = build_generic_type_deserializer(
                    self.adapted, depth=depth
                )
            return

        if not isinstance(self.adapted, type):
            raise TypeError(f"Adapter target `{self.adapted}` must be a type")

        if len(self.serializers) < 2:
            self.serializers = (
                build_dataclass_serializers_map(self.serializers)
                if issubclass(self.adapted, Dataclass)
                else build_concrete_type_serializers_map(
                    self.adapted, serializers=self.serializers, depth=depth
                )
            )

        if self._type_validator is None:
            self._type_validator = instance_of(self.adapted)
        if self.deserializer is None:
            self.deserializer = build_concrete_type_deserializer(
                self.adapted, depth=depth
            )
        return

    def check_type(self, value: typing.Any) -> bool:
        """
        Check if the value is of the adapted type.

        :param value: The value to check
        :return: True if the value is of the adapted type, False otherwise
        """
        if self._type_validator is None:
            raise RuntimeError(
                f"Adapter {self.name or repr(self)} is not built. "
                "You must build it before checking types."
            )

        if self._can_cache_type:
            value_type = type(value)
            if value_type in self._type_cache:
                return self._type_cache[value_type]
            is_type = self._type_cache[value_type] = isinstance(value, self.adapted)  # type: ignore
            return is_type

        try:
            self._type_validator(value, self)
            return True
        except ValidationError:
            return False

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
        if (validator := self.validator) is None:
            return

        try:
            validator(value, self, *args, **kwargs)
        except (ValidationError, ValueError) as exc:
            raise ValidationError.from_exc(
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
        return self.serializers[fmt](value, self, *args, **kwargs)

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
            return self.deserializer(value, self, *args, **kwargs)
        except (DeserializationError, ValueError, TypeError) as exc:
            raise DeserializationError.from_exc(
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

    def __instancecheck__(self, instance: typing.Any) -> bool:
        """
        Check if the instance is of the adapted type.

        :param instance: The instance to check
        :return: True if the instance is of the adapted type, False otherwise
        """
        return self.check_type(instance)

    def __repr__(self) -> str:
        """
        Return a string representation of the adapter.

        :return: A string representation of the adapter
        """
        return f"{self.__class__.__name__}(name={self.name or '<unset>'}, adapted={self.adapted})"
