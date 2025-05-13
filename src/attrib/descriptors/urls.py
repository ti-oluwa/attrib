import typing
from typing_extensions import Unpack

from attrib.descriptors.base import Field, FieldInitKwargs, to_string_serializer
from urllib3.util import Url, parse_url  # type: ignore[import]


def url_deserializer(
    value: typing.Any,
    field: Field,
) -> typing.Any:
    """Deserialize URL data to the specified type."""
    return parse_url(str(value))


class URL(Field[Url]):
    """Field for handling URL values."""

    default_serializers = {
        "json": to_string_serializer,
    }
    default_deserializer = url_deserializer

    def __init__(self, **kwargs: Unpack[FieldInitKwargs]) -> None:
        super().__init__(field_type=Url, **kwargs)
