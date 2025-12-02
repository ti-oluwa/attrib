import copy
import functools
import sys
import typing
from itertools import count

import annotated_types as annot
from typing_extensions import Annotated, TypeAlias, Unpack

from attrib._field import field as _field
from attrib._utils import is_iterable
from attrib.dataclasses import (
    Dataclass,
    DataclassTco,
    MetaConfig,
    _MetaConfigs,
    is_dataclass,
)
from attrib.descriptors.base import Field, FieldType
from attrib.exceptions import ConfigurationError
from attrib.types import EMPTY, T

__all__ = [
    "make",
    "modify",
    "define",
    "dataclass",
    "partial",
    "strict",
    "ordered",
    "hashable",
    "frozen",
]


def _make_dataclass(
    base_cls: typing.Type[DataclassTco],
    prefix: str,
    name: typing.Optional[str] = None,
    attributes: typing.Optional[typing.Dict[str, typing.Any]] = None,
    module: typing.Optional[str] = None,
    **meta_kwargs: typing.Any,
) -> typing.Type[DataclassTco]:
    """
    Make a new dataclass with a modified name and module.

    :param base_cls: The original dataclass to modify.
    :param prefix: Prefix to use for the new dataclass name.
    :param name: Optional name for the new dataclass. If not provided,
        the original dataclass name will be used with the prefix.
    :param attributes: Additional attributes to add to the new dataclass.
        This can include custom methods or properties.
    :param module: Optional module name for the new dataclass. If not provided,
        the original dataclass' module will be used.
    :param meta_kwargs: Additional keyword arguments to pass to the dataclass constructor/metaclass.
    :return: A new dataclass type with the specified prefix.
    """
    return typing.cast(
        typing.Type[DataclassTco],
        type(
            f"{prefix}{name or base_cls.__name__}",
            (base_cls,),
            {"__module__": module or base_cls.__module__, **(attributes or {})},
            **meta_kwargs,
        ),
    )


def make(
    name: str,
    fields: typing.Mapping[str, typing.Union[FieldType[T], Field[T]]],
    module: typing.Optional[str] = None,
    copy_fields: bool = False,
    **meta_kwargs: typing.Any,
) -> typing.Type[Dataclass]:
    """
    Dataclass factory.

    Make a new dataclass dynamically.

    :param name: Name of the new dataclass.
    :param fields: A dictionary mapping field names to their types or Field instances.
    :param module: Optional module name for the new dataclass.
    :param copy_fields: Whether to copy the Field instances or not.
    :param meta_kwargs: Additional keyword arguments to pass to the dataclass constructor/metaclass.
    :return: A new dataclass type.
    """
    attributes: typing.Dict[str, Field[typing.Any]] = {}
    for field_name, field_type in fields.items():  # type: ignore[misc]
        if isinstance(field_type, Field):
            if copy_fields:
                field = copy.copy(field_type)
            else:
                field = field_type
            field.name = None  # Reset name to None to avoid binding conflicts
            attributes[field_name] = field
        else:
            attributes[field_name] = _field(field_type)

    return _make_dataclass(
        Dataclass,
        prefix="",
        name=name,
        attributes=attributes,
        module=module or "__dynamic__",
        **meta_kwargs,
    )


AttributeValue: TypeAlias = typing.Union[T, typing.Iterator[T]]
FieldSelector: TypeAlias = typing.Callable[[str, Field[typing.Any]], bool]


class _GenericFieldAttrs(typing.TypedDict, total=False):
    """
    Generic attributes that can be modified for fields in a dataclass.

    Each attribute corresponds to a field attribute in a dataclass.
    The values can be either a single value or an iterator that yields values.
    This allows for dynamic modification of field attributes when creating a new dataclass.
    """

    strict: AttributeValue[bool]
    fail_fast: AttributeValue[bool]
    allow_null: AttributeValue[bool]
    required: AttributeValue[bool]
    always_coerce: AttributeValue[bool]
    skip_validator: AttributeValue[bool]
    hash: AttributeValue[bool]
    repr: AttributeValue[bool]
    init: AttributeValue[bool]
    eq: AttributeValue[bool]
    order: typing.Optional[AttributeValue[Annotated[int, annot.Ge(0)]]]


__allowed_modifications = set(_GenericFieldAttrs.__annotations__.keys())


@typing.overload
def modify(
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    selector: typing.Optional[FieldSelector] = ...,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = ...,
    **modifications: Unpack[_GenericFieldAttrs],
) -> typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]]: ...


@typing.overload
def modify(
    datacls: typing.Type[DataclassTco],
    /,
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    selector: typing.Optional[FieldSelector] = ...,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = ...,
    **modifications: Unpack[_GenericFieldAttrs],
) -> typing.Type[DataclassTco]: ...


@typing.overload
def modify(
    datacls: None = ...,
    /,
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    selector: typing.Optional[FieldSelector] = ...,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = ...,
    **modifications: Unpack[_GenericFieldAttrs],
) -> typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]]: ...


def modify(
    datacls: typing.Optional[typing.Type[DataclassTco]] = None,
    /,
    *,
    prefix: typing.Optional[str] = None,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
    selector: typing.Optional[FieldSelector] = None,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None,
    **modifications: Unpack[_GenericFieldAttrs],
) -> typing.Union[
    typing.Type[DataclassTco],
    typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]],
]:
    """
    Dataclass decorator.

    Returns a new dataclass with specific fields and attributes modified.

    This is especially useful if you need a dataclass with specific field behavior,
    but do not want to redefine an entirely new dataclass for that purpose.

    :param datacls: Target dataclass to be modified.
    :param prefix: Prefix to prepend to the new dataclass' name. Default is None.
        Not providing a prefix may mean that the new/modified dataclass
        will overwrite the original dataclass in the module namespace.

    :param include: Iterable of fields to include for modification.
    :param exclude: Iterable of fields to exclude from modification.

    Note: `include` and `exclude` are mutually exclusive.

    :param selector: A callable that takes a field name and a Field instance,
        and returns True if the field should be included for modification.
        This allows for more complex selection logic based on field attributes,
        after the `include` and `exclude` filters have been applied.

    :param meta_kwargs: Additional keyword arguments to pass to the dataclass
        constructor/metaclass for creating a new dataclass type.

    :param modifications: Generic field attributes to modify.
        This can include 'strict', 'lazy', etc.

    :return: A new dataclass type with the specified modifications applied.
    """
    if not modifications and not meta_kwargs:
        raise ConfigurationError(
            "No modifications can be applied. At least one field attribute or meta-configuration must be specified."
        )
    if not __allowed_modifications.issuperset(modifications.keys()):
        raise ConfigurationError(
            f"Invalid field attributes provided: {set(modifications.keys()) - __allowed_modifications}. "
            "Allowed attributes are: "
            f"{__allowed_modifications}."
        )

    def decorator(
        datacls: typing.Type[DataclassTco],
    ) -> typing.Type[DataclassTco]:
        if include and exclude:
            raise ConfigurationError(
                "Cannot use both 'include' and 'exclude' options at the same time."
            )
        if selector and (include or exclude):
            raise ConfigurationError(
                "Cannot use 'selector' with 'include' or 'exclude' options at the same time."
            )

        cls_fields = datacls.__dataclass_fields__
        field_names = cls_fields.keys()
        if include:
            include_set = set(include)
            field_names = [name for name in field_names if name in include_set]
        elif exclude:
            exclude_set = set(exclude)
            field_names = [name for name in field_names if name not in exclude_set]

        if selector:
            field_names = [
                name for name in field_names if selector(name, cls_fields[name])
            ]
        if not field_names and modifications:
            raise ConfigurationError(
                "No fields to modify. Either 'include' or 'exclude' must specify valid fields."
            )

        modified_fields = {}
        for field_name in field_names:
            field = copy.copy(cls_fields[field_name])
            for attr, value in modifications.items():
                if is_iterable(value):
                    try:
                        value = next(iter(value))
                    except StopIteration:
                        raise ConfigurationError(
                            f"The iterable provided for attribute '{attr}' was exhausted before all fields were processed."
                        ) from None

                if value and attr == "required":
                    field.default = EMPTY
                elif value and attr == "allow_null" and field.default is EMPTY:
                    field.default = None

                setattr(field, attr, value)

            field.name = None  # Reset name to None to avoid conflicts
            modified_fields[field_name] = field

        modified_cls = _make_dataclass(
            datacls,
            prefix=prefix or "",
            attributes=modified_fields,
            **(meta_kwargs or {}),
        )
        return modified_cls

    if datacls is not None:
        return decorator(datacls)
    return decorator


if sys.version_info >= (3, 9):
    _get_type_hints = functools.partial(typing.get_type_hints, include_extras=True)
else:
    _get_type_hints = typing.get_type_hints  # type: ignore[assignment]


def _extract_fields(
    cls: typing.Type[typing.Any], copy_fields: bool = True
) -> typing.Dict[str, Field[typing.Any]]:
    """
    Extract fields from type annotations in a class.

    :param cls: The class to extract fields from.
    :param copy_fields: Whether to copy the fields or not.
    :return: A dictionary of field names to Field instances.
    """
    fields: typing.Dict[str, Field[typing.Any]] = {}
    cls_attributes = vars(cls)
    annotations = _get_type_hints(cls)

    # Use __annotations__ to preserve definition order (Python 3.7+)
    # This dict maintains insertion order
    if hasattr(cls, "__annotations__"):
        # Start with annotated fields in their definition order
        seen = set()
        for name in cls.__annotations__:
            if name.startswith("__") and name.endswith("__"):
                continue

            seen.add(name)
            attr = cls_attributes.get(name)

            if isinstance(attr, Field):
                if copy_fields:
                    attr = copy.copy(attr)
                attr.name = None  # Reset name to None to avoid binding conflicts
                fields[name] = attr
            elif name in annotations:
                fields[name] = _field(annotations[name])

        # Add any remaining Field instances that weren't annotated
        # (in the order they appear in vars())
        for name, attr in cls_attributes.items():
            if name in seen or (name.startswith("__") and name.endswith("__")):
                continue
            if isinstance(attr, Field):
                if copy_fields:
                    attr = copy.copy(attr)
                attr.name = None  # Reset name to None to avoid binding conflicts
                fields[name] = attr
    else:
        # For classes without __annotations__
        for name, attr in cls_attributes.items():
            if name.startswith("__") and name.endswith("__"):
                continue
            if isinstance(attr, Field):
                if copy_fields:
                    attr = copy.copy(attr)
                attr.name = None  # Reset name to None to avoid binding conflicts
                fields[name] = attr

    return fields


@typing.overload
def define(
    cls: None, /
) -> typing.Callable[[typing.Type[typing.Any]], typing.Type[Dataclass]]: ...


@typing.overload
def define(cls: typing.Type[T], /) -> typing.Type[Dataclass]: ...


@typing.overload
def define(
    **meta_kwargs: Unpack[_MetaConfigs],
) -> typing.Callable[[typing.Type[typing.Any]], typing.Type[Dataclass]]: ...


@typing.overload
def define(
    cls: typing.Type[T], /, **meta_kwargs: Unpack[_MetaConfigs]
) -> typing.Type[Dataclass]: ...


def define(
    cls: typing.Optional[typing.Type[T]] = None, /, **meta_kwargs: Unpack[_MetaConfigs]
) -> typing.Union[
    typing.Type[Dataclass], typing.Callable[[typing.Type[T]], typing.Type[Dataclass]]
]:
    """
    Class decorator.

    Converts a regular class with type annotations and fields into a dataclass.

    :param cls: The class to convert into a dataclass.
    :param meta_kwargs: Additional keyword arguments to pass to the dataclass constructor/metaclass.
    :return: The dataclass.

    Example:
        ```python
        import attrib

        @attrib.define(repr=True)
        class User:
            id: int
            name = attrib.field(str, max_length=100)

        user = User(id=1, name="Alice")
        print(user)
        # Output: User(id=1, name='Alice')
        ```
    """

    def _decorator(
        cls: typing.Type[T], **meta_kwargs: Unpack[_MetaConfigs]
    ) -> typing.Type[Dataclass]:
        if is_dataclass(cls):
            return cls  # type: ignore[return-value]

        # No need to copy fields here since we're creating from scratch
        # that is, fields defined in the class are mostly new `Field`
        # instances and not shared ones
        fields = _extract_fields(cls, copy_fields=False)
        if hasattr(cls, "__config__") and isinstance(cls.__config__, MetaConfig):  # type: ignore[attr-defined]
            meta_kwargs = {**cls.__config__._asdict(), **meta_kwargs}  # type: ignore[attr-defined]

        datacls = _make_dataclass(
            Dataclass,
            prefix="",
            name=cls.__name__,
            attributes=fields,
            module=cls.__module__,
            **meta_kwargs,
        )
        datacls.__doc__ = cls.__doc__
        return datacls

    if cls is not None:
        return _decorator(cls, **meta_kwargs)
    return functools.partial(_decorator, **meta_kwargs)


dataclass = define

##########################
# Convenience Decorators #
##########################

strict = functools.partial(modify, strict=True)
"""
Dataclass decorator.

Returns a dataclass with all or specific fields strict.
"""

hashable = functools.partial(
    modify, hash=True, meta_kwargs={"frozen": True, "hash": True}
)
"""
Dataclass decorator.

Returns a new dataclass with all or specific fields hashable.

This is useful for creating immutable dataclasses that can be used as dictionary keys or in sets.
"""


@typing.overload
def ordered(
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    selector: typing.Optional[FieldSelector] = ...,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = ...,
) -> typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]]: ...


@typing.overload
def ordered(
    datacls: typing.Type[DataclassTco],
    /,
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    selector: typing.Optional[FieldSelector] = ...,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = ...,
) -> typing.Type[DataclassTco]: ...


@typing.overload
def ordered(
    datacls: None = ...,
    /,
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    selector: typing.Optional[FieldSelector] = ...,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = ...,
) -> typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]]: ...


def ordered(
    datacls: typing.Optional[typing.Type[DataclassTco]] = None,
    /,
    *,
    prefix: typing.Optional[str] = None,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
    selector: typing.Optional[FieldSelector] = None,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Union[
    typing.Type[DataclassTco],
    typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]],
]:
    """
    Dataclass decorator.

    Returns a new dataclass with all or specific fields ordered.

    :param datacls: Target dataclass to be modified.
    :param prefix: Prefix to prepend to the new dataclass' name. Default is None.
        Not providing a prefix may mean that the new/modified dataclass
        will overwrite the original dataclass in the module namespace.

    :param include: Iterable of fields to include for modification.
    :param exclude: Iterable of fields to exclude from modification.

    Note: `include` and `exclude` are mutually exclusive.

    :param selector: A callable that takes a field name and a Field instance,
        and returns True if the field should be included for modification.
        This allows for more complex selection logic based on field attributes,
        after the `include` and `exclude` filters have been applied.

    :param meta_kwargs: Additional keyword arguments to pass to the dataclass
        constructor/metaclass for creating a new dataclass type.

    :return: A new dataclass type with the specified modifications applied.
    """
    decorator = modify(
        prefix=prefix,
        include=include,
        exclude=exclude,
        selector=selector,
        order=count(0, step=1),
        meta_kwargs={**(meta_kwargs or {}), "order": True},
    )
    if datacls is not None:
        return decorator(datacls)
    return decorator


partial = functools.partial(modify, required=False, allow_null=True)
"""
Dataclass decorator.

Returns a new dataclass with all or specific fields made optional.

```

import attrib

class QuestionSchema(attrib.Dataclass):
    question_text = attrib.String(max_length=200)
    options = attrib.List(
        child=attrib.String(max_length=100),
        min_length=2,
        max_length=5,
    )
    answer_index = attrib.Integer(min_value=0, max_value=4)
    hints = attrib.String(
        max_length=500,
        allow_null=True,
        default=None,
    )

class QuizSchema(attrib.Dataclass):
    title = attrib.String(max_length=100)
    description = attrib.String(max_length=500, allow_null=True)
    questions = attrib.List(
        child=attrib.Nested(QuestionSchema),
        min_length=1,
        max_length=10,
    )

UpdateQuizSchema = attrib.partial(QuizSchema, prefix="Update")
# Now UpdateQuizSchema has all fields as optional. Making it suitable for
# use in an update operation where not all fields need to be provided.

```
"""

frozen = functools.partial(modify, meta_kwargs={"frozen": True})
"""
Dataclass decorator.

Returns a new dataclass with all or specific fields frozen (immutable).
"""
