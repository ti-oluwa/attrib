import typing
from typing_extensions import Unpack

from attrib.descriptors import Field, FieldInitKwargs, NonTupleFieldType
from attrib.dataclass import Dataclass
from attrib.serializers import _serialize_instance
from attrib._utils import is_iterable


_Dataclass = typing.TypeVar("_Dataclass", bound=Dataclass)
_Dataclass_co = typing.TypeVar("_Dataclass_co", bound=Dataclass, covariant=True)


def nested_json_serializer(
    instance: _Dataclass_co,
    field: Field[_Dataclass_co],
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Dict[str, typing.Any]:
    """Serialize a nested dataclass instance to a dictionary."""
    return _serialize_instance(
        fmt="json",
        instance=instance,
        options_map=context.get("__options", None) if context else None,
        context=context,
    )


def nested_python_serializer(
    instance: _Dataclass_co,
    field: Field[_Dataclass_co],
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Dict[str, typing.Any]:
    """Serialize a nested dataclass instance to a dictionary."""
    return _serialize_instance(
        fmt="python",
        instance=instance,
        options_map=context.get("__options", None) if context else None,
        context=context,
    )


class Nested(Field[_Dataclass]):
    """Nested Dataclass field."""

    default_serializers = {
        "python": nested_python_serializer,
        "json": nested_json_serializer,
    }

    def __init__(
        self,
        dataclass_: NonTupleFieldType[_Dataclass],
        **kwargs: Unpack[FieldInitKwargs],
    ) -> None:
        """
        Initialize a nested field.

        :param dataclass_: The dataclass type or a callable that returns the dataclass type.

        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(dataclass_, **kwargs)

    def post_init_validate(self) -> None:
        super().post_init_validate()
        field_type = typing.cast(NonTupleFieldType[_Dataclass], self.field_type)
        if isinstance(field_type, (typing.ForwardRef, str)):
            return

        if is_iterable(field_type):
            raise TypeError(
                f"{type(self).__name__} does not support iterable types. Got {field_type}."
            )
        if not issubclass(field_type, Dataclass):
            raise TypeError(
                f"{type(self).__name__} must be a subclass of Dataclass. Got {field_type}."
            )
