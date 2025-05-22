from attrib.descriptors.base import String
from attrib import validators


__all__ = [
    "HexColor",
    "RGBColor",
    "HSLColor",
]


hex_color_validator = validators.pattern(
    r"^#(?:[0-9a-fA-F]{3,4}){1,2}$",
    message="'{name}' must be a valid hex color code.",
)


class HexColor(String):
    """Field for handling hex color values."""

    # default_min_length = 4
    # default_max_length = 9
    default_validator = hex_color_validator


rgb_color_validator = validators.pattern(
    r"^rgb[a]?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*(\d{1,3})\s*)?\)$",
    message="'{name}' must be a valid RGB color code.",
)


class RGBColor(String):
    """Field for handling RGB color values."""

    # default_max_length = 38
    default_validator = rgb_color_validator

    def __init__(
        self,
        *,
        min_length=None,
        max_length=None,
        trim_whitespaces=True,
        **kwargs,
    ):
        # Field enforces lowercase for RGB color values
        kwargs["to_lowercase"] = True
        kwargs["to_uppercase"] = False
        super().__init__(
            min_length=min_length,
            max_length=max_length,
            trim_whitespaces=trim_whitespaces,
            **kwargs,
        )


hsl_color_validator = validators.pattern(
    r"^hsl[a]?\(\s*(\d{1,3})\s*,\s*(\d{1,3})%?\s*,\s*(\d{1,3})%?\s*(?:,\s*(\d{1,3})\s*)?\)$",
    message="'{name}' must be a valid HSL color code.",
)


class HSLColor(String):
    """Field for handling HSL color values."""

    # default_max_length = 40
    default_validator = hsl_color_validator

    def __init__(
        self,
        *,
        min_length=None,
        max_length=None,
        trim_whitespaces=True,
        **kwargs,
    ):
        # Field enforces lowercase for HSL color values
        kwargs["to_lowercase"] = True
        kwargs["to_uppercase"] = False
        super().__init__(
            min_length=min_length,
            max_length=max_length,
            trim_whitespaces=trim_whitespaces,
            **kwargs,
        )
