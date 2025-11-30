from contextlib import contextmanager
import sys
import typing

from typing_extensions import Self

from attrib.types import Context


class AttribException(Exception):
    """Base exception for all attrib-related errors."""

    pass


class ConfigurationError(AttribException):
    """Raised for configuration-related errors."""

    pass


class InstanceError(AttribException):
    """Raised for instance-related errors."""

    pass


class FrozenInstanceError(InstanceError):
    """Raised when trying to modify a frozen instance."""

    pass


class FieldError(AttribException):
    """Raised for field-related errors."""

    def __init__(
        self,
        message: str,
        name: typing.Optional[str] = None,
    ):
        super().__init__(message)
        self.name = name
        self.message = message

    def __str__(self) -> str:
        if self.name is None:
            return self.message
        return f"Error in {self.name!r}: \n\t {self.message}"


if sys.version_info >= (3, 9):
    removeprefix = str.removeprefix
else:
    # Fallback for Python versions < 3.9
    # This is a simple implementation of removeprefix for compatibility
    # with older Python versions.
    def removeprefix(s: str, prefix: str) -> str:
        if s.startswith(prefix):
            return s[len(prefix) :]
        return s


class ErrorDetail(typing.NamedTuple):
    """Error detail for field errors."""

    location: typing.List[typing.Any]
    """Location of the error source in the data structure, in sequence."""
    message: str
    """Error message."""
    expected_type: typing.Optional[type] = None
    """Expected type for the field or context."""
    input_type: typing.Optional[typing.Any] = None
    """Input type that caused the error."""
    code: typing.Optional[str] = None
    """Error code for the error detail."""
    context: typing.Optional[Context] = None
    """Context dictionary for additional information."""
    origin: typing.Optional[BaseException] = None
    """Original exception that caused the error, if any."""

    def as_string(self) -> str:
        """Return a string representation of the error detail."""
        text = [
            removeprefix(
                "".join(
                    [
                        f"[{loc}]" if isinstance(loc, int) else f".{loc}"
                        for loc in self.location
                    ]
                ),
                ".",
            ),
            f"\n  {self.message} ",
        ]

        info = []
        if self.input_type is not None:
            type_name = (
                self.input_type.__name__
                if isinstance(self.input_type, type)
                else str(self.input_type)
            )
            info.append(f"input_type={type_name!r}")
        if self.expected_type is not None:
            type_name = (
                self.expected_type.__name__
                if isinstance(self.expected_type, type)
                else str(self.expected_type)
            )
            info.append(f"expected_type={type_name!r}")
        if self.code is not None:
            info.append(f"code={self.code!r}")
        if self.origin is not None:
            info.append(f"origin={type(self.origin).__name__}")
        return "".join(text) + "[" + ", ".join(info) + "]"

    def as_json(self) -> typing.Dict[str, typing.Any]:
        """Return a JSON-serializable representation of the error detail."""
        return {
            "location": self.location,
            "message": self.message,
            "expected_type": (
                self.expected_type.__name__
                if isinstance(self.expected_type, type)
                else str(self.expected_type)
            ),
            "input_type": (
                self.input_type.__name__
                if isinstance(self.input_type, type)
                else str(self.input_type)
            ),
            "code": self.code,
            "context": self.context,
        }


class DetailedError(AttribException):
    """Raised for errors with detailed information."""

    def __init__(
        self,
        message: str,
        *,
        parent_name: typing.Optional[str] = None,
        expected_type: typing.Optional[typing.Any] = None,
        input_type: typing.Optional[typing.Any] = None,
        location: typing.Optional[typing.List[typing.Any]] = None,
        code: typing.Optional[str] = None,
        context: typing.Optional[Context] = None,
        origin: typing.Optional[BaseException] = None,
    ) -> None:
        """
        Initialize a `DetailedError`.

        :param message: The error message for the field error
        :param parent_name: Optional name for the parent context
        :param expected_type: Optional expected type for the field or context
        :param input_type: Optional input type that caused the error
        :param location: Optional location(s) of the error in the data structure.
            Can be an integer(index) or any stringable value.
        :param code: Optional error code for the error detail
        :param context: Optional context dictionary for additional information
        """
        super().__init__(message)
        self.parent_name = parent_name
        self.error_list: typing.List[ErrorDetail] = []
        self.add_detail(
            message=message,
            expected_type=expected_type,
            input_type=input_type,
            location=location,
            code=code or "error",
            context=context,
            origin=origin,
        )

    def add_detail(
        self,
        message: str,
        *,
        location: typing.Optional[typing.List[typing.Any]] = None,
        expected_type: typing.Optional[typing.Any] = None,
        input_type: typing.Optional[typing.Any] = None,
        code: typing.Optional[str] = None,
        context: typing.Optional[Context] = None,
        origin: typing.Optional[BaseException] = None,
    ) -> None:
        """
        Add a new error detail directly to the error list.

        :param message: The error message for the detail
        :param location: Optional location(s) of the error in the data structure.
            Can be an integer(index) or any stringable value.
        :param expected_type: Optional expected type for the field or context
        :param input_type: Optional input type that caused the error
        :param code: Optional error code for the error detail
        :param context: Optional context dictionary for additional information
        """
        detail = ErrorDetail(
            message=message,
            expected_type=expected_type,
            input_type=input_type,
            location=list(filter(lambda x: x is not None, location or [])),
            code=code,
            context=context,
            origin=origin,
        )
        self.error_list.append(detail)

    @classmethod
    def from_exception(
        cls,
        exception: BaseException,
        *,
        message: typing.Optional[str] = None,
        parent_name: typing.Optional[str] = None,
        expected_type: typing.Optional[typing.Any] = None,
        input_type: typing.Optional[typing.Any] = None,
        location: typing.Optional[typing.List[typing.Any]] = None,
        code: typing.Optional[str] = None,
        context: typing.Optional[Context] = None,
    ) -> Self:
        """
        Create a detailed error from any exception type.

        :param exception: The exception to convert into a DetailedError
        :param message: Optional message to use for the error detail
        :param parent_name: Optional name for the parent context
        :param expected_type: Optional expected type for the field or context
        :param input_type: Optional input type that caused the error
        :param location: Optional location(s) of the error in the data structure.
            Can be an integer(index) or any stringable value.
        :param code: Optional error code for the error detail
        :param context: Optional context dictionary for additional information
        :return: A new `DetailedError` instance with the provided details
        """
        exception_msg = exception.args[0] if exception.args else None
        try:
            exception_msg = str(exception_msg)
        except Exception:
            exception_msg = f"<unprintable {type(exception_msg).__name__}>"

        msg = f"{message or ''}\n  {exception_msg}".strip()
        new = cls(
            parent_name=parent_name,
            message=msg,
            expected_type=expected_type,
            input_type=input_type,
            location=location,
            code=code or ERROR_CODE_MAPPING.get(type(exception), None),
            context=context,
            origin=exception,
        )
        if isinstance(exception, DetailedError):
            new.error_list.clear()
            new.merge(exception, location=location)
        return new

    def merge(
        self,
        other: "DetailedError",
        location: typing.Optional[typing.List[typing.Any]] = None,
    ) -> None:
        """
        Merge another `DetailedError` into this one.

        :param other: The other DetailedError to merge
        :param location: Optional location(s) to prepend to the error details
        """
        location = location or []
        for detail in other.error_list:
            loc = list(filter(lambda x: x is not None, [*location, *detail.location]))
            self.add_detail(
                message=detail.message,
                expected_type=detail.expected_type,
                input_type=detail.input_type,
                location=loc,
                code=detail.code,
                context=detail.context,
                origin=detail.origin or other,
            )

    def add(
        self,
        exception: Exception,
        *,
        message: typing.Optional[str] = None,
        parent_name: typing.Optional[str] = None,
        expected_type: typing.Optional[typing.Any] = None,
        input_type: typing.Optional[typing.Any] = None,
        location: typing.Optional[typing.List[typing.Any]] = None,
        code: typing.Optional[str] = None,
        context: typing.Optional[Context] = None,
    ) -> None:
        """
        Add an exception as a new error detail.

        :param exception: The exception to add as an error detail
        :param message: Optional message to use for the error detail
        :param parent_name: Optional name for the parent context
        :param expected_type: Optional expected type for the field or context
        :param input_type: Optional input type that caused the error
        :param location: Optional location(s) of the error in the data structure.
            Can be an integer(index) or any stringable value.

        :param code: Optional error code for the error detail
        :param context: Optional context dictionary for additional information
        """
        if not isinstance(exception, DetailedError):
            self.merge(
                self.from_exception(
                    exception,
                    message=message,
                    parent_name=parent_name,
                    expected_type=expected_type,
                    input_type=input_type,
                    location=location,
                    code=code,
                    context=context,
                ),
            )
        else:
            self.merge(exception, location=location)

    @classmethod
    @contextmanager
    def collect(
        cls,
        target: typing.Union[
            typing.Type[Exception], typing.Tuple[typing.Type[Exception]]
        ] = Exception,
        /,
        message: str = "Collected errors",
        *,
        parent_name: typing.Optional[str] = None,
        location: typing.Optional[typing.List[typing.Any]] = None,
    ) -> typing.Generator["DetailedError", None, None]:
        """
        Context manager to collect errors raised within a block of code.

        This context manager will catch exceptions of the specified type(s) and
        collect them into a `DetailedError`. If multiple errors are caught or added,
        they will be merged into a single `DetailedError` instance, which
        will be raised at the end of the block.

        :param target: The exception type(s) to catch and collect
        :param parent_name: Optional name for the parent context
        :param message: The message to use for the `DetailedError` if multiple errors are collected
        :param location: Optional location(s) to prepend to the error details
        :return: A `DetailedError` instance that collects errors raised in the block
        :raises DetailedError: If any errors are collected or added during the block execution

        Example:
        ```python
        with DetailedError.collect((ValueError, TypeError), location=["parent"]) as errors:
            # Code that might raise an error or exception
            if invalid:
                errors.add("Invalid value", location=["child"])
        ```
        """
        errors = cls(
            message=message,
            parent_name=parent_name,
            location=location,
        )
        collected = []

        try:
            yield errors
        except target as exc:
            if exc is errors:
                pass
            if isinstance(exc, DetailedError):
                collected.append(exc)
            else:
                collected.append(cls.from_exception(exc))

        if collected or len(errors.error_list) > 1:
            for error in collected:
                errors.merge(error, location=location)
            raise errors

    def error_messages(self) -> typing.Generator[str, None, None]:
        """Yield error messages as strings."""
        for error_detail in self.error_list:
            yield error_detail.as_string()

    def errors(self) -> typing.Generator[typing.Dict[str, typing.Any], None, None]:
        """Yield error details as JSON-serializable dictionaries."""
        for error_detail in self.error_list:
            yield error_detail.as_json()

    def __str__(self) -> str:
        """Return a string representation of the detailed field error."""
        if self.error_list:
            return "\n".join(
                [
                    f"""{len(self.error_list)} error(s){f" in {self.parent_name}" if self.parent_name else ""}""",
                    *self.error_messages(),
                    "\r",
                ]
            )
        return super().__str__()


class ValidationError(DetailedError):
    """Raised when validation fails."""

    def __init__(
        self,
        message: str,
        *,
        parent_name: typing.Optional[str] = None,
        expected_type: typing.Optional[typing.Any] = None,
        input_type: typing.Optional[typing.Any] = None,
        location: typing.Optional[typing.List[typing.Any]] = None,
        code: typing.Optional[str] = None,
        context: typing.Optional[Context] = None,
        origin: typing.Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message=message,
            parent_name=parent_name,
            expected_type=expected_type,
            input_type=input_type,
            location=location,
            code=code or "validation_failed",
            context=context,
            origin=origin,
        )


class SerializationError(DetailedError):
    """Raised for serialization errors."""

    def __init__(
        self,
        message: str,
        *,
        parent_name: typing.Optional[str] = None,
        expected_type: typing.Optional[typing.Any] = None,
        input_type: typing.Optional[typing.Any] = None,
        location: typing.Optional[typing.List[typing.Any]] = None,
        code: typing.Optional[str] = None,
        context: typing.Optional[Context] = None,
        origin: typing.Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message=message,
            parent_name=parent_name,
            expected_type=expected_type,
            input_type=input_type,
            location=location,
            code=code or "serialization_failed",
            context=context,
            origin=origin,
        )


class DeserializationError(DetailedError):
    """Raised for deserialization errors."""

    def __init__(
        self,
        message: str,
        *,
        parent_name: typing.Optional[str] = None,
        expected_type: typing.Optional[typing.Any] = None,
        input_type: typing.Optional[typing.Any] = None,
        location: typing.Optional[typing.List[typing.Any]] = None,
        code: typing.Optional[str] = None,
        context: typing.Optional[Context] = None,
        origin: typing.Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message=message,
            parent_name=parent_name,
            expected_type=expected_type,
            input_type=input_type,
            location=location,
            code=code or "coercion_failed",
            context=context,
            origin=origin,
        )


class InvalidTypeError(DeserializationError):
    """Validation error raised when an invalid unexpected type is encountered."""

    def __init__(
        self,
        message: str,
        *,
        parent_name: typing.Optional[str] = None,
        expected_type: typing.Optional[typing.Any] = None,
        input_type: typing.Optional[typing.Any] = None,
        location: typing.Optional[typing.List[typing.Any]] = None,
        code: typing.Optional[str] = None,
        context: typing.Optional[Context] = None,
        origin: typing.Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message=message,
            parent_name=parent_name,
            expected_type=expected_type,
            input_type=input_type,
            location=location,
            code=code or "invalid_type",
            context=context,
            origin=origin,
        )


ERROR_CODE_MAPPING = {
    TypeError: "invalid_type",
    ValueError: "invalid_value",
    ValidationError: "validation_failed",
    SerializationError: "serialization_failed",
    DeserializationError: "coercion_failed",
    InvalidTypeError: "invalid_type",
}
