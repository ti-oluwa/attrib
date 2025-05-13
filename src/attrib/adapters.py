import typing
from collections import defaultdict

from attrib._typing import Validator, T, Serializer, Deserializer
from attrib.validators import Pipeline
from attrib.exceptions import SerializationError


def _unsupported_serializer(*args, **kwargs) -> None:
    """Raise an error for unsupported serialization."""
    raise SerializationError(
        "Unsupported serialization format. Register a serializer for this format."
    )


def _unsupported_serializer_factory():
    """Return a function that raises an error for unsupported serialization."""
    return _unsupported_serializer


@typing.final
class SerializerRegistry(typing.NamedTuple):
    """
    Registry class to handle different serialization formats.

    :param serializer_map: A dictionary mapping format names to their respective serializer functions.
    """

    serializer_map: typing.DefaultDict[str, Serializer] = defaultdict(
        _unsupported_serializer_factory
    )

    def __call__(self, fmt: str, *args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        """
        Serialize data using the specified format.

        :param fmt: The format to serialize to (e.g., 'json', 'xml').
        :param args: Positional arguments to pass to the format's serializer.
        :param kwargs: Keyword arguments to pass to the format's serializer.
        :return: Serialized data in the specified format.
        """
        return self.serializer_map[fmt](*args, **kwargs)


@typing.final
class TypeAdapter(typing.Generic[T]):
    """
    Concrete `TypeAdapter` implementation.

    A type adapter is a pseudo-type. It defines type-like behavior using 3 methods:
    - validate: Validates the value
    - serialize: Serializes the value to a specific format
    - deserialize: Coerces the value to a specific type
    """

    __slots__ = ("name", "validator", "serializer", "deserializer")

    def __init__(
        self,
        name: typing.Optional[str] = None,
        /,
        *,
        validators: typing.Optional[typing.Iterable[Validator[T]]] = None,
        serializers: typing.Optional[typing.Mapping[str, Serializer]] = None,
        deserializer: typing.Optional[Deserializer] = None,
    ):
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

    def validate(
        self,
        value: typing.Any,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Any:
        """
        Validate the value using the validator.

        :param value: The value to validate
        :param args: Additional arguments to pass to the validator
        :param kwargs: Additional keyword arguments to pass to the validator
        :return: None if all validators pass
        """
        if self.validator:
            self.validator(value, self, *args, **kwargs)
        return value

    def serialize(
        self,
        value: T,
        fmt: str,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Any:
        """
        Serialize the value using the serializer.

        :param value: The value to serialize
        :param fmt: The format to use for serialization
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
    ) -> typing.Any:
        """
        Deserialize the value using the deserializer.

        :param value: The value to deserialize
        :param args: Additional arguments to pass to the deserializer
        :param kwargs: Additional keyword arguments to pass to the deserializer
        :return: The deserialized value
        """
        if self.deserializer:
            return self.deserializer(value, *args, **kwargs)
        return value

    def __call__(
        self,
        value: typing.Any,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Any:
        """
        Call the adapter to coerce the value to the adapted type and validate it.
        This method is a convenience method that combines deserialization and validation.

        :param value: The value to adapt
        :param args: Additional arguments for validation
        :param kwargs: Additional keyword arguments for validation
        :return: The validated value
        """
        deserialized = self.deserialize(value)
        return self.validate(deserialized, *args, **kwargs)
