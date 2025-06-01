import inspect
import typing
import operator
import re
import os
import pathlib
from collections import deque
from annotated_types import MinLen
from typing_extensions import Annotated, Self

from attrib._typing import SupportsRichComparison, Validator, TypeAdapter
from attrib._utils import is_iterable, is_mapping
from attrib.exceptions import ValidationError


Bound: typing.TypeAlias = SupportsRichComparison
Comparable: typing.TypeAlias = SupportsRichComparison
Countable: typing.TypeAlias = typing.Sized


@typing.final
class Pipeline(typing.NamedTuple):
    """
    Pipeline of validators.

    Applies a sequence of validators to a value in order.

    :param validators: A tuple of validator functions
    """

    validators: Annotated[typing.Tuple[Validator[typing.Any], ...], MinLen(2)]
    message: typing.Optional[str] = None

    def __call__(
        self,
        value: typing.Any,
        adapter: typing.Optional[TypeAdapter] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Run the pipeline of validators.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :param args: Additional positional arguments to pass to the validators
        :param kwargs: Additional keyword arguments to pass to the validators or to use for validation (e.g, `fail_fast`).
        :raises ValidationError: If any of the validators fail
        :return: None if all validators pass
        """
        fail_fast = kwargs.pop("fail_fast", False)
        msg = self.message or "Validation pipeline failed."
        name = getattr(adapter, "name", None)
        error = None
        for validator in self.validators:
            try:
                validator(value, adapter, *args, **kwargs)
            except (ValueError, ValidationError) as exc:
                loc = [name] if not isinstance(exc, ValidationError) else None
                if fail_fast:
                    raise ValidationError.from_exception(
                        exc,
                        message=msg,
                        location=loc,
                    )
                elif error is None:
                    error = ValidationError.from_exception(
                        exc,
                        message=msg,
                        location=loc,
                    )
                else:
                    error.add(
                        exc,
                        message=msg,
                        location=loc,
                    )
        if error:
            raise error

    def __hash__(self) -> int:
        return hash(self.validators)

    def __repr__(self) -> str:
        return f"pipeline({' -> '.join([repr(v) for v in self.validators])})"

    def __and__(self, other: typing.Any) -> "Self":
        # This ensures that the resulting pipeline always remains flat
        # Nesting Pipelines may cause performance issues
        if isinstance(other, Validator):
            if isinstance(other, Pipeline):
                return self.__class__(
                    tuple(
                        {
                            *self.validators,
                            *other.validators,
                        }
                    )
                )
            return self.__class__(tuple({*self.validators, other}))
        return NotImplemented


And = Pipeline


@typing.final
class Or(typing.NamedTuple):
    """
    Or validator.

    Applies logical OR to a sequence of validators.

    :param validators: A tuple of validator functions
    """

    validators: Annotated[typing.Tuple[Validator[typing.Any], ...], MinLen(2)]
    message: typing.Optional[str] = None

    def __call__(
        self,
        value: typing.Any,
        adapter: typing.Optional[TypeAdapter] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Run the OR validator.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :param args: Additional positional arguments to pass to the validators
        :param kwargs: Additional keyword arguments to pass to the validators or to use for validation (e.g, `fail_fast`).
        :raises ValidationError: If all validators fail
        :return: None if at least one validator passes
        """
        msg = self.message or "All validation failed."
        name = getattr(adapter, "name", None)
        error = None
        for validator in self.validators:
            try:
                validator(value, adapter, *args, **kwargs)
                return
            except (ValueError, ValidationError) as exc:
                loc = [name] if not isinstance(exc, ValidationError) else None
                if error is None:
                    error = ValidationError.from_exception(
                        exc,
                        message=msg,
                        location=loc,
                    )
                else:
                    error.add(
                        exc,
                        message=msg,
                        location=loc,
                    )

        if error:
            raise error

    def __hash__(self) -> int:
        return hash(self.validators)

    def __repr__(self) -> str:
        return f"or({' | '.join([repr(v) for v in self.validators])})"

    def __or__(self, other: typing.Any) -> "Self":
        # This ensures that the resulting or always remains flat
        # Nesting Ors may cause performance issues
        if isinstance(other, Validator):
            if isinstance(other, Or):
                return self.__class__(
                    tuple(
                        {
                            *self.validators,
                            *other.validators,
                        }
                    )
                )
            return self.__class__(tuple({*self.validators, other}))
        return NotImplemented


#######################################
###### Field Specific Validators ######
#######################################


@typing.final
class FieldValidator(typing.NamedTuple):
    """Field validator."""

    func: Validator[typing.Any]
    """Validator function."""
    message: typing.Optional[str] = None
    """Validation error message (template)."""

    @property
    def description(self) -> str:
        return self.func.__doc__ or ""

    @property
    def name(self) -> str:
        return getattr(self.func, "__name__", None) or str(self.func)

    def __call__(
        self,
        value: typing.Any,
        adapter: typing.Optional[TypeAdapter] = None,
        instance: typing.Optional[typing.Any] = None,
        fail_fast: bool = False,
    ) -> None:
        msg = self.message or "Field validation failed."
        name = getattr(adapter, "name", None)
        try:
            self.func(
                value,
                adapter,
                instance,
                fail_fast=fail_fast,
            )
        except ValueError as exc:
            raise ValidationError.from_exception(
                exc,
                message=msg,
                parent_name=type(instance).__name__ if instance else None,
                input_type=type(value),
                expected_type=getattr(adapter, "typestr", None),
                location=[name],
            )

    def __hash__(self) -> int:
        try:
            return hash(self.func)
        except TypeError:
            return hash(id(self.func))

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"FieldValidator({self.func!r})"

    def __and__(self, other: typing.Any) -> "FieldValidator":
        if isinstance(other, Validator):
            return pipe(self, other)
        return NotImplemented

    def __or__(self, other: typing.Any) -> "FieldValidator":
        if isinstance(other, Validator):
            return or_(self, other)
        return NotImplemented

    def __not__(self) -> "FieldValidator":
        return FieldValidator(not_(self))


def load(*validators: Validator) -> typing.Tuple[FieldValidator, ...]:
    """Load the validators as `FieldValidator`s."""
    loaded = deque()
    for validator in validators:
        if isinstance(validator, FieldValidator):
            loaded.append(validator)
            continue

        if not callable(validator):
            raise TypeError(f"Validator '{validator}' is not callable.")

        loaded.append(FieldValidator(validator))
    return tuple(set(loaded))  # Ensure only unique validators


def pipe(
    *validators: Validator[typing.Any], message: typing.Optional[str] = None
) -> FieldValidator:
    """
    Builds a pipeline of validators.

    Applies a sequence of validators to a value in order.

    :param validators: A sequence of validator functions
    :param message: Optional message for validation errors
    :return: A field validator that applies the sequence of validators
    """
    if not validators:
        raise ValueError("At least one validator must be provided.")

    if len(validators) == 1:
        validator = validators[0]
        if isinstance(validator, FieldValidator):
            return validator
        return FieldValidator(validator)

    aggregate = deque()
    for validator in validators:
        if isinstance(validator, FieldValidator):
            validator = validator.func
        if isinstance(validator, Pipeline):
            aggregate.extend(validator.validators)
        else:
            aggregate.append(validator)
    return FieldValidator(Pipeline(tuple(aggregate)), message)


def or_(*validators: Validator, message: typing.Optional[str] = None) -> FieldValidator:
    """
    Builds an OR validator.

    Applies logical OR to a sequence of validators.

    :param validators: A sequence of validator functions
    :param message: Optional message for validation errors
    :return: A validator function that applies logical OR to the sequence of validators
    """
    if len(validators) < 2:
        raise ValueError("At least two validators must be provided.")

    aggregate = deque()
    for validator in validators:
        if isinstance(validator, FieldValidator):
            validator = validator.func
        if isinstance(validator, Or):
            aggregate.extend(validator.validators)
        else:
            aggregate.append(validator)
    return FieldValidator(Or(tuple(aggregate)), message)


#######################################
###### Field Specific Validators ######
#######################################


def number_validator_factory(
    comparison_func: typing.Callable[[Comparable, Bound], bool],
    symbol: str,
):
    """
    Builds a validator factory for numeric comparisons.

    :param comparison_func: The comparison function to use
    :param symbol: The symbol to use in the error message
    :return: The validator factory function
    """
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("The symbol must be a non-empty string.")

    def validator_factory(
        bound: Bound,
        message: typing.Optional[str] = None,
    ) -> Validator[typing.Any]:
        """
        Builds a validator for numeric comparisons.

        :param bound: The bound to compare against
        :param message: Error message template

        :return: A validator function
        """
        msg = message or "'{value} {symbol} {bound}' is not True"

        def validator(
            value: typing.Any,
            adapter: typing.Optional[typing.Any] = None,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> None:
            """
            Numeric comparison validator.

            Performs a comparison between the value and the bound using the
            specified comparison function.

            :param value: The value to validate
            :param adapter: The type adapter being used
            :raises ValidationError: If the value does not pass the comparison
            :return: None if the comparison passes
            """
            nonlocal msg
            if isinstance(value, (int, float)) and comparison_func(value, bound):
                return

            name = getattr(adapter, "name", None)
            raise ValidationError(
                msg.format_map(
                    {
                        "value": value,
                        "symbol": symbol,
                        "bound": bound,
                    },
                ),
                expected_type=type(bound),
                input_type=type(value),
                location=[name],
                code="value_out_of_bounds",
                context={
                    "symbol": symbol,
                },
            )

        validator.__name__ = f"number({symbol}{bound})"
        return validator

    validator_factory.__name__ = f"number_validator_factory({symbol})"
    return validator_factory


gte = number_validator_factory(operator.ge, ">=")
"""Validates that the value is greater than or equal to the bound."""
lte = number_validator_factory(operator.le, "<=")
"""Validates that the value is less than or equal to the bound."""
gt = number_validator_factory(operator.gt, ">")
"""Validates that the value is greater than the bound."""
lt = number_validator_factory(operator.lt, "<")
"""Validates that the value is less than the bound."""
eq = number_validator_factory(operator.eq, "=")
"""Validates that the value is equal to the bound."""


def number_range(
    min_val: SupportsRichComparison,
    max_val: SupportsRichComparison,
    message: typing.Optional[str] = None,
) -> Validator[typing.Any]:
    """
    Number range validator.

    Builds a validator that checks if a value is within a specified range.

    :param min_val: Minimum allowed value
    :param max_val: Maximum allowed value
    :param message: Error message template
    :return: A validator function
    """
    msg = message or "'{name}' must be between {min} and {max}, got {value!r}"

    def validator(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Range validator.

        Checks if the value is within the specified range.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value is not within the range
        :return: None if the value is within the range
        """
        nonlocal msg

        if not (min_val <= value <= max_val):
            name = getattr(adapter, "name", None)
            raise ValidationError(
                msg.format(name=name, min=min_val, max=max_val, value=value),
                expected_type=type(min_val),
                input_type=type(value),
                location=[name],
                code="value_not_in_range",
                context={
                    "min": min_val,
                    "max": max_val,
                },
            )

    validator.__name__ = f"number_range({min_val},{max_val})"
    return validator


def length_validator_factory(
    comparison_func: typing.Callable[[int, Bound], bool], symbol: str
):
    """
    Builds a validator factory for length comparisons.

    :param comparison_func: The comparison function to use
    :param symbol: The symbol to use in the error message
    :return: The validator factory function
    :raises ValueError: If the symbol is not valid
    """
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("The symbol must be a non-empty string.")

    def validator_factory(
        bound: Bound,
        message: typing.Optional[str] = None,
    ) -> Validator[typing.Any]:
        """
        Builds a validator for length comparisons.

        :param bound: The bound to compare against
        :param message: Error message template

        :return: A validator function
        """
        msg = message or "Value length must be {symbol} {bound}"

        def validator(
            value: Countable,
            adapter: typing.Optional[typing.Any] = None,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> None:
            """
            Length comparison validator.

            Performs a comparison between the length of the value and the bound
            using the specified comparison function.

            :param value: The value to validate
            :param adapter: The type adapter being used
            :raises ValidationError: If the length of the value does not pass the comparison
            :return: None if the comparison passes
            """
            nonlocal msg

            if comparison_func(len(value), bound):
                return
            name = getattr(adapter, "name", None)
            length = len(value)
            raise ValidationError(
                msg.format_map(
                    {
                        "name": name,
                        "symbol": symbol,
                        "bound": bound,
                        "value": value,
                        "length": length,
                    }
                ),
                expected_type="countable",
                input_type=type(value),
                location=[name],
                code="invalid_length",
                context={
                    "symbol": symbol,
                    "bound": bound,
                    "length": length,
                },
            )

        validator.__name__ = f"length({symbol}{bound})"
        return validator

    validator_factory.__name__ = f"length_validator_factory({symbol})"
    return validator_factory


min_length = length_validator_factory(operator.ge, ">=")
"""Validates that the length of the value is greater than or equal to the bound."""
max_length = length_validator_factory(operator.le, "<=")
"""Validates that the length of the value is less than or equal to the bound."""
length = length_validator_factory(operator.eq, "=")
"""Validates that the length of the value is equal to the bound."""


def pattern(
    regex: typing.Union[re.Pattern, typing.AnyStr],
    flags: typing.Union[re.RegexFlag, typing.Literal[0]] = 0,
    func: typing.Optional[typing.Callable] = None,
    message: typing.Optional[str] = None,
) -> Validator[typing.Any]:
    """
    Builds a validator that checks if a value matches a given regex pattern.

    :param regex: A regex string or precompiled pattern to match against
    :param message: Error message template
    :param flags: Flags that will be passed to the underlying re function (default 0)
    :param func: Which underlying `re` function to call. Valid options are
        `re.fullmatch`, `re.search`, and `re.match`; the default `None`
        means `re.fullmatch`. For performance reasons, the pattern is
        always precompiled using `re.compile`.
    :param pre_validation_hook: A function to preprocess the value before matching
    :return: A validator function
    """
    valid_funcs = (re.fullmatch, None, re.search, re.match)
    if func not in valid_funcs:
        msg = "'func' must be one of {}.".format(
            ", ".join(sorted((e and e.__name__) or "None" for e in set(valid_funcs)))
        )
        raise ValueError(msg)

    if isinstance(regex, re.Pattern):
        if flags:
            msg = "'flags' can only be used with a string pattern; pass flags to re.compile() instead"
            raise TypeError(msg)
        pattern = regex
    else:
        pattern = re.compile(regex, flags)

    if func is re.match:
        match_func = pattern.match
    elif func is re.search:
        match_func = pattern.search
    else:
        match_func = pattern.fullmatch

    msg = message or "Value must match pattern {pattern!r}"

    def validator(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Regex pattern validator.

        Checks if the value matches the specified regex pattern.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value does not match the pattern
        :return: None if the value matches the pattern
        """
        nonlocal msg

        if not match_func(str(value)):
            name = getattr(adapter, "name", None)
            raise ValidationError(
                msg.format_map(
                    {
                        "name": name,
                        "pattern": pattern.pattern,
                        "value": value,
                    }
                ),
                expected_type=f"pattern[{pattern.pattern!r}]",
                input_type=type(value),
                location=[name],
                code="pattern_mismatch",
                context={
                    "pattern": pattern.pattern,
                },
            )

    validator.__name__ = f"pattern({pattern.pattern!r})"
    return validator


def instance_of(
    cls: typing.Union[
        typing.Type[typing.Any], typing.Tuple[typing.Type[typing.Any], ...]
    ],
    message: typing.Optional[str] = None,
) -> Validator[typing.Any]:
    """
    Builds a validator that checks if a value is an instance of a given type.

    :param cls: A type or tuple of types to check against
    :param message: Error message template
    :return: A validator function
    """
    msg = message or "Value must be an instance of {cls!r}, not {type!r}"

    def validator(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Instance check validator.

        Checks if the value is an instance of the specified class.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value is not an instance of the class
        :return: None if the value is an instance of the class
        """
        nonlocal msg

        if cls is typing.Any:
            return

        if not isinstance(value, cls):
            name = getattr(adapter, "name", None)
            raise ValidationError(
                msg.format_map(
                    {
                        "cls": cls,
                        "value": value,
                        "type": type(value),
                        "name": name,
                    }
                ),
                expected_type=cls,
                input_type=type(value),
                location=[name],
                code="invalid_type",
            )

    validator.__name__ = f"instance_of({cls!r})"
    return validator


def subclass_of(
    cls: typing.Union[
        typing.Type[typing.Any], typing.Tuple[typing.Type[typing.Any], ...]
    ],
    message: typing.Optional[str] = None,
) -> Validator[typing.Any]:
    """
    Builds a validator that checks if a value is a subclass of a given type.

    :param cls: A type or tuple of types to check against
    :param message: Error message template
    :return: A validator function
    """
    msg = message or "Value must be a subclass of {cls!r}, not {value_type!r}."

    def validator(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Subclass check validator.

        Checks if the value is a subclass of the specified class.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value is not a subclass of the class
        :return: None if the value is a subclass of the class
        """
        nonlocal msg

        if not (inspect.isclass(value) and issubclass(value, cls)):
            name = getattr(adapter, "name", None)
            raise ValidationError(
                msg.format_map(
                    {
                        "cls": cls,
                        "value": value,
                        "value_type": type(value),
                        "name": name,
                    }
                ),
                expected_type=f"type[{cls!r}]",
                input_type=f"type[{value!r}]",
                location=[name],
                code="invalid_type",
            )

    validator.__name__ = f"subclass_of({cls!r})"
    return validator


def optional(validator: Validator) -> Validator[typing.Any]:
    """
    Builds a validator that applies the given validator only if the value is not `None`.

    :param validator: The validator to apply to the adapter, if the adapter is not `None`
    :return: A validator function that applies the given validator if the value is not `None`
    """
    if not isinstance(validator, Validator):
        raise TypeError(f"Invalid validator: {validator!r}")

    def optional_validator(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Optional validator.

        Applies the given validator only if the value is not `None`.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value is not `None` and does not pass the validator
        :return: None if the value is `None` or passes the validator
        """
        if value is None:
            return
        return validator(value, adapter, *args, **kwargs)

    optional_validator.__name__ = f"optional({validator!r})"
    return optional_validator


def member_of(
    choices: typing.Iterable[typing.Any],
    message: typing.Optional[str] = None,
) -> Validator[typing.Any]:
    """
    Builds a validator that checks if a value is a member of a given set of choices.

    :param choices: An iterable of valid choices
    :param message: Error message template
    :return: A validator function
    """
    msg = message or "Value not in choices."
    try:
        choices = set(choices)  # fast membership check. Ensures uniqueness
    except TypeError:
        # Choices is not hashable, so we need to use a tuple
        choices = tuple(choices)

    if len(choices) < 2:
        raise ValueError("'choices' must contain at least 2 unique elements")

    def validator(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Membership check validator.

        Checks if the value is in the specified set of choices.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value is not in the choices
        :return: None if the value is in the choices
        """
        nonlocal msg

        if value not in choices:
            name = getattr(adapter, "name", None)
            raise ValidationError(
                msg.format_map(
                    {
                        "choices": choices,
                        "value": value,
                        "name": name,
                    }
                ),
                expected_type=f"member_of[{[repr(c) for c in choices]}]",
                input_type=f"{type(value)!r}",
                location=[name],
                code="invalid_choice",
            )

    validator.__name__ = f"member_of({choices!r})"
    return validator


in_ = member_of


def not_(
    validator: Validator,
    message: typing.Optional[str] = None,
) -> Validator[typing.Any]:
    """
    Builds a validator that raises `ValidationError` if the value
    validates against the specified validator.

    :param validator: The validator to check against
    :param message: Error message template
    :return: A validator function
    """
    if not isinstance(validator, Validator):
        raise TypeError(f"Invalid validator: {validator!r}")

    msg = message or "Value validated when its should not."

    def negate_validator(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Negation validator. Applies logical NOT to the specified validator.

        Raises `ValidationError` if the value validates against the specified validator.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value validates against the specified validator
        :return: None if the value does not validate against the specified validator
        """
        nonlocal msg

        try:
            validator(value, adapter, *args, **kwargs)
        except (ValueError, ValidationError):
            return
        name = getattr(adapter, "name", None)
        raise ValidationError(
            msg.format_map(
                {
                    "validator": validator,
                    "value": value,
                    "name": name,
                }
            ),
            expected_type=f"not[{validator!r}]",
            input_type=type(value),
            location=[name],
            code="negation_failed",
        )

    negate_validator.__name__ = f"negate({validator!r})"
    return negate_validator


and_ = pipe
"""Alias for `pipe` function. Applies logical AND to a sequence of validators."""


def is_callable(
    value: typing.Any,
    adapter: typing.Optional[typing.Any] = None,
    *args: typing.Any,
    **kwargs: typing.Any,
) -> None:
    """
    Checks if the value is callable.

    :param value: The value to check
    :param adapter: The type adapter being used
    :raises ValidationError: If the value is not callable
    :return: None if the value is callable
    """
    if not callable(value):
        name = getattr(adapter, "name", None)
        raise ValidationError(
            "Value must be a callable",
            expected_type="callable",
            input_type=type(value),
            location=[name],
            code="not_callable",
        )


def value_validator(
    func: typing.Callable[[typing.Any], typing.Any],
    message: typing.Optional[str] = None,
) -> Validator[typing.Any]:
    """
    Wraps a validator function that only accepts a value and returns a boolean
    indicating whether the value is valid or not such that it can be used
    as a validator for a adapter.

    The function can also raise a `ValidationError` if the value is invalid.

    :param func: A function that takes a value and returns a boolean
        indicating whether the value is valid or not
    :param message: Validation error message (template)
    :return: A validator function
    :raises TypeError: If the function is not callable
    """
    if not callable(func):
        raise TypeError(f"Validator function '{func}' is not callable.")

    def validator_wrapper(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Validator wrapper.

        Checks if the value is valid according to the specified function.
        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value does not pass the validation
        :return: None if the value is valid
        """

        if not func(value):
            name = getattr(adapter, "name", None)
            raise ValidationError(
                message or "Validation failed.",
                location=[name],
            )
        return

    validator_wrapper.__name__ = f"validate_value({func.__name__})"
    validator_wrapper.__doc__ = func.__doc__
    return validator_wrapper


@typing.overload
def path(
    *,
    is_absolute: bool = ...,
    is_relative: bool = ...,
    exists: typing.Literal[False] = False,
) -> Validator[typing.Any]: ...


@typing.overload
def path(
    *,
    is_absolute: bool = ...,
    is_relative: bool = ...,
    exists: typing.Literal[True] = True,
    is_dir: bool = ...,
    is_file: bool = ...,
    is_symlink: bool = ...,
    is_readable: bool = ...,
    is_writable: bool = ...,
    is_executable: bool = ...,
    is_empty: bool = ...,
) -> Validator[typing.Any]: ...


@typing.overload
def path(
    *,
    is_absolute: typing.Literal[True] = True,
    is_relative: typing.Literal[False] = False,
    exists: bool = ...,
    is_dir: bool = ...,
    is_file: bool = ...,
    is_symlink: bool = ...,
    is_readable: bool = ...,
    is_writable: bool = ...,
    is_executable: bool = ...,
    is_empty: bool = ...,
) -> Validator[typing.Any]: ...


@typing.overload
def path(
    *,
    is_absolute: typing.Literal[False] = False,
    is_relative: typing.Literal[True] = True,
    exists: bool = ...,
    is_dir: bool = ...,
    is_file: bool = ...,
    is_symlink: bool = ...,
    is_readable: bool = ...,
    is_writable: bool = ...,
    is_executable: bool = ...,
    is_empty: bool = ...,
) -> Validator[typing.Any]: ...


def path(
    *,
    is_absolute: bool = False,
    is_relative: bool = False,
    exists: bool = False,
    is_dir: bool = False,
    is_file: bool = False,
    is_symlink: bool = False,
    is_readable: bool = False,
    is_writable: bool = False,
    is_executable: bool = False,
    is_empty: bool = False,
) -> Validator[typing.Any]:
    """
    `pathlib.Path` validator factory

    Builds a validator or validation pipeline that checks if a value is a valid path
    based on the specified criteria.

    :param is_absolute: Check if the path is absolute
    :param is_relative: Check if the path is relative
    :param exists: Check if the path exists

    The parameter below are only valid if `exists=True`:

    :param is_dir: Check if the path is a directory
    :param is_file: Check if the path is a file
    :param is_symlink: Check if the path is a symlink
    :param is_readable: Check if the path is readable
    :param is_writable: Check if the path is writable
    :param is_executable: Check if the path is executable
    :param is_empty: Check if the path is empty
    """
    if not any(
        (
            exists,
            is_dir,
            is_file,
            is_symlink,
            is_absolute,
            is_relative,
            is_readable,
            is_writable,
            is_executable,
            is_empty,
        )
    ):
        raise ValueError("At least one of the path checks must be True.")

    if is_absolute and is_relative:
        raise ValueError("`is_absolute` and `is_relative` cannot be used together.")

    if not exists and any(
        (is_dir, is_file, is_symlink, is_readable, is_writable, is_executable, is_empty)
    ):
        raise ValueError("`exists=True` is required for the selected checks.")
    if is_dir and is_file:
        raise ValueError("`is_dir` and `is_file` cannot be used together.")
    if is_empty and not (is_dir or is_file):
        raise ValueError("`is_empty` must be used with `is_dir` or `is_file`.")

    validators = []
    if is_absolute:
        validators.append(value_validator(pathlib.Path.is_absolute))
    elif is_relative:
        validators.append(
            value_validator(lambda path: not pathlib.Path.is_absolute(path))
        )

    if exists:
        validators.append(
            value_validator(pathlib.Path.exists, message="Path does not exist.")
        )
    if is_symlink:
        validators.append(
            value_validator(pathlib.Path.is_symlink, message="Path is not a symlink.")
        )
    if is_dir:
        validators.append(
            value_validator(pathlib.Path.is_dir, message="Path is not a directory.")
        )
    if is_file:
        validators.append(
            value_validator(pathlib.Path.is_file, message="Path is not a file.")
        )
        if is_executable:
            validators.append(
                value_validator(
                    lambda path: os.access(path, os.X_OK),
                    message="Path is not executable.",
                )
            )

    if is_empty:
        if is_dir:
            validators.append(
                value_validator(
                    lambda path: not any(path.iterdir()),
                    message="Directory is not empty.",
                )
            )
        elif is_file:
            validators.append(
                value_validator(
                    lambda path: path.stat().st_size == 0, message="File is not empty."
                )
            )

    if is_readable:
        validators.append(
            value_validator(
                lambda path: os.access(path, os.R_OK), message="Path is not readable."
            )
        )
    if is_writable:
        validators.append(
            value_validator(
                lambda path: os.access(path, os.W_OK), message="Path is not writable."
            )
        )

    return Pipeline(tuple(validators)) if len(validators) > 1 else validators[0]


def mapping(
    key_validator: typing.Optional[Validator],
    value_validator: typing.Optional[Validator],
    *,
    deep: bool = False,
    message: typing.Optional[str] = None,
) -> Validator[typing.Any]:
    """
    Builds a validator that checks if a value is a mapping (e.g., dict) and validates its keys
    and values using the provided validators.

    NOTE: If `deep=True`, before the value's (which is a mapping) items are validated,
    the value itself is first validated using the `value_validator`.
    This is to ensure consistency in the validation process.

    :param key_validator: A validator for the keys of the mapping
    :param value_validator: A validator for the values of the mapping
    :param deep: If True, applies the validators iteratively to nested mappings
    :param message: Error message template
    :return: A validator function
    """
    if not (key_validator or value_validator):
        raise ValueError(
            "Either one of `key_validator` or `value_validator` must be provided."
        )
    msg = message or "Value must be a valid mapping."

    def validate_mapping(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Mapping validator.

        Checks if the value is a mapping and validates its keys and values.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value is not a mapping or if any key/value fails validation
        :return: None if the value is a valid mapping
        """
        nonlocal msg
        name = getattr(adapter, "name", None)

        if not is_mapping(value):
            raise ValidationError(
                msg.format_map({"name": name, "value": value}),
                expected_type="mapping",
                input_type=type(value),
                location=[name],
                code="invalid_type",
            )

        for key, val in value.items():
            if key_validator:
                try:
                    key_validator(key, adapter, *args, **kwargs)
                except (ValidationError, ValueError) as exc:
                    raise ValidationError.from_exception(
                        exc,
                        message="Key validation failed",
                        location=[name, f"{key}:key"],
                        input_type=type(key),
                        code="key_validation_failed",
                    )
            if value_validator:
                try:
                    value_validator(val, adapter, *args, **kwargs)
                except (ValidationError, ValueError) as exc:
                    raise ValidationError.from_exception(
                        exc,
                        message="Value validation failed",
                        location=[name, f"{key}:value"],
                        input_type=type(val),
                        code="value_validation_failed",
                    )

    def deep_validate_mapping(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Deep mapping validator.

        Checks if the value is a mapping and validates its keys and values
        iteratively.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value is not a mapping or if any key/value fails validation
        :return: None if the value is a valid mapping
        """
        nonlocal msg
        name = getattr(adapter, "name", None)
        if not is_mapping(value):
            raise ValidationError(
                msg.format_map({"name": name, "value": value}),
                expected_type="mapping",
                input_type=type(value),
                location=[name],
                code="invalid_type",
            )

        # Use iterative approach to avoid recursion limit issues
        # when dealing with deeply nested mappings. May be more
        # efficient than recursion in some cases.
        stack = deque([value])
        while stack:
            current_value = stack.pop()
            for key, val in current_value.items():
                if key_validator:
                    try:
                        key_validator(key, adapter, *args, **kwargs)
                    except (ValidationError, ValueError) as exc:
                        raise ValidationError.from_exception(
                            exc,
                            message="Key validation failed",
                            location=[name, f"{key}:key"],
                            input_type=type(key),
                            code="key_validation_failed",
                        )
                if value_validator:
                    try:
                        value_validator(val, adapter, *args, **kwargs)
                    except (ValidationError, ValueError) as exc:
                        raise ValidationError.from_exception(
                            exc,
                            message="Value validation failed",
                            location=[name, f"{key}:value"],
                            input_type=type(val),
                            code="value_validation_failed",
                        )

                if is_mapping(val):
                    stack.appendleft(val)

    return deep_validate_mapping if deep else validate_mapping


def iterable(
    child_validator: Validator,
    *,
    deep: bool = False,
    message: typing.Optional[str] = None,
) -> Validator[typing.Any]:
    """
    Builds a validator that checks if a value is an iterable (e.g., list, tuple) and validates
    its elements using the provided validator.

    NOTE: If `deep=True`, before the value's (which is an iterable) items are validated,
    the value itself is first validated using the `child_validator`.
    This is to ensure consistency in the validation process.

    :param child_validator: A validator for the elements of the iterable
    :param deep: If True, applies the validators recursively to nested iterables
    :param message: Error message template
    :return: A validator function
    """
    msg = message or "Value must be a valid iterable."

    def validate_iterable(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Iterable validator.

        Checks if the value is an iterable and validates its elements.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value is not an iterable or if any element fails validation
        :return: None if the value is a valid iterable
        """
        nonlocal msg
        name = getattr(adapter, "name", None)
        if not is_iterable(value):
            raise ValidationError(
                msg.format_map({"name": name, "value": value}),
                expected_type="iterable",
                input_type=type(value),
                location=[name],
                code="invalid_type",
            )

        for index, item in enumerate(value):
            try:
                child_validator(item, adapter, *args, **kwargs)
            except (ValidationError, ValueError) as exc:
                raise ValidationError.from_exception(
                    exc,
                    message="Item validation failed",
                    location=[name, index],
                    input_type=type(item),
                )

    def deep_validate_iterable(
        value: typing.Any,
        adapter: typing.Optional[typing.Any] = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Deep iterable validator.

        Checks if the value is an iterable and validates its elements iteratively.

        :param value: The value to validate
        :param adapter: The type adapter being used
        :raises ValidationError: If the value is not an iterable or if any element fails validation
        :return: None if the value is a valid iterable
        """
        nonlocal msg
        name = getattr(adapter, "name", None)
        if not is_iterable(value):
            raise ValidationError(
                msg.format_map({"name": name, "value": value}),
                expected_type="iterable",
                input_type=type(value),
                location=[name],
                code="invalid_type",
            )

        # Use iterative approach to avoid recursion limit issues
        # when dealing with deeply nested iterables. May be more
        # efficient than recursion in some cases.
        stack = deque([value, []])
        while stack:
            current_value, parent_indices = stack.pop()
            for index, item in enumerate(current_value):
                try:
                    child_validator(item, adapter, *args, **kwargs)
                except (ValidationError, ValueError) as exc:
                    raise ValidationError.from_exception(
                        exc,
                        message="Item validation failed",
                        location=[name, *parent_indices, index],
                        input_type=type(item),
                    )
                if is_iterable(item):
                    stack.appendleft((item, [*parent_indices, index]))

    return deep_validate_iterable if deep else validate_iterable
