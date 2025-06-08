import functools
import typing
from typing_extensions import Unpack, Annotated, TypeAlias
from collections.abc import Iterator
import copy
import annotated_types as annot
from itertools import count

from attrib._typing import EMPTY, T
from attrib.dataclass import DataclassTco
from attrib.exceptions import ConfigurationError

__all__ = [
    "partial",
    "modify_fields",
    "strict",
    "lazy",
    "ordered",
]


def _make_new_dataclass(
    dataclass_: typing.Type[DataclassTco],
    prefix: str,
    attributes: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> typing.Type[DataclassTco]:
    """
    Create a new dataclass with a modified name and module.

    :param dataclass_: The original dataclass to modify.
    :param prefix: Prefix to use for the new dataclass name.
    :param attributes: Additional attributes to add to the new dataclass.
        This can include custom methods or properties.
    :return: A new dataclass type with the specified prefix.
    """
    return typing.cast(
        typing.Type[DataclassTco],
        type(
            f"{prefix}{dataclass_.__name__}",
            (dataclass_,),
            {
                "__module__": dataclass_.__module__,
                "__qualname__": f"{prefix}{dataclass_.__qualname__}",
                **(attributes or {}),
            },
        ),
    )


AttributeValue: TypeAlias = typing.Union[T, typing.Iterator[T]]


class GenericFieldAttributes(typing.TypedDict, total=False):
    """
    Generic attributes that can be modified for fields in a dataclass.
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
def modify_fields(
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    **modifications: Unpack[GenericFieldAttributes],
) -> typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]]: ...


@typing.overload
def modify_fields(
    dataclass_: typing.Type[DataclassTco],
    /,
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    **modifications: Unpack[GenericFieldAttributes],
) -> typing.Type[DataclassTco]: ...


@typing.overload
def modify_fields(
    dataclass_: None = ...,
    /,
    *,
    prefix: typing.Optional[str] = ...,
    include: typing.Optional[typing.Iterable[str]] = ...,
    exclude: typing.Optional[typing.Iterable[str]] = ...,
    **modifications: Unpack[GenericFieldAttributes],
) -> typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]]: ...


def modify_fields(
    dataclass_: typing.Optional[typing.Type[DataclassTco]] = None,
    /,
    *,
    prefix: typing.Optional[str] = None,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
    **modifications: Unpack[GenericFieldAttributes],
) -> typing.Union[
    typing.Type[DataclassTco],
    typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]],
]:
    """
    Dataclass decorator.

    Creates a dataclass with specific fields modified according to the provided attributes.

    This is especially useful if you need a with specify field behavior, but do not want to
    redefine an entirely new dataclass for that purpose.

    :param dataclass_: The dataclass which fields should be modified.
    :param prefix: Prefix to use for the new dataclass name. Default is None.
        Not providing a prefix may mean that the new dataclass
        will overwrite the original dataclass in the module namespace.

    :param include: Iterable of fields to include for modification.
    :param exclude: Iterable of fields to exclude from modification.
    :param modifications: (Generic) Field attributes to modify.
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

        cls_fields = dataclass_.__fields__
        field_names = cls_fields.keys()
        if include:
            field_names = [name for name in field_names if name in include]
        elif exclude:
            field_names = [name for name in field_names if name not in exclude]
        if not field_names:
            raise ConfigurationError(
                "No fields to modify. Either 'include' or 'exclude' must specify valid fields."
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

        return _make_new_dataclass(
            dataclass_, prefix=prefix or "", attributes=modified_fields
        )

    if dataclass_ is not None:
        return decorator(dataclass_)
    return decorator


strict = functools.partial(modify_fields, strict=True)
lazy = functools.partial(modify_fields, lazy=True)
ordered = functools.partial(modify_fields, order=count(0, step=1))
"""
Dataclass decorator.

Creates a dataclass with all or specific fields ordered.
"""
partial = functools.partial(modify_fields, required=False, allow_null=True)
"""
Dataclass decorator.

Creates a dataclass with all or specific fields made optional.

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
