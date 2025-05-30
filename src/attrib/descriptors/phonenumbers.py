import typing
from typing_extensions import Unpack

from attrib.descriptors.base import Field, String, FieldKwargs
from phonenumbers import (  # type: ignore[import]
    PhoneNumber as PhoneNumberType,
    parse as parse_number,
    format_number,
    PhoneNumberFormat,
)


def phone_number_serializer(
    value: PhoneNumberType, field: "PhoneNumber", *_: typing.Any, **__: typing.Any
) -> str:
    """Serialize a phone number object to a string format."""
    output_format = typing.cast(int, field.output_format)
    return format_number(value, output_format)


def phone_number_deserializer(
    value: typing.Any, *_: typing.Any, **__: typing.Any
) -> PhoneNumberType:
    """Deserialize a string to a phone number object."""
    return parse_number(value)


class PhoneNumber(Field[PhoneNumberType]):
    """Phone number object field."""

    default_output_format: typing.ClassVar[int] = PhoneNumberFormat.E164
    default_serializers = {
        "json": phone_number_serializer,
    }
    default_deserializer = phone_number_deserializer

    def __init__(
        self,
        output_format: typing.Optional[int] = None,
        **kwargs: Unpack[FieldKwargs],
    ):
        """
        Initialize the field.

        :param output_format: The preferred output format for the phone number value.
            E.g. PhoneNumberFormat.E164, PhoneNumberFormat.INTERNATIONAL, etc.
            See the `phonenumbers` library for more details.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(field_type=PhoneNumberType, **kwargs)
        self.output_format = output_format or self.default_output_format


def phone_number_string_serializer(
    value: PhoneNumberType, field: "PhoneNumberString", *_: typing.Any, **__: typing.Any
) -> str:
    """Serialize a phone number object to a string format."""
    return format_number(value, field.output_format)


def phone_number_string_deserializer(
    value: typing.Any, field: "PhoneNumberString", *_: typing.Any, **__: typing.Any
) -> str:
    """Deserialize a string to a phone number object."""
    return format_number(parse_number(value), field.output_format)


class PhoneNumberString(String):
    """Phone number string field"""

    default_output_format: typing.ClassVar[int] = PhoneNumberFormat.E164
    default_serializers = {
        "json": phone_number_string_serializer,
    }
    default_deserializer = phone_number_string_deserializer

    def __init__(
        self,
        output_format: typing.Optional[int] = None,
        **kwargs: Unpack[FieldKwargs],
    ):
        """
        Initialize the field.

        :param output_format: The preferred output format for the phone number value.
            E.g. PhoneNumberFormat.E164, PhoneNumberFormat.INTERNATIONAL, etc.
            See the `phonenumbers` library for more details.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(max_length=20, **kwargs)
        self.output_format = output_format or self.default_output_format


__all__ = [
    "PhoneNumber",
    "PhoneNumberString",
]
