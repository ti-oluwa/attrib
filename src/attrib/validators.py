import inspect
import typing
import operator
import re
import os
import pathlib
from collections import deque

from attrib._typing import SupportsRichComparison
from attrib._utils import is_iterable, is_mapping
from attrib.exceptions import FieldValidationError


_Validator: typing.TypeAlias = typing.Callable[
    [
        typing.Any,
        typing.Optional[typing.Any],
        typing.Optional[typing.Any],
    ],
    None,
]

Bound = SupportsRichComparison
ComparableValue = SupportsRichComparison
CountableValue = typing.Sized


@typing.final
class FieldValidator(typing.NamedTuple):
    """Field validator wrapper."""

    func: _Validator
    """Validator function."""
    message: typing.Optional[str] = None
    """Error message template."""

    @property
    def name(self) -> str:
        return self.func.__name__

    @property
    def description(self) -> str:
        return self.func.__doc__ or ""

    def __call__(
        self,
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        try:
            self.func(value, field, instance)
        except (ValueError, TypeError) as exc:
            msg = self.message or str(exc)
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format_map(
                    {
                        "name": name,
                        "value": value,
                        "field": field,
                    }
                ),
                name,
                value,
            ) from exc

    def __hash__(self) -> int:
        try:
            return hash(self.func)
        except TypeError:
            return hash(id(self.func))


def load_validators(
    *validators: _Validator,
) -> typing.Set[FieldValidator]:
    """Load the field validators into preferred internal type."""
    loaded_validators: typing.Set[FieldValidator] = set()
    for validator in validators:
        if isinstance(validator, FieldValidator):
            loaded_validators.add(validator)
            continue

        if not callable(validator):
            raise TypeError(f"Field validator '{validator}' is not callable.")

        loaded_validators.add(FieldValidator(validator))
    return loaded_validators


def pipe(
    *validators: typing.Union[_Validator, FieldValidator],
) -> FieldValidator:
    """
    Takes a sequence of validators and returns a single validator
    that applies all the validators in sequential order.

    :param validators: A list of validator functions
    :return: A single validator function
    """
    if not validators:
        raise ValueError("At least one validator must be provided.")

    loaded_validators = tuple(load_validators(*validators))
    if len(loaded_validators) == 1:
        return loaded_validators[0]

    def validation_pipeline(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Validation pipeline that applies all validators in sequence.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If any validator fails
        :return: None if all validators pass
        """
        nonlocal loaded_validators

        for validator in loaded_validators:
            validator(value, field, instance)

    validation_pipeline.__name__ = (
        f"pipeline({'-->'.join([v.name for v in loaded_validators])})"
    )
    return FieldValidator(validation_pipeline)


_NUMBER_VALIDATION_FAILURE_MESSAGE = (
    "'{value} {symbol} {bound}' is not True for {name!r}"
)


def number_validator_factory(
    comparison_func: typing.Callable[[ComparableValue, Bound], bool],
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
        pre_validation_hook: typing.Optional[
            typing.Callable[[typing.Any], ComparableValue]
        ] = None,
    ) -> FieldValidator:
        """
        Builds a validator for numeric comparisons.

        :param bound: The bound to compare against
        :param message: Error message template
        :param pre_validation_hook: A function to preprocess the value before validation
        :return: A validator function
        """
        global _NUMBER_VALIDATION_FAILURE_MESSAGE

        msg = message or _NUMBER_VALIDATION_FAILURE_MESSAGE

        def validator(
            value: typing.Any,
            field: typing.Optional[typing.Any] = None,
            instance: typing.Optional[typing.Any] = None,
        ) -> None:
            """
            Numeric comparison validator.

            Performs a comparison between the value and the bound using the
            specified comparison function.

            :param value: The value to validate
            :param field: The field being validated
            :param instance: The instance being validated
            :raises FieldValidationError: If the value does not pass the comparison
            :return: None if the comparison passes
            """
            nonlocal msg

            if pre_validation_hook:
                value = pre_validation_hook(value)

            if isinstance(value, (int, float)) and comparison_func(value, bound):
                return

            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format_map(
                    {
                        "value": value,
                        "symbol": symbol,
                        "bound": bound,
                        "name": name,
                        "field": field,
                    }
                ),
                name,
                value,
                bound,
                symbol,
            )

        validator.__name__ = f"number({symbol}{bound})"
        return FieldValidator(validator)

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
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], ComparableValue]
    ] = None,
) -> FieldValidator:
    """
    Number range validator.

    Builds a validator that checks if a value is within a specified range.

    :param min_val: Minimum allowed value
    :param max_val: Maximum allowed value
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    """
    msg = message or "'{name}' must be between {min} and {max}"

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Range validator.

        Checks if the value is within the specified range.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value is not within the range
        :return: None if the value is within the range
        """
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)

        if not (min_val <= value <= max_val):
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format(name=name, min=min_val, max=max_val),
                name,
                value,
                min_val,
                max_val,
            )

    validator.__name__ = f"number_range({min_val},{max_val})"
    return FieldValidator(validator)


_LENGTH_VALIDATION_FAILURE_MESSAGE = (
    "'len({name}) {symbol} {bound}' is not True, got {length}"
)


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
        pre_validation_hook: typing.Optional[
            typing.Callable[[typing.Any], CountableValue]
        ] = None,
    ) -> FieldValidator:
        """
        Builds a validator for length comparisons.

        :param bound: The bound to compare against
        :param message: Error message template
        :param pre_validation_hook: A function to preprocess the value before validation
        :return: A validator function
        """
        global _LENGTH_VALIDATION_FAILURE_MESSAGE

        msg = message or _LENGTH_VALIDATION_FAILURE_MESSAGE

        def validator(
            value: typing.Union[CountableValue, typing.Any],
            field: typing.Optional[typing.Any] = None,
            instance: typing.Optional[typing.Any] = None,
        ) -> None:
            """
            Length comparison validator.

            Performs a comparison between the length of the value and the bound
            using the specified comparison function.

            :param value: The value to validate
            :param field: The field being validated
            :param instance: The instance being validated
            :raises FieldValidationError: If the length of the value does not pass the comparison
            :return: None if the comparison passes
            """
            nonlocal msg

            if pre_validation_hook:
                value = pre_validation_hook(value)
            if comparison_func(len(value), bound):
                return
            name = field.effective_name if field else "value"
            length = len(value)
            raise FieldValidationError(
                msg.format_map(
                    {
                        "name": name,
                        "field": name,
                        "symbol": symbol,
                        "bound": bound,
                        "value": value,
                        "length": length,
                    }
                ),
                name,
                value,
                bound,
                symbol,
                length,
            )

        validator.__name__ = f"length({symbol}{bound})"
        return FieldValidator(validator)

    validator_factory.__name__ = f"length_validator_factory({symbol})"
    return validator_factory


min_length = length_validator_factory(operator.ge, ">=")
"""Validates that the length of the value is greater than or equal to the bound."""
max_length = length_validator_factory(operator.le, "<=")
"""Validates that the length of the value is less than or equal to the bound."""
length = length_validator_factory(operator.eq, "=")
"""Validates that the length of the value is equal to the bound."""


_NO_MATCH_MESSAGE = "'{name}' must match pattern {pattern!r} ({value!r} doesn't)"


def pattern(
    regex: typing.Union[re.Pattern, typing.AnyStr],
    flags: typing.Union[re.RegexFlag, typing.Literal[0]] = 0,
    func: typing.Optional[typing.Callable] = None,
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
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
    global _NO_MATCH_MESSAGE

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

    msg = message or _NO_MATCH_MESSAGE

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Regex pattern validator.

        Checks if the value matches the specified regex pattern.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value does not match the pattern
        :return: None if the value matches the pattern
        """
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if not match_func(value):
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format_map(
                    {
                        "name": name,
                        "pattern": pattern.pattern,
                        "value": value,
                    }
                ),
                name,
                pattern,
                value,
            )

    validator.__name__ = f"pattern({pattern.pattern!r})"
    return FieldValidator(validator)


_INSTANCE_CHECK_FAILURE_MESSAGE = "Value must be an instance of {cls!r}"


def instance_of(
    cls: typing.Union[
        typing.Type[typing.Any], typing.Tuple[typing.Type[typing.Any], ...]
    ],
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
    """
    Builds a validator that checks if a value is an instance of a given type.

    :param cls: A type or tuple of types to check against
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    """
    global _INSTANCE_CHECK_FAILURE_MESSAGE

    msg = message or _INSTANCE_CHECK_FAILURE_MESSAGE

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Instance check validator.

        Checks if the value is an instance of the specified class.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value is not an instance of the class
        :return: None if the value is an instance of the class
        """
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if not isinstance(value, cls):
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format_map(
                    {"cls": cls, "value": value, "name": name, "field": field}
                ),
                name,
                value,
                cls,
            )

    validator.__name__ = f"instance_of({cls!r})"
    return FieldValidator(validator)


_SUBCLASS_CHECK_FAILURE_MESSAGE = "Value must be a subclass of {cls!r}"


def subclass_of(
    cls: typing.Union[
        typing.Type[typing.Any], typing.Tuple[typing.Type[typing.Any], ...]
    ],
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
    """
    Builds a validator that checks if a value is a subclass of a given type.

    :param cls: A type or tuple of types to check against
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    """
    global _SUBCLASS_CHECK_FAILURE_MESSAGE

    msg = message or _SUBCLASS_CHECK_FAILURE_MESSAGE

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Subclass check validator.

        Checks if the value is a subclass of the specified class.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value is not a subclass of the class
        :return: None if the value is a subclass of the class
        """
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if not (inspect.isclass(value) and issubclass(value, cls)):
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format_map(
                    {"cls": cls, "value": value, "name": name, "field": field}
                ),
                name,
                value,
                cls,
            )

    validator.__name__ = f"subclass_of({cls!r})"
    return FieldValidator(validator)


def optional(validator: _Validator) -> FieldValidator:
    """
    Builds a validator that applies the given validator only if the value is not `None`.

    :param validator: The validator to apply to the field, if the field is not `None`
    :return: A validator function that applies the given validator if the value is not `None`
    """
    _validator = load_validators(validator).pop()

    def optional_validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Optional validator.

        Applies the given validator only if the value is not `None`.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value is not `None` and does not pass the validator
        :return: None if the value is `None` or passes the validator
        """
        if value is None:
            return
        return _validator(value, field, instance)

    optional_validator.__name__ = f"optional({validator.__name__})"
    return FieldValidator(optional_validator)


_IN_CHECK_FAILURE_MESSAGE = "Value must be in {choices!r}"


def in_(
    choices: typing.Iterable[typing.Any],
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
    """
    Builds a validator that checks if a value is in a given set of choices.

    :param choices: An iterable of valid values
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    """
    global _IN_CHECK_FAILURE_MESSAGE

    msg = message or _IN_CHECK_FAILURE_MESSAGE
    try:
        choices = set(choices)  # fast membership check. Ensures uniqueness
    except TypeError:
        # Choices is not hashable, so we need to use a tuple
        choices = tuple(choices)

    if len(choices) < 2:
        raise ValueError("'choices' must contain at least 2 unique elements")

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Membership check validator.

        Checks if the value is in the specified set of choices.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value is not in the choices
        :return: None if the value is in the choices
        """
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if value not in choices:
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format_map(
                    {"choices": choices, "value": value, "name": name, "field": field}
                ),
                name,
                value,
                choices,
            )

    validator.__name__ = f"member_of({choices!r})"
    return FieldValidator(validator)


_NEGATION_CHECK_FAILURE_MESSAGE = "Value must not validate {validator!r}"


def not_(
    validator: _Validator,
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
    """
    Builds a validator that raises `FieldValidationError` if the value
    validates against the specified validator.

    :param validator: The validator to check against
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    """
    global _NEGATION_CHECK_FAILURE_MESSAGE

    msg = message or _NEGATION_CHECK_FAILURE_MESSAGE
    _validator = load_validators(validator).pop()

    def negate_validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Negation validator. Applies logical NOT to the specified validator.

        Raises `FieldValidationError` if the value validates against the specified validator.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value validates against the specified validator
        :return: None if the value does not validate against the specified validator
        """
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)
        try:
            _validator(value, field, instance)
        except (ValueError, FieldValidationError):
            return
        name = field.effective_name if field else "value"
        raise FieldValidationError(
            msg.format_map(
                {"validator": validator, "value": value, "name": name, "field": field}
            ),
            name,
            value,
            validator,
        )

    negate_validator.__name__ = f"negate({_validator.name})"
    return FieldValidator(negate_validator)


and_ = pipe
"""Alias for `pipe` function. Applies logical AND to a sequence of validators."""


_ANY_CHECK_FAILURE_MESSAGE = "Value must validate at least one of {validators!r}"


def or_(
    *validators: _Validator,
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
    """
    Builds a validator that raises `FieldValidationError` if the value
    does not validate against any of the specified validators.

    :param validators: The validators to check against
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    """
    global _ANY_CHECK_FAILURE_MESSAGE

    msg = message or _ANY_CHECK_FAILURE_MESSAGE
    _validators = load_validators(*validators)
    if len(_validators) < 2:
        raise ValueError("'validators' must contain at least 2 unique validators")

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Or validator. Applies logical OR to a sequence of validators.

        Raises `FieldValidationError` if the value does not validate against any of the specified validators.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value does not validate against any of the specified validators
        :return: None if the value validates against at least one of the specified validators
        """
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)

        for validator in _validators:
            try:
                validator(value, field, instance)
                return
            except (ValueError, FieldValidationError):
                continue

        name = field.effective_name if field else "value"
        raise FieldValidationError(
            msg.format_map(
                {
                    "validators": [v.name for v in _validators],
                    "value": value,
                    "name": name,
                    "field": field,
                }
            ),
            name,
            value,
            [v.name for v in _validators],
        )

    validator.__name__ = f"any_of({[v.name for v in _validators]})"
    return FieldValidator(validator)


def is_callable(
    value: typing.Any,
    field: typing.Optional[typing.Any] = None,
    instance: typing.Optional[typing.Any] = None,
) -> None:
    """
    Checks if the value is callable.

    :param value: The value to check
    :param field: The field being validated
    :param instance: The instance being validated
    :raises FieldValidationError: If the value is not callable
    :return: None if the value is callable
    """
    if not callable(value):
        name = field.effective_name if field else "value"
        raise FieldValidationError(
            f"'{name}' must be callable",
            name,
            value,
        )


is_callable = FieldValidator(is_callable)


def value_validator(
    func: typing.Callable[[typing.Any], typing.Any],
) -> FieldValidator:
    """
    Wraps a validator function that only accepts a value and returns a boolean
    indicating whether the value is valid or not such that it can be used
    as a validator for a field.

    The function can also raise a `FieldValidationError` if the value is invalid.

    :param func: A function that takes a value and returns a boolean
        indicating whether the value is valid or not
    :return: A validator function
    :raises TypeError: If the function is not callable
    """
    if not callable(func):
        raise TypeError(f"Validator function '{func}' is not callable.")

    def validator_wrapper(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        if not func(value):
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                f"Validation with `{func.__name__}` failed for '{name}'",
                name,
                value,
            )
        return

    validator_wrapper.__name__ = f"value_validator({func.__name__})"
    validator_wrapper.__doc__ = func.__doc__
    return FieldValidator(validator_wrapper)


@typing.overload
def path(
    *,
    is_absolute: bool = ...,
    is_relative: bool = ...,
    exists: typing.Literal[False] = False,
) -> FieldValidator: ...


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
) -> FieldValidator: ...


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
) -> FieldValidator: ...


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
) -> FieldValidator: ...


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
) -> FieldValidator:
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
        validators.append(value_validator(pathlib.Path.exists))
    if is_symlink:
        validators.append(value_validator(pathlib.Path.is_symlink))
    if is_dir:
        validators.append(value_validator(pathlib.Path.is_dir))
    if is_file:
        validators.append(value_validator(pathlib.Path.is_file))
        if is_executable:
            validators.append(value_validator(lambda path: os.access(path, os.X_OK)))

    if is_empty:
        if is_dir:
            validators.append(value_validator(lambda path: not any(path.iterdir())))
        elif is_file:
            validators.append(value_validator(lambda path: path.stat().st_size == 0))

    if is_readable:
        validators.append(value_validator(lambda path: os.access(path, os.R_OK)))
    if is_writable:
        validators.append(value_validator(lambda path: os.access(path, os.W_OK)))

    return pipe(*validators) if len(validators) > 1 else validators[0]


def mapping(
    key_validator: _Validator,
    value_validator: _Validator,
    *,
    deep: bool = False,
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
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
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    """
    msg = message or "'{name}' must be a valid mapping, got {value!r}"
    _key_validator = load_validators(key_validator).pop()
    _value_validator = load_validators(value_validator).pop()

    def validate_mapping(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Mapping validator.

        Checks if the value is a mapping and validates its keys and values.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value is not a mapping or if any key/value fails validation
        :return: None if the value is a valid mapping
        """
        nonlocal msg, _key_validator, _value_validator

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if not is_mapping(value):
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format_map({"name": name, "value": value, "field": field}),
                name,
                value,
            )

        for key, val in value.items():
            _key_validator(key, field, instance)
            _value_validator(val, field, instance)

    def deep_validate_mapping(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Deep mapping validator.

        Checks if the value is a mapping and validates its keys and values
        iteratively.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value is not a mapping or if any key/value fails validation
        :return: None if the value is a valid mapping
        """
        nonlocal msg, _key_validator, _value_validator

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if not is_mapping(value):
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format_map({"name": name, "value": value, "field": field}),
                name,
                value,
            )

        # Use iterative approach to avoid recursion limit issues
        # when dealing with deeply nested mappings. May be more
        # efficient than recursion in some cases.
        stack = deque([value])
        while stack:
            current_value = stack.pop()
            for key, val in current_value.items():
                _key_validator(key, field, instance)
                _value_validator(val, field, instance)
                if is_mapping(val):
                    stack.appendleft(val)

    return FieldValidator(deep_validate_mapping if deep else validate_mapping)


def iterable(
    child_validator: _Validator,
    *,
    deep: bool = False,
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
    """
    Builds a validator that checks if a value is an iterable (e.g., list, tuple) and validates
    its elements using the provided validator.

    NOTE: If `deep=True`, before the value's (which is an iterable) items are validated,
    the value itself is first validated using the `child_validator`.
    This is to ensure consistency in the validation process.

    :param child_validator: A validator for the elements of the iterable
    :param deep: If True, applies the validators recursively to nested iterables
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    """
    msg = message or "'{name}' must be a valid iterable, got {value!r}"
    _child_validator = load_validators(child_validator).pop()

    def validate_iterable(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Iterable validator.

        Checks if the value is an iterable and validates its elements.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value is not an iterable or if any element fails validation
        :return: None if the value is a valid iterable
        """
        nonlocal msg, _child_validator

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if not is_iterable(value):
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format_map({"name": name, "value": value, "field": field}),
                name,
                value,
            )

        for item in value:
            _child_validator(item, field, instance)

    def deep_validate_iterable(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ) -> None:
        """
        Deep iterable validator.

        Checks if the value is an iterable and validates its elements iteratively.

        :param value: The value to validate
        :param field: The field being validated
        :param instance: The instance being validated
        :raises FieldValidationError: If the value is not an iterable or if any element fails validation
        :return: None if the value is a valid iterable
        """
        nonlocal msg, _child_validator

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if not is_iterable(value):
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format_map({"name": name, "value": value, "field": field}),
                name,
                value,
            )

        # Use iterative approach to avoid recursion limit issues
        # when dealing with deeply nested iterables. May be more
        # efficient than recursion in some cases.
        stack = deque([value])
        while stack:
            current_value = stack.pop()
            for item in current_value:
                _child_validator(item, field, instance)
                if is_iterable(item):
                    stack.appendleft(item)

    return FieldValidator(deep_validate_iterable if deep else validate_iterable)
