import pytest

from attrib.exceptions import (
    AttribException,
    ConfigurationError,
    DeserializationError,
    ErrorDetail,
    FieldError,
    FrozenInstanceError,
    SerializationError,
    ValidationError,
)


class TestAttribException:
    """Test base AttribException."""

    def test_attrib_exception_creation(self):
        """Test creating AttribException."""
        exc = AttribException("Test error")
        assert str(exc) == "Test error"

    def test_attrib_exception_inheritance(self):
        """Test that all custom exceptions inherit from AttribException."""
        assert issubclass(ConfigurationError, AttribException)
        assert issubclass(FieldError, AttribException)
        assert issubclass(FrozenInstanceError, AttribException)
        assert issubclass(ValidationError, AttribException)


class TestFieldError:
    """Test FieldError exception."""

    def test_field_error_with_name(self):
        """Test FieldError with field name."""
        exc = FieldError("Invalid value", name="field_name")
        assert exc.name == "field_name"
        assert exc.message == "Invalid value"
        assert "field_name" in str(exc)

    def test_field_error_without_name(self):
        """Test FieldError without field name."""
        exc = FieldError("Invalid value")
        assert exc.name is None
        assert str(exc) == "Invalid value"


class TestFrozenInstanceError:
    """Test FrozenInstanceError exception."""

    def test_frozen_instance_error(self):
        """Test FrozenInstanceError creation."""
        exc = FrozenInstanceError("Cannot modify frozen instance")
        assert "Cannot modify" in str(exc)


class TestErrorListAPI:
    """Test error list API."""

    def test_error_list_access(self):
        """Test accessing the error list."""
        exc = ValidationError(
            "Validation failed", location=["field"], expected_type=int, input_type=str
        )
        assert len(exc.error_list) >= 1
        assert exc.error_list[0].location == ["field"]
        assert exc.error_list[0].expected_type is int
        assert exc.error_list[0].input_type is str

    def test_error_detail_as_string(self):
        """Test ErrorDetail as_string method."""
        detail = ErrorDetail(
            location=["field1"],
            message="Invalid value",
            expected_type=int,
            input_type=str,
        )
        string_repr = detail.as_string()
        assert "field1" in string_repr
        assert "Invalid value" in string_repr

    def test_error_detail_nested_location(self):
        """Test ErrorDetail with nested location."""
        detail = ErrorDetail(
            location=["outer", "inner", 0, "field"], message="Nested error"
        )
        string_repr = detail.as_string()
        assert "outer" in string_repr
        assert "inner" in string_repr


class TestValidationError:
    """Test ValidationError exception."""

    def test_validation_error_creation(self):
        """Test creating ValidationError."""
        exc = ValidationError("Validation failed", location=["field"])
        assert len(exc.error_list) >= 1
        assert "Validation failed" in str(exc)

    def test_validation_error_from_exc(self):
        """Test creating ValidationError from another exception."""
        original = ValueError("Original error")
        exc = ValidationError.from_exc(
            original, message="Wrapped error", location=["field"]
        )
        assert len(exc.error_list) >= 1

    def test_validation_error_add_detail(self):
        """Test adding details to ValidationError."""
        exc = ValidationError("Base error", location=["field1"])

        # Add another error
        new_error = ValueError("Additional error")
        exc.add(new_error, location=["field2"])

        # Should have multiple details
        assert len(exc.error_list) >= 2

    def test_validation_error_add_detail_direct(self):
        """Test adding error detail directly."""
        exc = ValidationError("Base error", location=["field1"])
        exc.add_detail(
            message="Additional error",
            location=["field2"],
            expected_type=int,
            input_type=str,
        )
        assert len(exc.error_list) >= 2


class TestDeserializationError:
    """Test DeserializationError exception."""

    def test_deserialization_error_creation(self):
        """Test creating DeserializationError."""
        exc = DeserializationError(
            "Cannot deserialize", location=["field"], expected_type=int, input_type=str
        )
        assert len(exc.error_list) >= 1

    def test_deserialization_error_from_exc(self):
        """Test creating DeserializationError from exception."""
        original = TypeError("Type error")
        exc = DeserializationError.from_exc(
            original,
            message="Wrapped",
            location=["field"],
            expected_type=int,
            input_type=str,
        )
        assert len(exc.error_list) >= 1

    def test_deserialization_error_with_parent(self):
        """Test DeserializationError with parent_name."""
        exc = DeserializationError.from_exc(
            ValueError("Error"), parent_name="MyClass", location=["field"]
        )
        error_str = str(exc)
        assert "MyClass" in error_str


class TestSerializationError:
    """Test SerializationError exception."""

    def test_serialization_error_creation(self):
        """Test creating SerializationError."""
        exc = SerializationError("Cannot serialize", location=["field"])
        assert len(exc.error_list) >= 1

    def test_serialization_error_from_exc(self):
        """Test creating SerializationError from exception."""
        original = ValueError("Cannot convert")
        exc = SerializationError.from_exc(
            original, message="Wrapped", location=["field"]
        )
        assert len(exc.error_list) >= 1


class TestDetailedErrorIntegration:
    """Test detailed error integration."""

    def test_error_with_context(self):
        """Test error with context information."""
        detail = ErrorDetail(
            location=["field"], message="Error with context", context={"key": "value"}
        )
        assert detail.context == {"key": "value"}

    def test_error_with_code(self):
        """Test error with error code."""
        detail = ErrorDetail(location=["field"], message="Error", code="INVALID_TYPE")
        assert detail.code == "INVALID_TYPE"

    def test_error_with_origin(self):
        """Test error with origin exception."""
        origin = ValueError("Original")
        detail = ErrorDetail(location=["field"], message="Wrapped error", origin=origin)
        assert detail.origin is origin


class TestErrorStringRepresentation:
    """Test error string representations."""

    def test_validation_error_str(self):
        """Test ValidationError string representation."""
        exc = ValidationError("Invalid value", location=["field"])
        error_str = str(exc)
        assert "field" in error_str
        assert "Invalid value" in error_str

    def test_deserialization_error_str(self):
        """Test DeserializationError string representation."""
        exc = DeserializationError(
            "Cannot deserialize", location=["field"], expected_type=int, input_type=str
        )
        error_str = str(exc)
        assert "field" in error_str

    def test_error_with_nested_location(self):
        """Test error string with nested location."""
        exc = ValidationError("Nested error", location=["outer", "inner", 0])
        error_str = str(exc)
        # Should show location path
        assert "outer" in error_str


class TestErrorRaising:
    """Test raising custom exceptions."""

    def test_raise_configuration_error(self):
        """Test raising ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc_info:
            raise ConfigurationError("Config error")
        assert "Config error" in str(exc_info.value)

    def test_raise_field_error(self):
        """Test raising FieldError."""
        with pytest.raises(FieldError) as exc_info:
            raise FieldError("Field error", name="test_field")
        assert "test_field" in str(exc_info.value)

    def test_raise_validation_error(self):
        """Test raising ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("Validation failed", location=["field"])
        assert "Validation failed" in str(exc_info.value)


class TestErrorContext:
    """Test error context functionality."""

    def test_error_detail_without_origin(self):
        """Test ErrorDetail without origin."""
        detail = ErrorDetail(location=["field"], message="Error", origin=None)
        assert detail.origin is None

    def test_error_detail_full(self):
        """Test ErrorDetail with all parameters."""
        origin = ValueError("Origin")
        detail = ErrorDetail(
            location=["a", "b", "c"],
            message="Full error",
            expected_type=int,
            input_type=str,
            code="TYPE_ERROR",
            context={"info": "value"},
            origin=origin,
        )
        assert detail.location == ["a", "b", "c"]
        assert detail.message == "Full error"
        assert detail.expected_type is int
        assert detail.input_type is str
        assert detail.code == "TYPE_ERROR"
        assert detail.context == {"info": "value"}
        assert detail.origin is origin
        assert detail.origin is origin
