import copy
from types import MappingProxyType
import typing

from attrib._typing import EMPTY
from attrib.dataclass import DataclassTco
from attrib.exceptions import ConfigurationError


__all__ = [
    "partial",
    "strict",
]


@typing.overload
def partial(
    dataclass_: typing.Type[DataclassTco],
    /,
) -> typing.Type[DataclassTco]: ...


@typing.overload
def partial(
    dataclass_: None = None,
    /,
    *,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
) -> typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]]: ...


def partial(
    dataclass_: typing.Optional[typing.Type[DataclassTco]] = None,
    /,
    *,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
) -> typing.Union[
    typing.Type[DataclassTco],
    typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]],
]:
    """
    Create a partial dataclass with all or specific fields made optional.

    :param dataclass_: The dataclass which fields should be made optional.
    :param include: Iterable of fields to include as optional.
    :param exclude: Iterable of fields to exclude from being optional.
    """

    def decorator(
        dataclass_: typing.Type[DataclassTco],
    ) -> typing.Type[DataclassTco]:
        if include and exclude:
            raise ConfigurationError(
                "Cannot use both 'include' and 'exclude' options at the same time."
            )

        field_names = set(dataclass_.__fields__.keys())
        if include:
            field_names &= set(include)
        elif exclude:
            field_names -= set(exclude)
        if not field_names:
            raise ConfigurationError(
                "No fields to make partial. "
                "Either 'include' or 'exclude' must specify valid fields."
            )

        partial_fields = {}
        for field_name in field_names:
            field = copy.copy(dataclass_.__fields__[field_name])
            if field.default is EMPTY:
                field.default = None
            field.required = False
            field.allow_null = True
            partial_fields[field_name] = field

        dataclass_.__fields__ = MappingProxyType(
            {**dataclass_.__fields__, **partial_fields}
        )
        return dataclass_

    if dataclass_ is not None:
        return decorator(dataclass_)
    return decorator


@typing.overload
def strict(
    dataclass_: typing.Type[DataclassTco],
    /,
) -> typing.Type[DataclassTco]: ...


@typing.overload
def strict(
    dataclass_: None = None,
    /,
    *,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
) -> typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]]: ...


def strict(
    dataclass_: typing.Optional[typing.Type[DataclassTco]] = None,
    /,
    *,
    include: typing.Optional[typing.Iterable[str]] = None,
    exclude: typing.Optional[typing.Iterable[str]] = None,
) -> typing.Union[
    typing.Type[DataclassTco],
    typing.Callable[[typing.Type[DataclassTco]], typing.Type[DataclassTco]],
]:
    """
    Create a strict dataclass with all or specific fields made strict.

    :param dataclass_: The dataclass which fields should be made strict.
    :param include: Iterable of fields to include as strict.
    :param exclude: Iterable of fields to exclude from being strict.
    """
    def decorator(
        dataclass_: typing.Type[DataclassTco],
    ) -> typing.Type[DataclassTco]:
        if include and exclude:
            raise ConfigurationError(
                "Cannot use both 'include' and 'exclude' options at the same time."
            )

        field_names = set(dataclass_.__fields__.keys())
        if include:
            field_names &= set(include)
        elif exclude:
            field_names -= set(exclude)
        if not field_names:
            raise ConfigurationError(
                "No fields to make strict. "
                "Either 'include' or 'exclude' must specify valid fields."
            )

        strict_fields = {}
        for field_name in field_names:
            field = copy.copy(dataclass_.__fields__[field_name])
            field.strict = True
            strict_fields[field_name] = field

        dataclass_.__fields__ = MappingProxyType(
            {**dataclass_.__fields__, **strict_fields}
        )
        return dataclass_

    if dataclass_ is not None:
        return decorator(dataclass_)
    return decorator
