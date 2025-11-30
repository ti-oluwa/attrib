from typing_extensions import Unpack

from attrib import validators
from attrib.descriptors.base import FieldKwargs, String


__all__ = [
    "HexColor",
    "RGBColor",
    "HSLColor",
    "hex_color_validator",
    "rgb_color_validator",
    "hsl_color_validator",
]


hex_color_validator = validators.pattern(
    r"^#(?:[0-9a-fA-F]{3,4}){1,2}$",
    message="Value must be a valid hex color code.",
)


class HexColor(String):
    """Field for handling hex color values."""

    # default_min_length = 4
    # default_max_length = 9
    default_validator = hex_color_validator


rgb_color_validator = validators.pattern(
    r"^rgb[a]?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*(\d{1,3})\s*)?\)$",
    message="Value must be a valid RGB color code.",
)


class RGBColor(String):
    """Field for handling RGB color values."""

    # default_max_length = 38
    default_validator = rgb_color_validator

    def __init__(self, **kwargs: Unpack[FieldKwargs]) -> None:
        # Enforces lowercase for RGB color values
        super().__init__(
            trim_whitespaces=True,
            to_lowercase=True,
            to_uppercase=False,
            **kwargs,
        )


hsl_color_validator = validators.pattern(
    r"^hsl[a]?\(\s*(\d{1,3})\s*,\s*(\d{1,3})%?\s*,\s*(\d{1,3})%?\s*(?:,\s*(\d{1,3})\s*)?\)$",
    message="Value must be a valid HSL color code.",
)


class HSLColor(String):
    """Field for handling HSL color values."""

    # default_max_length = 40
    default_validator = hsl_color_validator

    def __init__(self, **kwargs: Unpack[FieldKwargs]) -> None:
        # Enforces lowercase for HSL color values
        super().__init__(
            trim_whitespaces=True,
            to_lowercase=True,
            to_uppercase=False,
            **kwargs,
        )
