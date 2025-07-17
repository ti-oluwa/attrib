import functools
import typing
from typing_extensions import Unpack, Annotated, TypeAlias
from collections.abc import Iterator
import copy
import annotated_types as annot
from itertools import count

from attrib.types import EMPTY, T
from attrib.dataclass import DataclassTco
from attrib.descriptors.base import Field
from attrib.exceptions import ConfigurationError

__all__ = [
    "modify_cls",
    "partial",
    "strict",
    "lazy",
    "ordered",
    "hashable",
]


def _make_new_dataclass(
    dataclass_: typing.Type[DataclassTco],
    prefix: str,
    attributes: typing.Optional[typing.Dict[str, typing.Any]] = None,
    **meta_kwargs: typing.Any,
) -> typing.Type[DataclassTco]:
    """
    Create a new dataclass with a modified name and module.

    :param dataclass_: The original dataclass to modify_cls.
    :param prefix: Prefix to use for the new dataclass name.
    :param attributes: Additional attributes to add to the new dataclass.
        This can include custom methods or properties.
    :param meta_kwargs: Additional keyword arguments to pass to the dataclass constructor/metaclass.
    :return: A new dataclass type with the specified prefix.
    """
    return typing.cast(
        typing.Type[DataclassTco],
        type(
            f"{prefix}{dataclass_.__name__}",
            (dataclass_,),
            {"__module__": dataclass_.__module__, **(attributes or {})},
            **meta_kwargs,
        ),
    )


AttributeValue: TypeAlias = typing.Union[T, typing.Iterator[T]]


class GenericFieldAttributes(typing.TypedDict, total=False):
    """
    Generic attributes that can be modified for fields in a dataclass.

    Each attribute corresponds to a field attribute in a dataclass.
    The values can be either a single value or an iterator that yields values.
    This allows for dynamic modification of field attributes when creating a new dataclass.
    """

    strict: AttributeValue[bool]
    lazy: AttributeValue[bool]
    fail_fast: AttributeValue[bool]
    allow_null: AttributeValue[bool]
    required: AttributeValue[bool]
    always_coerce: AttributeValue[bool]
    check_coerced: AttributeValue[bool]
    skip_validator: AttributeValue[bool]
    hash: AttributeValue[bool]
    repr: AttributeValue[bool]
    init: AttributeValue[bool]
    eq: AttributeValue[bool]
    order: typing.Optional[AttributeValue[Annotated[int, annot.Ge(0)]]]


_allowed_modifications = set(GenericFieldAttributes.__annotations__.keys())


@typing.overload
def modify_cls(
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    selector: typing.Optional[typing.Callable[[str, Field[typing.Any]], bool]] = ...,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = ...,
    **modifications: Unpack[GenericFieldAttributes],
) -> typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]]: ...


@typing.overload
def modify_cls(
    dataclass_: typing.Type[DataclassTco],
    /,
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    selector: typing.Optional[typing.Callable[[str, Field[typing.Any]], bool]] = ...,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = ...,
    **modifications: Unpack[GenericFieldAttributes],
) -> typing.Type[DataclassTco]: ...


@typing.overload
def modify_cls(
    dataclass_: None = ...,
    /,
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    selector: typing.Optional[typing.Callable[[str, Field[typing.Any]], bool]] = ...,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = ...,
    **modifications: Unpack[GenericFieldAttributes],
) -> typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]]: ...


def modify_cls(
    dataclass_: typing.Optional[typing.Type[DataclassTco]] = None,
    /,
    *,
    prefix: typing.Optional[str] = None,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
    selector: typing.Optional[typing.Callable[[str, Field[typing.Any]], bool]] = None,
    meta_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None,
    **modifications: Unpack[GenericFieldAttributes],
) -> typing.Union[
    typing.Type[DataclassTco],
    typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]],
]:
    """
    Dataclass decorator.

    Returns a new dataclass with specific fields and attributes modified.

    This is especially useful if you need a dataclass with specific field behavior,
    but do not want to redefine an entirely new dataclass for that purpose.

    :param dataclass_: Target dataclass to be modified.
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
    if not modifications:
        raise ConfigurationError(
            "No modifications provided. At least one field attribute must be specified."
        )
    if not _allowed_modifications.issuperset(modifications.keys()):
        raise ConfigurationError(
            f"Invalid field attributes provided: {set(modifications.keys()) - _allowed_modifications}. "
            "Allowed attributes are: "
            f"{_allowed_modifications}."
        )

    def decorator(
        dataclass_: typing.Type[DataclassTco],
    ) -> typing.Type[DataclassTco]:
        if include and exclude:
            raise ConfigurationError(
                "Cannot use both 'include' and 'exclude' options at the same time."
            )

        cls_fields = dataclass_.__dataclass_fields__
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
        if not field_names:
            raise ConfigurationError(
                "No fields to modify_cls. Either 'include' or 'exclude' must specify valid fields."
            )

        modified_fields = {}
        for field_name in field_names:
            field = copy.copy(cls_fields[field_name])
            for attr, value in modifications.items():
                if isinstance(value, Iterator):
                    value = next(value)

                if value and attr == "required":
                    field.default = EMPTY
                elif value and attr == "allow_null" and field.default is EMPTY:
                    field.default = None

                setattr(field, attr, value)

            field.name = None  # Reset name to None to avoid conflicts
            modified_fields[field_name] = field

        modified_cls = _make_new_dataclass(
            dataclass_,
            prefix=prefix or "",
            attributes=modified_fields,
            **(meta_kwargs or {}),
        )
        return modified_cls

    if dataclass_ is not None:
        return decorator(dataclass_)
    return decorator


##########################
# Convenience Decorators #
##########################

strict = functools.partial(modify_cls, strict=True)
"""
Dataclass decorator.

Returns a dataclass with all or specific fields strict.
"""

lazy = functools.partial(modify_cls, lazy=True)
"""
Dataclass decorator.

Returns a dataclass with all or specific fields lazy.
"""

hashable = functools.partial(
    modify_cls,
    hash=True,
    meta_kwargs={
        "frozen": True,
        "hash": True,
    },
)
"""
Dataclass decorator.

Returns a new dataclass with all or specific fields hashable.

This is useful for creating immutable dataclasses that can be used as dictionary keys or in sets.
"""

ordered = functools.partial(
    modify_cls, order=count(0, step=1), meta_kwargs={"order": True}
)
"""
Dataclass decorator.

Returns a new dataclass with all or specific fields ordered.
"""

partial = functools.partial(modify_cls, required=False, allow_null=True)
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
