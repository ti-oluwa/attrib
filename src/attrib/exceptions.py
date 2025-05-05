class FieldError(Exception):
    """Exception raised for field-related errors."""

    pass


class FieldValidationError(FieldError):
    """Exception raised for validation errors."""

    pass


class SerializationError(Exception):
    """Exception raised for serialization errors."""

    pass


class DeserializationError(Exception):
    """Exception raised for deserialization errors."""

    pass


class FrozenError(Exception):
    """Exception raised for frozen data classes."""

    pass


class FrozenFieldError(FrozenError):
    """Exception raised for frozen fields."""

    pass


class FrozenInstanceError(FrozenError):
    """Exception raised for frozen instances."""

    pass
