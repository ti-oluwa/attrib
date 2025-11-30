from types import MappingProxyType
import typing

from typing_extensions import Unpack

from attrib._utils import is_iterable
from attrib.dataclass import Dataclass
from attrib.descriptors.base import Field, FieldKwargs, NonTupleFieldType
from attrib.exceptions import FieldError
from attrib.serializers import _asdict
from attrib.types import Context, DataDict, JSONDict, JSONNamedDataTuple

__all__ = [
    "Nested",
    "dataclass_serializers",
]


DataclassT = typing.TypeVar("DataclassT", bound=Dataclass)
DataclassTco = typing.TypeVar("DataclassTco", bound=Dataclass, covariant=True)


def nested_json_serializer(
    instance: DataclassTco,
    field: Field[DataclassTco],
    context: Context,
) -> typing.Union[JSONDict, JSONNamedDataTuple]:
    return _asdict(instance, context=context, fmt="json")


def nested_python_serializer(
    instance: DataclassTco,
    field: Field[DataclassTco],
    context: Context,
) -> DataDict:
    return _asdict(instance, context=context, fmt="python")


dataclass_serializers = MappingProxyType(
    {
        "json": nested_json_serializer,
        "python": nested_python_serializer,
    }
)
"""Default serializers dataclass fields' use."""


class Nested(Field[DataclassT]):
    """Nested Dataclass field."""

    default_serializers = dataclass_serializers

    def __init__(
        self, nested: NonTupleFieldType[DataclassT], /, **kwargs: Unpack[FieldKwargs]
    ) -> None:
        """
        Initialize nested field.

        :param nested: The nested dataclass type.
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(nested, **kwargs)

    def __post_init__(self) -> None:
        super().__post_init__()
        field_type = typing.cast(NonTupleFieldType[DataclassT], self.field_type)
        if isinstance(field_type, (typing.ForwardRef, str)):
            return

        if is_iterable(field_type):
            raise FieldError(
                f"{type(self).__name__} does not support iterable types. Got {field_type}."
            )
        if not issubclass(field_type, Dataclass):
            raise FieldError(
                f"{field_type} must be a subclass of {Dataclass.__qualname__}. Got {field_type}."
            )
