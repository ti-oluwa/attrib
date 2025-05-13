class AttribError(Exception):
    """Base exception for all attrib-related errors."""

    pass


class FieldError(AttribError):
    """Raised for field-related errors."""

    pass


class ValidationError(AttribError):
    """Raised when validation fails."""

    pass


class SerializationError(AttribError):
    """Raised for serialization errors."""

    pass


class DeserializationError(AttribError):
    """Raised for deserialization errors."""

    pass


class FrozenInstanceError(AttribError):
    """Raised when trying to modify a frozen instance."""

    pass
