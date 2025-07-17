import typing
from contextvars import ContextVar, Token
from contextlib import contextmanager


__all__ = [
    "deserialization_context",
    "serialization_context",
]


fail_fast_ctx_var: ContextVar[bool] = ContextVar("fail_fast", default=False)
"""
`fail_fast` context variable to control whether to stop on the first error encountered during loading
data onto dataclass instances.
"""
ignore_extras_ctx_var: ContextVar[bool] = ContextVar("ignore_extras", default=False)
"""
`ignore_extras` context variable to control whether to ignore extra fields not defined in the dataclass
"""
by_name_ctx_var: ContextVar[bool] = ContextVar("by_name", default=False)
"""
`by_name` context variable to control whether to use actual field names as keys instead of their effective names (name or alias)
 when loading data onto dataclass instances.
"""
is_valid_ctx_var: ContextVar[bool] = ContextVar("is_valid", default=False)
"""`is_valid` context variable to control whether the data being loaded is already validated."""

by_alias_ctx_var: ContextVar[bool] = ContextVar("by_alias", default=False)
"""
`by_alias` context variable to control whether to use field aliases when serializing dataclass instances.
This is useful when you want to serialize the dataclass using the field aliases instead of their names.
"""
exclude_unset_ctx_var: ContextVar[bool] = ContextVar("exclude_unset", default=False)
"""
`exclude_unset` context variable to control whether to exclude unset fields when serializing dataclass instances.
This is useful when you want to serialize only the fields that have been explicitly set.
"""
astuple_ctx_var: ContextVar[bool] = ContextVar("as_tuple", default=False)
"""
`as_tuple` context variable to control whether to serialize the dataclass as a tuple instead of a dictionary.
This is useful when you want to serialize the dataclass as a named tuple.
"""


@contextmanager
def deserialization_context(
    fail_fast: typing.Optional[bool] = None,
    ignore_extras: typing.Optional[bool] = None,
    by_name: typing.Optional[bool] = None,
    is_valid: typing.Optional[bool] = None,
) -> typing.Generator[None, None, None]:
    """
    Deserialization context manager.

    All deserialization occurring within this context will use the defined settings.

    :param fail_fast: If True, stop on the first error encountered during loading.
    :param ignore_extras: If True, ignore extra fields not defined in the dataclass.
    :param by_name: If True, use actual field names as keys instead of their effective names (name or alias).
        when loading data onto dataclass instances.
    :param is_valid: If True, the data being loaded is already validated and will not be validated again.

    Leaving any of this parameters as None will leave the current context variable value unchanged.
    """
    context_settings: typing.Dict[ContextVar[bool], typing.Optional[bool]] = {
        fail_fast_ctx_var: fail_fast,
        ignore_extras_ctx_var: ignore_extras,
        by_name_ctx_var: by_name,
        is_valid_ctx_var: is_valid,
    }
    reset_tokens: typing.Dict[ContextVar[bool], Token[bool]] = {}
    for context_var, value in context_settings.items():
        if value is not None:
            reset_tokens[context_var] = context_var.set(value)

    try:
        yield
    finally:
        for context_var, token in reset_tokens.items():
            context_var.reset(token)


@contextmanager
def serialization_context(
    fail_fast: typing.Optional[bool] = None,
    by_alias: typing.Optional[bool] = None,
    exclude_unset: typing.Optional[bool] = None,
) -> typing.Generator[None, None, None]:
    """
    Serialization context manager.

    All serialization occurring within this context will use the defined settings.

    :param fail_fast: If True, serialization will stop at the first error encountered.
        If False, it will collect all errors and raise a `SerializationError` at the end.

    :param by_alias: If True, use field aliases for serialization. Defaults to False.
        If the field has no serialization alias, it will use the effective name which
        resolves to the default (deserialization) alias if it was set, or the field
        name otherwise.

    :param exclude_unset: If True, exclude fields that were not explicitly set on the instance
        during instantiation or directly. This does not include field defaults set for fields with
        default values.

    Leaving any of this parameters as None will leave the current context variable value unchanged.
    """
    context_settings: typing.Dict[ContextVar[bool], typing.Optional[bool]] = {
        fail_fast_ctx_var: fail_fast,
        by_alias_ctx_var: by_alias,
        exclude_unset_ctx_var: exclude_unset,
    }
    reset_tokens: typing.Dict[ContextVar[bool], Token[bool]] = {}
    for context_var, value in context_settings.items():
        if value is not None:
            reset_tokens[context_var] = context_var.set(value)

    try:
        yield
    finally:
        for context_var, token in reset_tokens.items():
            context_var.reset(token)
