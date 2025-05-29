"""Dataclass serialization module."""

from collections import deque
import functools
import typing
import os
from annotated_types import Ge, MinLen
from typing_extensions import Annotated

from attrib._typing import EMPTY
from attrib.exceptions import DetailedError, SerializationError
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


def _serialize_instance_asdict_recursive(
    fmt: str,
    instance: Dataclass,
    options: typing.Optional[OptionsMap] = None,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    fail_fast: bool = False,
) -> typing.Dict[str, typing.Any]:
    """
    Recursively serialize a dataclass instance.

    :param fmt: Serialization format (e.g., 'python', 'json').
    :param instance: The dataclass instance to serialize.
    :param options: Optional serialization options map.
    :param context: Optional context dictionary.
    :param fail_fast: If True, serialization will stop at the first error encountered.
    :return: Serialized dictionary.
    :raises SerializationError: If serialization fails.
    """
    serialized_data = {}
    instance_type = type(instance)
    if context is None:
        context = {}
    if "__options" not in context:
        context["__options"] = options or {}
    if "__fail_fast" not in context:
        context["__fail_fast"] = fail_fast
    if "__depth" not in context:
        context["__depth"] = 0

    local_options = context["__options"]
    if instance_type in local_options:
        option = local_options[instance_type]
    else:
        option = resolve_option(instance_type, local_options)
        local_options[instance_type] = option  # Cache resolved option

    field_names = instance.__fields__.keys()
    if option.include:
        field_names = set(field_names) & option.include
    elif option.exclude:
        field_names = set(field_names) - option.exclude

    error = None
    for name in field_names:
        field = instance.__fields__[name]
        key = field.effective_name

        try:
            value = field.__get__(instance, owner=instance_type)
            if value is EMPTY:
                continue
            
            if isinstance(value, Dataclass):
                current_depth = context["__depth"]
                if option.depth is not None and current_depth >= option.depth:
                    serialized_data[key] = value
                    continue
                
                context["__depth"] += 1 # Next level is one deeper
                serialized_data[key] = _serialize_instance_asdict_recursive(
                    fmt=fmt,
                    instance=value,
                    options=options,
                    context=context,
                )
            else:
                serialized_data[key] = field.serialize(
                    value,
                    fmt=fmt,
                    context=context,
                )
        except (TypeError, ValueError, DetailedError) as exc:
            if context["__fail_fast"]:
                raise SerializationError.from_exception(
                    exc,
                    parent_name=instance_type.__name__,
                    expected_type=field.typestr,
                    location=[key],
                )
            if error is None:
                error = SerializationError.from_exception(
                    exc,
                    parent_name=instance_type.__name__,
                    expected_type=field.typestr,
                    location=[key],
                )
            else:
                error.add(
                    exc,
                    parent_name=instance_type.__name__,
                    expected_type=field.typestr,
                    location=[key],
                )
    if error:
        raise error
    return serialized_data


def _serialize_instance_asdict_iterative(
    fmt: str,
    instance: Dataclass,
    options: typing.Optional[OptionsMap] = None,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    fail_fast: bool = False,
) -> typing.Dict[str, typing.Any]:
    """
    Iteratively serialize a dataclass instance.

    *Significantly faster and memory efficient than recursive serialization for*
    *large/deeply nested dataclass serialization.*

    :param obj: The dataclass instance to serialize.
    :param fmt: Serialization format (e.g., 'python', 'json').
    :param options: Optional serialization options.
    :param context: Optional context dictionary.
    :param fail_fast: If True, serialization will stop at the first error encountered.
    :return: Serialized dictionary.
    :raises SerializationError: If serialization fails.
    """
    serialized_data = {}
    stack = deque([(instance, 0, serialized_data)])  # Add path tracking

    if context is None:
        context = {}
    if "__options" not in context:
        context["__options"] = options or {}
    if "__fail_fast" not in context:
        context["__fail_fast"] = fail_fast

    local_options = context["__options"]
    error = None

    while stack:
        current_instance, current_depth, current_output = stack.pop()
        instance_type = type(current_instance)

        if instance_type in local_options:
            option = local_options[instance_type]
        else:
            option = resolve_option(instance_type, local_options)
            local_options[instance_type] = option  # Cache resolved option

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
                    stack.appendleft(
                        (value, current_depth + 1, nested_output)
                    )
                else:
                    current_output[key] = field.serialize(
                        value, fmt=fmt, context=context
                    )

            except (TypeError, ValueError, DetailedError) as exc:
                if context["__fail_fast"]:
                    raise SerializationError.from_exception(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[name],
                    )
                if error is None:
                    error = SerializationError.from_exception(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[name],
                    )
                else:
                    error.add(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[name],
                    )

    if error:
        raise error
    return serialized_data


def _serialize_instance_asnamedtuple_recursive(
    fmt: str,
    instance: Dataclass,
    options: typing.Optional[OptionsMap] = None,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    fail_fast: bool = False,
) -> typing.Tuple[typing.Tuple[str, typing.Any], ...]:
    """
    Recursively serialize a dataclass instance into a tuple of (name, value) pairs.

    :param fmt: Serialization format (e.g., 'python', 'json').
    :param instance: The dataclass instance to serialize.
    :param options: Optional serialization options map.
    :param context: Optional context dictionary.
    :param fail_fast: If True, serialization will stop at the first error encountered.
    :return: Serialized tuple of (name, value) pairs.
    :raises SerializationError: If serialization fails.
    """
    instance_type = type(instance)

    if context is None:
        context = {}
    if "__options" not in context:
        context["__options"] = options or {}
    if "__fail_fast" not in context:
        context["__fail_fast"] = fail_fast
    if "__astuple" not in context:
        context["__astuple"] = True
    if "__depth" not in context:
        context["__depth"] = 0

    local_options = context["__options"]
    if instance_type in local_options:
        option = local_options[instance_type]
    else:
        option = resolve_option(instance_type, local_options)
        local_options[instance_type] = option  # Cache resolved option

    field_names = instance.__fields__.keys()
    if option.include:
        field_names = [name for name in field_names if name in option.include]
    elif option.exclude:
        field_names = [name for name in field_names if name not in option.exclude]

    serialized_items = []
    error = None

    for name in field_names:
        field = instance.__fields__[name]
        key = field.effective_name
        try:
            value = field.__get__(instance, owner=type(instance))
            if value is EMPTY:
                continue

            if isinstance(value, Dataclass):
                current_depth = context["__depth"]
                if option.depth is not None and current_depth >= option.depth:
                    serialized_items.append((key, value))
                    continue

                context["__depth"] += 1  # Next level is one deeper
                nested = _serialize_instance_asnamedtuple_recursive(
                    fmt=fmt,
                    instance=value,
                    options=options,
                    context=context,
                    fail_fast=fail_fast,
                )
                serialized_items.append((key, nested))
            else:
                serialized_value = field.serialize(
                    value,
                    fmt=fmt,
                    context=context,
                )
                serialized_items.append((key, serialized_value))
        except (TypeError, ValueError, DetailedError) as exc:
            if context["__fail_fast"]:
                raise SerializationError.from_exception(
                    exc,
                    parent_name=instance_type.__name__,
                    expected_type=field.typestr,
                    location=[key],
                )
            if error is None:
                error = SerializationError.from_exception(
                    exc,
                    parent_name=instance_type.__name__,
                    expected_type=field.typestr,
                    location=[key],
                )
            else:
                error.add(
                    exc,
                    parent_name=instance_type.__name__,
                    expected_type=field.typestr,
                    location=[key],
                )

    if error:
        raise error
    return tuple(serialized_items)


def _serialize_instance_asnamedtuple_iterative(
    fmt: str,
    instance: Dataclass,
    options: typing.Optional[OptionsMap] = None,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    fail_fast: bool = False,
) -> typing.Tuple[typing.Tuple[str, typing.Any], ...]:
    """
    Iteratively serialize a dataclass instance into a tuple of (name, value) pairs.

    *Significantly faster and memory efficient than recursive serialization for*
    *large/deeply nested dataclass serialization.*

    :param instance: The dataclass instance to serialize.
    :param fmt: Serialization format (e.g., 'python', 'json').
    :param options: Optional serialization options.
    :param context: Optional context dictionary.
    :param fail_fast: If True, serialization will stop at the first error encountered.
    :return: Serialized tuple of (name, value) pairs.
    :raises SerializationError: If serialization fails.
    """
    serialized_items = []
    stack = deque([(instance, 0, serialized_items)])  # Add path tracking

    if context is None:
        context = {}
    if "__options" not in context:
        context["__options"] = options or {}
    if "__fail_fast" not in context:
        context["__fail_fast"] = fail_fast
    if "__astuple" not in context:
        context["__astuple"] = True

    local_options = context["__options"]
    error = None

    while stack:
        current_instance, current_depth, current_output = stack.pop()
        instance_type = type(current_instance)

        if instance_type in local_options:
            option = local_options[instance_type]
        else:
            option = resolve_option(instance_type, local_options)
            local_options[instance_type] = option

        field_names = list(current_instance.__fields__.keys())
        if option.include:
            field_names = [name for name in field_names if name in option.include]
        elif option.exclude:
            field_names = [name for name in field_names if name not in option.exclude]

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
                    stack.appendleft(
                        (value, current_depth + 1, nested_output,)
                    )
                else:
                    serialized_value = field.serialize(
                        value,
                        fmt=fmt,
                        context=context,
                    )
                    current_output.append((key, serialized_value))

            except (TypeError, ValueError, DetailedError) as exc:
                if context["__fail_fast"]:
                    raise SerializationError.from_exception(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[name],
                    )
                if error is None:
                    error = SerializationError.from_exception(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[name],
                    )
                else:
                    error.add(
                        exc,
                        parent_name=instance_type.__name__,
                        expected_type=field.typestr,
                        location=[name],
                    )

    if error:
        raise error
    return tuple(serialized_items)


@functools.lru_cache(maxsize=128)
def Options(
    *options: Option,
) -> OptionsMap:
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

        target_fields = set(option.target.effective_to_base_name_map)
        if option.include:
            unknown_fields = option.include - target_fields
            if unknown_fields:
                raise ValueError(
                    f"Some included fields are not present in {option.target.__name__} - {', '.join(unknown_fields)}"
                )
        elif option.exclude:
            unknown_fields = option.exclude - target_fields
            if unknown_fields:
                raise ValueError(
                    f"Some excluded fields are not present in {option.target.__name__} - {', '.join(unknown_fields)}"
                )
        options_map[option.target] = option

    return options_map


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
    options: typing.Optional[OptionsMap] = ...,
    context: typing.Optional[typing.Dict[str, typing.Any]] = ...,
    fail_fast: bool = ...,
) -> typing.Dict[str, typing.Any]: ...


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = ...,
    options: typing.Optional[OptionsMap] = ...,
    astuple: typing.Literal[False],
    context: typing.Optional[typing.Dict[str, typing.Any]] = ...,
    fail_fast: bool = ...,
) -> typing.Dict[str, typing.Any]: ...


@typing.overload
def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = ...,
    options: typing.Optional[OptionsMap] = ...,
    astuple: typing.Literal[True],
    context: typing.Optional[typing.Dict[str, typing.Any]] = ...,
    fail_fast: bool = ...,
) -> typing.Tuple[typing.Tuple[str, typing.Any], ...]: ...


def serialize(
    obj: Dataclass,
    *,
    fmt: typing.Union[typing.Literal["python", "json"], str] = "python",
    options: typing.Optional[OptionsMap] = None,
    astuple: bool = False,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    fail_fast: bool = False,
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

    :param astuple: If True, serialize as a tuple of (name, value) pairs.
    :param fail_fast: If True, serialization will stop at the first error encountered.
        If False, it will collect all errors and raise a `SerializationError` at the end.

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
        options=attrib.Options(
            attrib.Option(exclude={"address"}),
        ),
    )
    print(data)
    # Output:
    # {
    #     "name": "John Doe",
    #     "age": 30,
    #     "email": "john.doe@example.com",
    #     "phone": "+1234567890",
    # }
    ```
    """
    if astuple:
        return serialize_instance_asnamedtuple(
            fmt,
            instance=obj,
            options=options,
            context=context,
            fail_fast=fail_fast,
        )

    return serialize_instance_asdict(
        fmt,
        instance=obj,
        options=options,
        context=context,
        fail_fast=fail_fast,
    )
