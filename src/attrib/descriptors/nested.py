import typing
from typing_extensions import Unpack

from attrib.descriptors.base import Field, FieldInitKwargs, NonTupleFieldType
from attrib.dataclass import Dataclass
from attrib.serializers import (
    serialize_instance_asdict,
    serialize_instance_asnamedtuple,
)
from attrib._utils import is_iterable
from attrib.exceptions import FieldError


_Dataclass = typing.TypeVar("_Dataclass", bound=Dataclass)
_Dataclass_co = typing.TypeVar("_Dataclass_co", bound=Dataclass, covariant=True)


def nested_json_serializer(
    instance: _Dataclass_co,
    field: Field[_Dataclass_co],
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Union[
    typing.Dict[str, typing.Any], typing.Tuple[typing.Tuple[str, typing.Any], ...]
]:
    """Serialize a nested dataclass instance to a dictionary."""
    if context and context.get("__astuple", False):
        return serialize_instance_asnamedtuple(
            fmt="json",
            instance=instance,
            context=context,
        )
    return serialize_instance_asdict(
        fmt="json",
        instance=instance,
        context=context,
    )


def nested_python_serializer(
    instance: _Dataclass_co,
    field: Field[_Dataclass_co],
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Union[
    typing.Dict[str, typing.Any], typing.Tuple[typing.Tuple[str, typing.Any], ...]
]:
    """Serialize a nested dataclass instance to a dictionary."""
    if context and context.get("__astuple", False):
        return serialize_instance_asnamedtuple(
            fmt="python",
            instance=instance,
            context=context,
        )
    return serialize_instance_asdict(
        fmt="python",
        instance=instance,
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
            raise FieldError(
                f"{type(self).__name__} does not support iterable types. Got {field_type}."
            )
        if not issubclass(field_type, Dataclass):
            raise FieldError(
                f"{field_type} must be a subclass of {Dataclass.__qualname__}. Got {field_type}."
            )
