"""Dataclass serialization module."""

from collections import deque
import typing
import os
from annotated_types import Ge, MinLen
from typing_extensions import Annotated

from attrib._typing import EMPTY
from attrib.exceptions import SerializationError
from attrib.dataclass import Dataclass


SERIALIZATION_STYLE: typing.Union[str, typing.Literal["recursive", "iterative"]] = (
    os.getenv("ATTRIB_SERIALIZATION_STYLE", "iterative").strip().lower()
)
"""
`attrib` global serialization style setting. Can be either "recursive" or "iterative".

Use "iterative" for large or deeply nested dataclass serialization to improve performance and memory efficiency.
Use "recursive" for smaller or less complex dataclass serialization.

Default is "iterative".
This setting can also be overridden by the `ATTRIB_SERIALIZATION_STYLE` environment variable.
"""


class Option(typing.NamedTuple):
    """Dataclass serialization options."""

    target: typing.Type[Dataclass] = Dataclass
    """Target dataclass type for serialization."""
    depth: Annotated[typing.Optional[int], Ge(0)] = None
    """Depth for nested serialization."""
    include: typing.Optional[Annotated[typing.Set[str], MinLen(1)]] = None
    """Fields to include in serialization."""
    exclude: typing.Optional[Annotated[typing.Set[str], MinLen(1)]] = None
    """Fields to exclude from serialization."""
    strict: bool = False
    """If False, instances of subclasses of the target class will be serialized using this
    option, if no option is defined specifically for them. If True, only direct instances of the target class will be serialized.
    """

    def __hash__(self) -> int:
        return hash(
            (
                self.target,
                self.depth,
                self.include,
                self.exclude,
                self.strict,
            )
        )


DEFAULT_OPTION = Option()

OptionsMap: typing.TypeAlias = typing.MutableMapping[typing.Type[Dataclass], Option]


def resolve_option(
    dataclass_: typing.Type[Dataclass],
    options_map: OptionsMap,
) -> Option:
    """Find the most appropriate Option for a given dataclass type, with local caching."""
    for base in dataclass_.__mro__[:-1]:
        option = options_map.get(base, None)
        if not option or (option.strict and base is not dataclass_):
            continue
        return option

    return DEFAULT_OPTION


def _serialize_instance_asdict_recursive(
    fmt: str,
    instance: Dataclass,
    options_map: typing.Optional[OptionsMap] = None,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Dict[str, typing.Any]:
    """
    Recursively serialize a dataclass instance.

    :param fmt: Serialization format (e.g., 'python', 'json').
    :param instance: The dataclass instance to serialize.
    :param options_map: Optional serialization options map.
    :param context: Optional context dictionary.
    :return: Serialized dictionary.
    :raises SerializationError: If serialization fails.
    """
    serialized_data = {}
    instance_type = type(instance)

    if options_map is None:
        option = DEFAULT_OPTION
        options_map = {}
    elif instance_type in options_map:
        option = options_map[instance_type]
    else:
        option = resolve_option(instance_type, options_map)
        options_map[instance_type] = option  # Cache resolved option

    field_names = instance.__fields__.keys()
    if option.include:
        field_names = set(field_names) & option.include
    elif option.exclude:
        field_names = set(field_names) - option.exclude

    if context is None:
        context = {}
    if "__options" not in context:
        context["__options"] = options_map

    current_depth = context.get("__depth", 0)

    for name in field_names:
        field = instance.__fields__[name]
        key = field.effective_name

        try:
            value = field.__get__(instance, owner=type(instance))
            if value is EMPTY:
                continue

            if isinstance(value, Dataclass):
                if option.depth is not None and current_depth >= option.depth:
                    serialized_data[key] = value
                    continue

                nested_option = Option(
                    target=type(value),
                    depth=option.depth,
                    include=option.include,
                    exclude=option.exclude,
                    strict=option.strict,
                )
                options_map[type(value)] = nested_option
                nested_context = context.copy()
                nested_context["__depth"] = current_depth + 1

                serialized_data[key] = _serialize_instance_asdict_recursive(
                    fmt=fmt,
                    instance=value,
                    options_map=options_map,
                    context=nested_context,
                )
            else:
                serialized_data[key] = field.serialize(
                    value,
                    fmt=fmt,
                    context=context,
                )
        except (TypeError, ValueError) as exc:
            raise SerializationError(
                f"Failed to serialize '{type(instance).__name__}.{key}'.",
                key,
            ) from exc

    return serialized_data


def _serialize_instance_asdict_iterative(
    fmt: str,
    instance: Dataclass,
    options_map: typing.Optional[OptionsMap] = None,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Dict[str, typing.Any]:
    """
    Iteratively serialize a dataclass instance.

    *Significantly faster and memory efficient than recursive serialization for*
    *large/deeply nested dataclass serialization.*

    :param obj: The dataclass instance to serialize.
    :param fmt: Serialization format (e.g., 'python', 'json').
    :param options: Optional serialization options.
    :param context: Optional context dictionary.
    :return: Serialized dictionary.
    :raises SerializationError: If serialization fails.
    """
    try:
        serialized_data = {}
        stack = deque([(instance, 0, serialized_data)])

        if context is None:
            context = {}
        if "__options" not in context:
            context["__options"] = options_map

        local_options_map = options_map or {}

        while stack:
            current_instance, current_depth, current_output = stack.pop()
            instance_type = type(current_instance)

            if instance_type in local_options_map:
                option = local_options_map[instance_type]
            else:
                option = resolve_option(instance_type, local_options_map)
                local_options_map[instance_type] = option  # Cache resolved option

            field_names = current_instance.__fields__.keys()
            if option.include:
                field_names = set(field_names) & option.include
            elif option.exclude:
                field_names = set(field_names) - option.exclude

            for name in field_names:
                field = current_instance.__fields__[name]
                key = field.effective_name

                try:
                    value = field.__get__(current_instance, owner=instance_type)
                    if value is EMPTY:
                        continue

                    if isinstance(value, Dataclass):
                        if option.depth is not None and current_depth >= option.depth:
                            current_output[key] = value
                            continue

                        nested_output = {}
                        current_output[key] = nested_output
                        stack.appendleft((value, current_depth + 1, nested_output))
                    else:
                        current_output[key] = field.serialize(
                            value, fmt=fmt, context=context
                        )

                except (TypeError, ValueError) as exc:
                    raise SerializationError(
                        f"Failed to serialize '{type(current_instance).__name__}.{key}'.",
                        key,
                    ) from exc
    except (TypeError, ValueError) as exc:
        raise SerializationError(
            f"Failed to serialize '{type(instance).__name__}'.", exc
        ) from exc

    return serialized_data


def _serialize_instance_asnamedtuple_recursive(
    fmt: str,
    instance: Dataclass,
    options_map: typing.Optional[OptionsMap] = None,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Tuple[typing.Tuple[str, typing.Any], ...]:
    """
    Recursively serialize a dataclass instance into a tuple of (name, value) pairs.

    :param fmt: Serialization format (e.g., 'python', 'json').
    :param instance: The dataclass instance to serialize.
    :param options_map: Optional serialization options map.
    :param context: Optional context dictionary.
    :return: Serialized tuple of (name, value) pairs.
    :raises SerializationError: If serialization fails.
    """
    instance_type = type(instance)

    if options_map is None:
        option = DEFAULT_OPTION
        options_map = {}
    elif instance_type in options_map:
        option = options_map[instance_type]
    else:
        option = resolve_option(instance_type, options_map)
        options_map[instance_type] = option  # Cache resolved option

    field_names = instance.__fields__.keys()
    if option.include:
        field_names = [fn for fn in field_names if fn in option.include]
    elif option.exclude:
        field_names = [fn for fn in field_names if fn not in option.exclude]

    if context is None:
        context = {}
    if "__options" not in context:
        context["__options"] = options_map
    if "__astuple" not in context:
        context["__astuple"] = True

    current_depth = context.get("__depth", 0)

    serialized_items = []

    for name in field_names:
        field = instance.__fields__[name]
        key = field.effective_name
        try:
            value = field.__get__(instance, owner=type(instance))
            if value is EMPTY:
                continue

            if isinstance(value, Dataclass):
                if option.depth is not None and current_depth >= option.depth:
                    serialized_items.append((key, value))
                    continue

                nested_option = Option(
                    target=type(value),
                    depth=option.depth,
                    include=option.include,
                    exclude=option.exclude,
                    strict=option.strict,
                )
                options_map[type(value)] = nested_option
                nested_context = context.copy()
                nested_context["__depth"] = current_depth + 1

                nested = _serialize_instance_asnamedtuple_recursive(
                    fmt=fmt,
                    instance=value,
                    options_map=options_map,
                    context=nested_context,
                )
                serialized_items.append((key, nested))
            else:
                serialized_value = field.serialize(
                    value,
                    fmt=fmt,
                    context=context,
                )
                serialized_items.append((key, serialized_value))
        except (TypeError, ValueError) as exc:
            raise SerializationError(
                f"Failed to serialize '{type(instance).__name__}.{key}'.",
                key,
            ) from exc

    return tuple(serialized_items)


def _serialize_instance_asnamedtuple_iterative(
    fmt: str,
    instance: Dataclass,
    options_map: typing.Optional[OptionsMap] = None,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Tuple[typing.Tuple[str, typing.Any], ...]:
    """
    Iteratively serialize a dataclass instance into a tuple of (name, value) pairs.

    *Significantly faster and memory efficient than recursive serialization for*
    *large/deeply nested dataclass serialization.*

    :param instance: The dataclass instance to serialize.
    :param fmt: Serialization format (e.g., 'python', 'json').
    :param options_map: Optional serialization options.
    :param context: Optional context dictionary.
    :return: Serialized tuple of (name, value) pairs.
    :raises SerializationError: If serialization fails.
    """
    try:
        serialized_items = []
        stack = deque([(instance, 0, serialized_items)])
        context = context or {}
        if "__options" not in context:
            context["__options"] = options_map
        if "__astuple" not in context:
            context["__astuple"] = True

        local_options_map = options_map or {}

        while stack:
            current_instance, current_depth, current_output = stack.pop()
            instance_type = type(current_instance)

            if instance_type in local_options_map:
                option = local_options_map[instance_type]
            else:
                option = resolve_option(instance_type, local_options_map)
                local_options_map[instance_type] = option

            field_names = list(current_instance.__fields__.keys())
            if option.include:
                field_names = [fn for fn in field_names if fn in option.include]
            elif option.exclude:
                field_names = [fn for fn in field_names if fn not in option.exclude]

            for name in field_names:
                field = current_instance.__fields__[name]
                key = field.effective_name

                try:
                    value = field.__get__(current_instance, owner=instance_type)
                    if value is EMPTY:
                        continue

                    if isinstance(value, Dataclass):
                        if option.depth is not None and current_depth >= option.depth:
                            current_output.append((key, value))
                            continue

                        nested_output = []
                        current_output.append((key, nested_output))
                        stack.appendleft((value, current_depth + 1, nested_output))
                    else:
                        serialized_value = field.serialize(
                            value,
                            fmt=fmt,
                            context=context,
                        )
                        current_output.append((key, serialized_value))

                except (TypeError, ValueError) as exc:
                    raise SerializationError(
                        f"Failed to serialize '{type(current_instance).__name__}.{key}'.",
                        key,
                    ) from exc
    except (TypeError, ValueError) as exc:
        raise SerializationError(
            f"Failed to serialize '{type(instance).__name__}'.", exc
        ) from exc

    return tuple(serialized_items)


if SERIALIZATION_STYLE == "recursive":
    serialize_instance_asdict = _serialize_instance_asdict_recursive
    serialize_instance_asnamedtuple = _serialize_instance_asnamedtuple_recursive
else:
    serialize_instance_asdict = _serialize_instance_asdict_iterative
    serialize_instance_asnamedtuple = _serialize_instance_asnamedtuple_iterative


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = ...,
    options: typing.Optional[typing.Iterable[Option]] = ...,
    context: typing.Optional[typing.Dict[str, typing.Any]] = ...,
) -> typing.Dict[str, typing.Any]: ...


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = ...,
    options: typing.Optional[typing.Iterable[Option]] = ...,
    astuple: typing.Literal[False],
    context: typing.Optional[typing.Dict[str, typing.Any]] = ...,
) -> typing.Dict[str, typing.Any]: ...


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = ...,
    options: typing.Optional[typing.Iterable[Option]] = ...,
    astuple: typing.Literal[True],
    context: typing.Optional[typing.Dict[str, typing.Any]] = ...,
) -> typing.Tuple[typing.Tuple[str, typing.Any], ...]: ...


def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = "python",
    options: typing.Optional[typing.Iterable[Option]] = None,
    astuple: bool = False,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Union[
    typing.Dict[str, typing.Any], typing.Tuple[typing.Tuple[str, typing.Any], ...]
]:
    """
    Build a serialized representation of the dataclass.

    :param obj: The dataclass instance to serialize.
    :param fmt: The format to serialize to. Can be 'python' or 'json' or any other
        custom format supported by the fields of the instance.
    :param options: Optional serialization options for the dataclass.
    :param context: Optional context for serialization. This can be used to pass
        additional information to the serialization process.
    :return: A serialized representation of the dataclass.
    :raises SerializationError: If serialization fails.

    Example:
    ```python
    import attrib

    class Person(attrib.Dataclass):
        name = attrib.String()
        age = attrib.Integer()
        email = attrib.String()
        phone = attrib.String()
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
        options=[
            Option(target=Person, include={"name", "age"}),
        ],
    )
    print(data)
    # Output:
    # {
    #     "name": "John Doe",
    #     "age": 30
    # }
    ```
    """
    try:
        options_map = None
        if options:
            options_map = {option.target: option for option in options}

        if astuple:
            return serialize_instance_asnamedtuple(
                fmt,
                instance=obj,
                options_map=options_map,
                context=context,
            )

        return serialize_instance_asdict(
            fmt,
            instance=obj,
            options_map=options_map,
            context=context,
        )
    except (TypeError, ValueError) as exc:
        raise SerializationError(
            f"Failed to serialize '{obj.__class__.__name__}'.", exc
        ) from exc
