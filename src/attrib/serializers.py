"""Dataclass serialization module."""

from collections import defaultdict
import typing
from typing_extensions import TypeAlias

from attrib.types import (
    EMPTY,
    JSONDict,
    DataDict,
    Context,
)
from attrib.exceptions import DeserializationError, SerializationError, ValidationError
from attrib.dataclass import Dataclass


__all__ = [
    "Option",
    "Options",
    "serialize",
]


@typing.final
class Option:
    """Dataclass serialization options."""

    __slots__ = ("target", "recurse", "include", "exclude", "field_names", "hash")

    def __init__(
        self,
        target: typing.Type[Dataclass],
        recurse: bool = True,
        include: typing.Optional[typing.Set[str]] = None,
        exclude: typing.Optional[typing.Set[str]] = None,
    ) -> None:
        if include and exclude:
            raise ValueError(
                "Cannot specify both 'include' and 'exclude' in the same Option."
            )

        if not isinstance(target, type) or not issubclass(target, Dataclass):
            raise TypeError(
                f"Target must be a subclass of Dataclass, got {target.__name__}"
            )

        self.target = target
        self.recurse = recurse
        self.include = include
        self.exclude = exclude

        target_fields = set(target._name_map.keys())

        if include:
            unknown_fields = include - target_fields
            if unknown_fields:
                raise ValueError(
                    f"Some included fields are not present in {target.__name__} - {', '.join(unknown_fields)}"
                )
            self.field_names = include
        elif exclude:
            unknown_fields = exclude - target_fields
            if unknown_fields:
                raise ValueError(
                    f"Some excluded fields are not present in {target.__name__} - {', '.join(unknown_fields)}"
                )
            self.field_names = target_fields - exclude
        else:
            self.field_names = target_fields

        self.hash = (
            self.target.__name__,
            self.recurse,
            frozenset(self.field_names) if self.field_names else frozenset(),
        )

    def __repr__(self) -> str:
        return (
            f"Option(target={self.target.__name__}, recurse={self.recurse}, "
            f"include={self.include}, exclude={self.exclude})"
        )


OptionsMap: TypeAlias = typing.DefaultDict[typing.Type[Dataclass], Option]
DEFAULT_OPTION = Option(Dataclass)
DEFAULT_OPTIONS_MAP: OptionsMap = defaultdict(lambda: DEFAULT_OPTION)


from line_profiler import profile


# @profile
def asdict(
    instance: Dataclass,
    context: Context,
    fmt: typing.Union[typing.Literal["python", "json"], str] = "python",
) -> DataDict:
    """
    Serialize instance as a dictionary.

    :param instance: The instance to serialize.
    :param fmt: Serialization format (e.g., 'python', 'json').
    :param context: Context dictionary.
    :return: Dictionary representation of the instance.
    :raises SerializationError: If serialization fails.
    """
    exclude_unset: bool = context["_exclude_unset"]
    options: OptionsMap = context["_options"]

    datacls = type(instance)
    option = options[datacls]
    field_names = option.field_names or datacls._name_map.keys()
    if exclude_unset:
        field_names = instance.__fields_set__ & field_names

    serialized_data = {}
    _setter = serialized_data.__setitem__
    by_alias = context["_by_alias"]
    error = None
    fields = instance.__dataclass_fields__
    for name in field_names:
        field = fields[name]
        key = field.serialization_alias or field.effective_name if by_alias else name

        try:
            value = field.__get__(instance, datacls)
            if value is EMPTY:
                continue

            if fmt in field._identity_formats or (
                not option.recurse and field._meta["_nested"]
            ):
                _setter(key, value)
                continue

            _setter(key, field.serialize(value, fmt, context))
        except (SerializationError, DeserializationError, ValidationError) as exc:
            parent_name = datacls.__name__
            if context["_fail_fast"]:
                raise SerializationError.from_exception(
                    exc,
                    parent_name=parent_name,
                    expected_type=field.typestr,
                    location=[name],
                ) from exc
            if error is None:
                error = SerializationError.from_exception(
                    exc,
                    parent_name=parent_name,
                    expected_type=field.typestr,
                    location=[name],
                )
            else:
                error.add(
                    exc,
                    parent_name=parent_name,
                    expected_type=field.typestr,
                    location=[name],
                )

    if error:
        raise error
    return serialized_data


def Options(*options: Option) -> OptionsMap:
    """
    Process a variable number of serialization `Option` instances into a mapping.

    :param options: Variable number of `Option` instances.
    :return: A mapping of dataclass types to their corresponding `Option` instances.
    """
    options_map: OptionsMap = defaultdict(lambda: DEFAULT_OPTION)
    for option in options:
        options_map[option.target] = option
    return options_map


@typing.overload
def serialize(
    instance: Dataclass,
    *,
    fmt: typing.Literal["python"] = ...,
    options: typing.Optional[OptionsMap] = ...,
    context: typing.Optional[Context] = ...,
    fail_fast: bool = ...,
    by_alias: bool = ...,
    exclude_unset: bool = ...,
) -> DataDict: ...


@typing.overload
def serialize(
    instance: Dataclass,
    *,
    fmt: typing.Literal["json"] = ...,
    options: typing.Optional[OptionsMap] = ...,
    context: typing.Optional[Context] = ...,
    fail_fast: bool = ...,
    by_alias: bool = ...,
    exclude_unset: bool = ...,
) -> JSONDict: ...


@typing.overload
def serialize(
    instance: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = ...,
    options: typing.Optional[OptionsMap] = ...,
    context: typing.Optional[Context] = ...,
    fail_fast: bool = ...,
    by_alias: bool = ...,
    exclude_unset: bool = ...,
) -> DataDict: ...


def serialize(
    instance: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = "python",
    options: typing.Optional[OptionsMap] = None,
    context: typing.Optional[Context] = None,
    fail_fast: bool = False,
    by_alias: bool = False,
    exclude_unset: bool = False,
) -> typing.Any:
    """
    Build a serialized representation of the instance.

    :param instance: The dataclass instance to serialize.
    :param fmt: The format to serialize to. Can be 'python' or 'json' or any other
        custom format supported by the fields of the instance.

    :param options: Optional serialization options for the dataclass.
    :param context: Optional context for serialization. This can be used to pass
        additional information to the serialization process.

    :param fail_fast: If True, serialization will stop at the first error encountered.
        If False, it will collect all errors and raise a `SerializationError` at the end.

    :param by_alias: If True, use field aliases for serialization. Defaults to False.
        If the field has no serialization alias, it will use the effective name which
        resolves to the default (deserialization) alias if it was set, or the field
        name otherwise.

    :param exclude_unset: If True, exclude fields that were not explicitly set on the instance
        during instantiation or directly. This does not include field defaults set for fields with
        default values.

    :return: A dictionary representation of the instance if `astuple` is False,
        or a tuple of (name, value) pairs if `astuple` is True.
    :raises SerializationError: If serialization fails.

    Example:
    ```python
    import attrib
    from attrib.descriptors.phonenumbers import PhoneNumber

    class Candidate(attrib.Dataclass):
        name = attrib.String()
        age = attrib.Integer()
        email = attrib.String()
        phone = PhoneNumber(serialization_alias="phone_number")
        address = attrib.String()

    john = Candidate(
        name="John Doe",
        age="30",
        email="john.doe@example.com",
        phone="+1234567890",
        address="123 Obadeyi Street, Lagos, Nigeria",
    )

    data = attrib.serialize(
        john,
        fmt="json",
        options=attrib.Options(
            attrib.Option(exclude={"address"}),
        ),
        by_alias=True,
    )
    print(data)
    # Output:
    # {
    #     "name": "John Doe",
    #     "age": 30,
    #     "email": "john.doe@example.com",
    #     "phone_number": "+1-234-567-890",
    # }
    ```
    """
    context = context or {}
    context["_options"] = options or DEFAULT_OPTIONS_MAP
    context["_fail_fast"] = fail_fast
    context["_by_alias"] = by_alias
    context["_exclude_unset"] = exclude_unset
    return asdict(instance, fmt=fmt, context=context)
