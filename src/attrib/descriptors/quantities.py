from collections.abc import Sequence
import typing
import numbers
from typing_extensions import Unpack
import quantities as pq

from attrib.descriptors.base import Field, FieldKwargs
from attrib.exceptions import FieldError
from attrib._typing import Context


__all__ = [
    "Quantity",
]


def _quantity_from_parts(
    parts: typing.List[typing.Any],
    default_unit: typing.Union[pq.UnitQuantity, str] = pq.dimensionless,
) -> pq.Quantity:
    """Create a Quantity from a list of parts."""
    if (parts_length := len(parts)) == 0 or parts_length > 2:
        raise ValueError(
            f"Invalid quantity parts: {parts}. Expected 1 or 2 parts (magnitude and unit)."
        )

    if parts_length == 1:
        magnitude = parts[0]
        return pq.Quantity(float(magnitude), default_unit)

    magnitude, unit = parts
    return pq.Quantity(float(magnitude), unit)


def quantity_deserializer(value: typing.Any, field: "Quantity") -> pq.Quantity:
    """Deserialize a value to a physical quantity."""
    try:
        if isinstance(value, pq.Quantity):
            deserialized = value

        elif isinstance(value, (Sequence, set)):
            parts = value.split() if isinstance(value, str) else list(value)
            deserialized = _quantity_from_parts(
                parts, default_unit=field.unit or pq.dimensionless
            )

        elif isinstance(value, numbers.Real):
            unit = field.unit or pq.dimensionless
            deserialized = pq.Quantity(float(value), unit)
            return deserialized

        else:
            raise ValueError(f"Invalid value for Quantity: {value!r}")

        return deserialized.rescale(field.unit) if field.unit else deserialized
    except (
        SyntaxError
    ) as exc:  # `quantities` library raises `SyntaxError` for invalid units
        raise ValueError(
            f"Invalid quantity value: {value!r}. Expected a valid quantity format."
        ) from exc


def quantity_json_serializer(
    value: pq.Quantity, field: "Quantity", context: Context
) -> str:
    """Serialize a physical quantity to JSON."""
    return f"{value.magnitude} {value.units.dimensionality}"


class Quantity(Field[pq.Quantity]):
    """
    Field for handling physical quantities using the `quantities` library.

    A quantity must either be a `quantities.Quantity` object or a sequence with two parts: 'magnitude' and 'unit'.
    Any sequence-like input will be split into parts, The first part
    is treated as the magnitude, while the second part as the unit.

    If the input is a single value (most-likely a real-number), it will be treated as a dimensionless quantity.
    The unit can be specified as an acceptable string or a `quantities.UnitQuantity`.

    For example, a valid input could be:
    - `"10 meter"`
    - `"10 m"`
    - `10 * pq.meter`
    - `["10", "meter"]`
    - `["10"]` (defaults to dimensionless unit)
    - `10` (defaults to dimensionless unit)
    - `pq.Quantity(10, pq.meter)`
    - `pq.Quantity(10, "meter")`

    """

    default_deserializer = quantity_deserializer
    default_serializers = {
        "json": quantity_json_serializer,
    }

    def __init__(
        self,
        unit: typing.Optional[typing.Union[str, pq.UnitQuantity]] = None,
        **kwargs: Unpack[FieldKwargs],
    ) -> None:
        """
        Initialize the field.

        :param unit: The default unit for the quantity. It can be an acceptable unit string or a `pq.UnitQuantity`.
            If not provided, and input also lacks a unit, the quantity will default to `pq.dimensionless`.

        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(field_type=pq.Quantity, **kwargs)
        self.unit = unit

    def post_init_validate(self) -> None:
        super().post_init_validate()
        if self.unit is not None:
            try:
                pq.quantity.validate_dimensionality(self.unit)
            except (TypeError, SyntaxError) as exc:
                raise FieldError("Invalid quantity unit", name=self.name) from exc
