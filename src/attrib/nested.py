import typing
from typing_extensions import Unpack

from attrib.fields import Field, FieldInitKwargs, FieldType
from attrib.dataclass import Dataclass
from attrib.serializers import _serialize_instance


_Dataclass = typing.TypeVar("_Dataclass", bound=Dataclass)
_Dataclass_co = typing.TypeVar("_Dataclass_co", bound=Dataclass, covariant=True)


def nested_json_serializer(
    instance: _Dataclass_co,
    field: Field[_Dataclass_co],
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Dict[str, typing.Any]:
    """Serialize a nested dataclass instance to a dictionary."""
    if context:
        depth = context.get("depth", 0)
        fields = context.get("__targets__", None)
        serializable_fields = (
            fields.get(instance.__class__.__name__, None) if fields else None
        )
    else:
        depth = 0
        serializable_fields = None

    return _serialize_instance(
        fmt="json",
        fields=serializable_fields or instance.__fields__,
        instance=instance,
        depth=depth,
        context=context,
    )


def nested_python_serializer(
    instance: _Dataclass_co,
    field: Field[_Dataclass_co],
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Dict[str, typing.Any]:
    """Serialize a nested dataclass instance to a dictionary."""
    if context:
        depth = context.get("depth", 0)
        fields = context.get("__targets__", None)
        serializable_fields = (
            fields.get(instance.__class__.__name__, None) if fields else None
        )
    else:
        depth = 0
        serializable_fields = None

    return _serialize_instance(
        fmt="python",
        fields=serializable_fields or instance.__fields__,
        instance=instance,
        depth=depth,
        context=context,
    )


class NestedField(Field[_Dataclass]):
    """Nested Dataclass field."""

    default_serializers = {
        "python": nested_python_serializer,
        "json": nested_json_serializer,
    }

    def __init__(
        self,
        dataclass_: FieldType[_Dataclass],
        **kwargs: Unpack[FieldInitKwargs],
    ) -> None:
        """
        Initialize a NestedField.

        :param dataclass_: The dataclass type or a callable that returns the dataclass type.
    
        :param kwargs: Additional keyword arguments for the field.
        """
        super().__init__(dataclass_, **kwargs)

    # def post_init_validate(self):
    #     super().post_init_validate()
    #     self.field_type = typing.cast(typing.Type[_Dataclass], self.field_type)
    #     if not issubclass(self.field_type, Dataclass):
    #         raise TypeError(
    #             f"{self.field_type} must be a subclass of {Dataclass.__name__}."
    #         )
