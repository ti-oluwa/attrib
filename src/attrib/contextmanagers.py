import typing
from contextvars import ContextVar, Token
from contextlib import contextmanager

__all__ = [
    "deserialization_context",
]


_fail_fast: ContextVar[bool] = ContextVar("fail_fast", default=False)
"""
`fail_fast` context variable to control whether to stop on the first error encountered during loading
data onto dataclass instances.
"""
_ignore_extras: ContextVar[bool] = ContextVar("ignore_extras", default=False)
"""
`ignore_extras` context variable to control whether to ignore extra fields not defined in the dataclass
"""
_by_name: ContextVar[bool] = ContextVar("by_name", default=False)
"""
`by_name` context variable to control whether to use actual field names as keys instead of their effective names (name or alias)
 when loading data onto dataclass instances.
"""
_is_valid: ContextVar[bool] = ContextVar("is_valid", default=False)
"""`is_valid` context variable to control whether the data being loaded is already validated."""


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
        _fail_fast: fail_fast,
        _ignore_extras: ignore_extras,
        _by_name: by_name,
        _is_valid: is_valid,
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
