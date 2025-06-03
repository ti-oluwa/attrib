"""Dataclass serialization module."""

from collections import deque
from collections.abc import Sequence
import functools
import typing
from annotated_types import Ge, MinLen
from typing_extensions import Annotated

from attrib._typing import (
    EMPTY,
    JSONDict,
    JSONNamedDataTuple,
    NamedDataTuple,
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


class Option(typing.NamedTuple):
    """Dataclass serialization options."""

    target: typing.Type[Dataclass] = Dataclass
    """Target dataclass type for serialization."""
    depth: Annotated[typing.Optional[int], Ge(0)] = None
    """Depth for nested serialization."""
    include: typing.Optional[Annotated[typing.Set[str], MinLen(1)]] = None
    """Name of fields to include in serialization."""
    exclude: typing.Optional[Annotated[typing.Set[str], MinLen(1)]] = None
    """Name of fields to exclude from serialization."""
    strict: bool = False
    """If False, instances of subclasses of the target class will be serialized using this
    option, if no option is defined specifically for them. If True, only direct instances of the target class will be serialized.
    """

    def __hash__(self) -> int:
        return hash(
            (
                self.target,
                self.depth,
                tuple(self.include or []),
                tuple(self.exclude or []),
                self.strict,
            )
        )


DEFAULT_OPTION = Option()
OptionsMap: typing.TypeAlias = typing.MutableMapping[typing.Type[Dataclass], Option]


def resolve_option(
    dataclass_: typing.Type[Dataclass],
    options: OptionsMap,
) -> Option:
    """Find the most appropriate `Option` for a given dataclass type."""
    if not options:
        return DEFAULT_OPTION

    mro = dataclass_.__mro__
    for i in range(len(mro) - 1):
        base = mro[i]
        option = options.get(base, None)
        if option and (not option.strict or base is dataclass_):
            return option
    return DEFAULT_OPTION


SerializationTarget: typing.TypeAlias = Dataclass
CurrentSerializationDepth: typing.TypeAlias = int
TargetParentName: typing.TypeAlias = str
SerializationOutput = typing.TypeVar("SerializationOutput")
SerializationStack: typing.TypeAlias = typing.Deque[
    typing.Tuple[
        SerializationTarget,
        typing.Optional[TargetParentName],
        CurrentSerializationDepth,
        SerializationOutput,
    ]
]


def _serialize_instance_asdict(
    fmt: str,
    instance: Dataclass,
    context: Context,
) -> DataDict:
    """
    Iteratively serialize a dataclass instance.

    *Significantly faster and memory efficient than recursive serialization for*
    *large/deeply nested dataclass serialization.*

    :param instance: The dataclass instance to serialize.
    :param fmt: Serialization format (e.g., 'python', 'json').
    :param context: Context dictionary.
    :return: Dictionary representation of the instance.
    :raises SerializationError: If serialization fails.
    """
    serialized_data = {}
    stack: SerializationStack[typing.Dict[typing.Any, typing.Any]] = deque(
        [
            (
                instance,
                None,
                0,
                serialized_data,
            )
        ]
    )
    local_options = context["__options"]
    error = None

    while stack:
        target_instance, parent_name, current_depth, serialized_output = stack.pop()
        instance_type = type(target_instance)

        if instance_type in local_options:
            option = local_options[instance_type]
        else:
            option = resolve_option(instance_type, local_options)
            local_options[instance_type] = option  # Cache resolved option

        if context["__exclude_unset"]:
            field_names = target_instance.__fields_set__
        else:
            field_names = target_instance.__fields__.keys()

        if option.include:
            field_names = set(field_names) & option.include
        elif option.exclude:
            field_names = set(field_names) - option.exclude

        for name in field_names:
            field = target_instance.__fields__[name]
            if context["__by_alias"]:
                key = field.serialization_alias or field.effective_name
            else:
                key = name

            try:
                value = field.__get__(target_instance, owner=instance_type)
                if value is EMPTY:
                    continue

                if isinstance(value, Dataclass):
                    if option.depth is not None and current_depth >= option.depth:
                        serialized_output[key] = value
                        continue

                    nested_output = {}
                    serialized_output[key] = nested_output
                    stack.appendleft((value, name, current_depth + 1, nested_output))
                else:
                    if (
                        isinstance(value, (Sequence, set))
                        and option.depth is not None
                        and current_depth >= option.depth
                    ):
                        serialized_output[key] = value
                        continue

                    serialized_output[key] = field.serialize(
                        value, fmt=fmt, context=context
                    )

            except (SerializationError, DeserializationError, ValidationError) as exc:
                if context["__fail_fast"]:
                    raise SerializationError.from_exception(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[parent_name],
                    ) from exc
                if error is None:
                    error = SerializationError.from_exception(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[parent_name],
                    )
                else:
                    error.add(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[parent_name],
                    )

    if error:
        raise error
    return serialized_data


def _serialize_instance_asnamedtuple(
    fmt: str,
    instance: Dataclass,
    context: Context,
) -> NamedDataTuple:
    """
    Iteratively serialize a dataclass instance into a tuple of (name, value) pairs.

    *Significantly faster and memory efficient than recursive serialization for*
    *large/deeply nested dataclass serialization.*

    :param instance: The dataclass instance to serialize.
    :param fmt: Serialization format (e.g., 'python', 'json').
    :param context: Context dictionary.
    :return: Tuple of (name, value) pairs representing the instance.
    :raises SerializationError: If serialization fails.
    """
    serialized_items = []
    stack: SerializationStack[typing.List[typing.Any]] = deque(
        [
            (
                instance,
                None,
                0,
                serialized_items,
            )
        ]
    )
    local_options = context["__options"]
    error = None

    while stack:
        target_instance, parent_name, current_depth, serialized_output = stack.pop()
        instance_type = type(target_instance)

        if instance_type in local_options:
            option = local_options[instance_type]
        else:
            option = resolve_option(instance_type, local_options)
            local_options[instance_type] = option

        if context["__exclude_unset"]:
            field_names = target_instance.__fields_set__
        else:
            field_names = target_instance.__fields__.keys()

        if option.include:
            field_names = set(field_names) & option.include
        elif option.exclude:
            field_names = set(field_names) - option.exclude

        for name in field_names:
            field = target_instance.__fields__[name]
            if context["__by_alias"]:
                key = field.serialization_alias or field.effective_name
            else:
                key = name

            try:
                value = field.__get__(target_instance, owner=instance_type)
                if value is EMPTY:
                    continue

                if isinstance(value, Dataclass):
                    if option.depth is not None and current_depth >= option.depth:
                        serialized_output.append((key, value))
                        continue

                    nested_output = []
                    serialized_output.append((key, nested_output))
                    stack.appendleft(
                        (
                            value,
                            name,
                            current_depth + 1,
                            nested_output,
                        )
                    )
                else:
                    if (
                        isinstance(value, (Sequence, set))
                        and option.depth is not None
                        and current_depth >= option.depth
                    ):
                        serialized_output.append((key, value))
                        continue

                    serialized_value = field.serialize(
                        value,
                        fmt=fmt,
                        context=context,
                    )
                    serialized_output.append((key, serialized_value))

            except (DeserializationError, SerializationError, ValidationError) as exc:
                if context["__fail_fast"]:
                    raise SerializationError.from_exception(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[parent_name],
                    ) from exc
                if error is None:
                    error = SerializationError.from_exception(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[parent_name],
                    )
                else:
                    error.add(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[parent_name],
                    )

    if error:
        raise error
    return tuple(serialized_items)


@functools.lru_cache(maxsize=128)
def Options(*options: Option) -> OptionsMap:
    """
    Process a variable number of serialization `Option` instances into a mapping.

    :param options: Variable number of `Option` instances.
    :return: A mapping of dataclass types to their corresponding `Option` instances.
    """
    options_map: OptionsMap = {}
    for option in options:
        if option.target in options_map:
            raise ValueError(
                f"Duplicate option for target dataclass: {option.target.__name__}"
            )
        if option.include and option.exclude:
            raise ValueError(
                "Cannot specify both 'include' and 'exclude' in the same Option."
            )

        target_fields = set(option.target.base_to_effective_name_map.keys())
        if option.include and option.target is not Dataclass:
            unknown_fields = option.include - target_fields
            if unknown_fields:
                raise ValueError(
                    f"Some included fields are not present in {option.target.__name__} - {', '.join(unknown_fields)}"
                )
        elif option.exclude and option.target is not Dataclass:
            unknown_fields = option.exclude - target_fields
            if unknown_fields:
                raise ValueError(
                    f"Some excluded fields are not present in {option.target.__name__} - {', '.join(unknown_fields)}"
                )
        options_map[option.target] = option

    return options_map


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Literal["python"] = ...,
    options: typing.Optional[OptionsMap] = ...,
    context: typing.Optional[Context] = ...,
    astuple: typing.Literal[False] = ...,
    fail_fast: bool = ...,
    by_alias: bool = ...,
    exclude_unset: bool = ...,
) -> DataDict: ...


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Literal["json"] = ...,
    options: typing.Optional[OptionsMap] = ...,
    context: typing.Optional[Context] = ...,
    astuple: typing.Literal[False] = ...,
    fail_fast: bool = ...,
    by_alias: bool = ...,
    exclude_unset: bool = ...,
) -> JSONDict: ...


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = ...,
    options: typing.Optional[OptionsMap] = ...,
    context: typing.Optional[Context] = ...,
    fail_fast: bool = ...,
    by_alias: bool = ...,
    exclude_unset: bool = ...,
) -> DataDict: ...


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = ...,
    options: typing.Optional[OptionsMap] = ...,
    astuple: typing.Literal[False],
    context: typing.Optional[Context] = ...,
    fail_fast: bool = ...,
    by_alias: bool = ...,
    exclude_unset: bool = ...,
) -> DataDict: ...


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Literal["python"],
    options: typing.Optional[OptionsMap] = ...,
    astuple: typing.Literal[True],
    context: typing.Optional[Context] = ...,
    fail_fast: bool = ...,
    by_alias: bool = ...,
    exclude_unset: bool = ...,
) -> NamedDataTuple: ...


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Literal["json"],
    options: typing.Optional[OptionsMap] = ...,
    astuple: typing.Literal[True],
    context: typing.Optional[Context] = ...,
    fail_fast: bool = ...,
    by_alias: bool = ...,
    exclude_unset: bool = ...,
) -> JSONNamedDataTuple: ...


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = ...,
    options: typing.Optional[OptionsMap] = ...,
    astuple: typing.Literal[True],
    context: typing.Optional[Context] = ...,
    fail_fast: bool = ...,
    by_alias: bool = ...,
    exclude_unset: bool = ...,
) -> NamedDataTuple: ...


def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = "python",
    options: typing.Optional[OptionsMap] = None,
    astuple: bool = False,
    context: typing.Optional[Context] = None,
    fail_fast: bool = False,
    by_alias: bool = False,
    exclude_unset: bool = False,
) -> typing.Union[DataDict, JSONDict, NamedDataTuple, JSONNamedDataTuple]:
    """
    Build a serialized representation of the dataclass.

    :param obj: The dataclass instance to serialize.
    :param fmt: The format to serialize to. Can be 'python' or 'json' or any other
        custom format supported by the fields of the instance.

    :param options: Optional serialization options for the dataclass.
    :param context: Optional context for serialization. This can be used to pass
        additional information to the serialization process.

    :param astuple: If True, serialize as a tuple of (name, value) pairs.
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

    class Person(attrib.Dataclass):
        name = attrib.String()
        age = attrib.Integer()
        email = attrib.String()
        phone = PhoneNumber(serialization_alias="phone_number")
        address = attrib.String()

    john = Person(
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
    context["__astuple"] = astuple
    context["__options"] = options or {}
    context["__fail_fast"] = fail_fast
    context["__by_alias"] = by_alias
    context["__exclude_unset"] = exclude_unset
    if astuple:
        return _serialize_instance_asnamedtuple(
            fmt,
            instance=obj,
            context=context,
        )
    return _serialize_instance_asdict(
        fmt,
        instance=obj,
        context=context,
    )
