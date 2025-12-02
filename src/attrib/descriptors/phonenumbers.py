import typing

from phonenumbers import (
    PhoneNumber as PhoneNumberType,
)
from phonenumbers import (
    PhoneNumberFormat,
    format_number,
)
from phonenumbers import (
    parse as parse_number,
)
from typing_extensions import Unpack

from attrib._utils import no_op_serializer
from attrib.descriptors.base import Field, FieldKwargs, String
from attrib.types import Context


def phone_number_serializer(
    value: PhoneNumberType,
    field: "PhoneNumber",
    context: Context,
) -> str:
    """Serialize a phone number object to a string format."""
    return format_number(value, field.output_format)


def phone_number_deserializer(
    value: typing.Any, field: Field[typing.Any]
) -> PhoneNumberType:
    """Deserialize a string to a phone number object."""
    return parse_number(value)


class PhoneNumber(Field[PhoneNumberType]):
    """Phone number object field."""

    default_output_format: typing.ClassVar[int] = PhoneNumberFormat.E164
    default_serializers = {
        "json": phone_number_serializer,
    }
    default_deserializer = phone_number_deserializer  # type: ignore[assignment]

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


def phone_number_string_deserializer(
    value: typing.Any,
    field: "PhoneNumberString",
) -> str:
    """Deserialize a string to a phone number object."""
    return format_number(parse_number(value), field.output_format)


class PhoneNumberString(String):
    """Phone number string field"""

    default_output_format: typing.ClassVar[int] = PhoneNumberFormat.E164
    default_serializers = {
        # Phonenumber string would have already been parsed to a string in output format,
        # so we can use the python serializer (that returns the string as is)
        "json": no_op_serializer,
    }
    default_deserializer = phone_number_string_deserializer  # type: ignore[assignment]

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
