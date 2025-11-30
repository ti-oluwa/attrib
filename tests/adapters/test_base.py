import typing
from datetime import datetime, date

import pytest

import attrib
from attrib._utils import iso_parse
from attrib.adapters import TypeAdapter
from attrib.descriptors.datetime import datetime_deserializer
from attrib.exceptions import ValidationError, DeserializationError


class TestTypeAdapterBasics:
    """Test basic TypeAdapter functionality."""

    def test_create_type_adapter(self):
        """Test creating a basic TypeAdapter."""
        adapter = TypeAdapter(int)
        assert adapter.adapted is int

    def test_type_adapter_with_name(self):
        """Test TypeAdapter with custom name."""
        adapter = TypeAdapter(int, name="PositiveInt")
        assert adapter.name == "PositiveInt"

    def test_type_adapter_adapt(self):
        """Test adapt method."""
        adapter = TypeAdapter(int)
        result = adapter.adapt("123")
        assert result == 123
        assert isinstance(result, int)

    def test_type_adapter_validate(self):
        """Test validate method."""
        adapter = TypeAdapter(int, validator=attrib.validators.gt(0))
        adapter.validate(5)  # Should pass

        with pytest.raises(ValidationError):
            adapter.validate(-5)

    def test_type_adapter_deserialize(self):
        """Test deserialize method."""
        adapter = TypeAdapter(int)
        result = adapter.deserialize("42")
        assert result == 42

    def test_type_adapter_serialize(self):
        """Test serialize method."""
        adapter = TypeAdapter(int)
        result = adapter.serialize(42, "python")
        assert result == 42


class TestTypeAdapterWithValidators:
    """Test TypeAdapter with validators."""

    def test_adapter_with_single_validator(self):
        """Test TypeAdapter with single validator."""
        adapter = TypeAdapter(int, validator=attrib.validators.gt(0))
        assert adapter.adapt(5) == 5

        with pytest.raises(ValidationError):
            adapter.adapt(-5)

    def test_adapter_with_multiple_validators(self):
        """Test TypeAdapter with pipeline of validators."""
        adapter = TypeAdapter(
            int,
            validator=attrib.validators.and_(
                attrib.validators.gt(0), attrib.validators.lt(100)
            ),
        )
        assert adapter.adapt(50) == 50

        with pytest.raises(ValidationError):
            adapter.adapt(-5)

        with pytest.raises(ValidationError):
            adapter.adapt(150)

    def test_adapter_strict_mode(self):
        """Test TypeAdapter in strict mode."""
        adapter = TypeAdapter(int, strict=True)
        # In strict mode, should not coerce types
        with pytest.raises(DeserializationError):
            adapter.adapt("123")


class TestTypeAdapterCustomDeserializer:
    """Test TypeAdapter with custom deserializer."""

    def test_custom_deserializer(self):
        """Test TypeAdapter with custom deserializer function."""

        def upper_deserializer(
            value: typing.Any, *arg: typing.Any, **kwargs: typing.Any
        ):
            return str(value).upper()

        adapter = TypeAdapter(str, deserializer=upper_deserializer)
        result = adapter.deserialize("hello")
        assert result == "HELLO"

    def test_custom_deserializer_with_validation(self):
        """Test custom deserializer with validation."""

        def int_from_hex(value: typing.Any, *arg: typing.Any, **kwargs: typing.Any):
            if isinstance(value, str):
                return int(value, 16)
            return int(value)

        adapter = TypeAdapter(
            int, deserializer=int_from_hex, validator=attrib.validators.gt(0)
        )
        result = adapter.adapt("FF")
        assert result == 255

        with pytest.raises(ValidationError):
            adapter.adapt("0")


class TestTypeAdapterCustomSerializer:
    """Test TypeAdapter with custom serializers."""

    def test_custom_serializer(self):
        """Test TypeAdapter with custom serializer."""

        def hex_serializer(value: typing.Any, *args: typing.Any, **kwargs: typing.Any):
            return hex(value)

        adapter = TypeAdapter(int, serializers={"hex": hex_serializer})
        result = adapter.serialize(255, fmt="hex")
        assert result == "0xff"


class TestTypeAdapterComplexTypes:
    """Test TypeAdapter with complex types."""

    def test_adapter_with_list(self):
        """Test TypeAdapter with list type."""
        adapter = TypeAdapter(typing.List[int])
        result = adapter.adapt(["1", "2", "3"])
        assert result == [1, 2, 3]

    def test_adapter_with_dict(self):
        """Test TypeAdapter with dict type."""
        adapter = TypeAdapter(typing.Dict[str, int])
        result = adapter.adapt({"a": "1", "b": "2"})
        assert result == {"a": 1, "b": 2}

    def test_adapter_with_optional(self):
        """Test TypeAdapter with Optional type."""
        adapter = TypeAdapter(typing.Optional[int])

        result = adapter.adapt(None)
        assert result is None

        result = adapter.adapt("42")
        assert result == 42


class TestTypeAdapterCheckType:
    """Test TypeAdapter check_type method."""

    def test_check_type_correct(self):
        """Test check_type with correct type."""
        adapter = TypeAdapter(int)
        assert adapter.check_type(42) is True

    def test_check_type_incorrect(self):
        """Test check_type with incorrect type."""
        adapter = TypeAdapter(int, strict=True)
        assert adapter.check_type("42") is False
        # In non-strict mode, might try to coerce
        # In strict mode, should return False

    def test_instance_check(self):
        """Test isinstance with TypeAdapter."""
        adapter = TypeAdapter(int)
        assert isinstance(10, adapter)  # type: ignore
        assert not isinstance("1", adapter)  # type: ignore


class TestTypeAdapterBuild:
    """Test TypeAdapter build method."""

    def test_deferred_build(self):
        """Test TypeAdapter with deferred build."""
        adapter = TypeAdapter(int, defer_build=True)
        # Should not be built yet

        adapter.build()
        # Now should be built and functional
        result = adapter.adapt("42")
        assert result == 42

    def test_forward_reference_build(self):
        """Test building TypeAdapter with forward reference."""
        # This test depends on having forward references available
        pass


class TestTypeAdapterIntegrationWithFields:
    """Test TypeAdapter integration with dataclass fields."""

    def test_field_with_type_adapter(self):
        """Test using TypeAdapter with dataclass field."""
        positive_int = TypeAdapter(
            int, name="PositiveInt", validator=attrib.validators.gt(0)
        )

        class TestClass(attrib.Dataclass):
            value = attrib.field(positive_int)

        instance = TestClass(value=5)
        assert instance.value == 5

        with pytest.raises(
            DeserializationError,
            check=lambda e: isinstance(e.error_list[0].origin, ValidationError),
        ):
            TestClass(value=-5)

    def test_field_with_custom_adapter(self):
        """Test field with custom TypeAdapter."""

        def even_validator(value, adapter, *args, **kwargs):
            if value % 2 != 0:
                raise ValueError(f"{value} is not even")

        even_int = TypeAdapter(int, name="EvenInt", validator=even_validator)

        class TestClass(attrib.Dataclass):
            even_value = attrib.field(even_int)

        instance = TestClass(even_value=4)
        assert instance.even_value == 4

        with pytest.raises(
            DeserializationError,
            check=lambda e: isinstance(e.error_list[0].origin, ValueError),
        ):
            TestClass(even_value=3)


class TestTypeAdapterErrors:
    """Test TypeAdapter error handling."""

    def test_deserialization_error(self):
        """Test DeserializationError handling."""
        adapter = TypeAdapter(int)

        with pytest.raises((DeserializationError, ValidationError, ValueError)):
            adapter.adapt("not a number")

    def test_validation_error(self):
        """Test ValidationError from validator."""
        adapter = TypeAdapter(int, validator=attrib.validators.gt(10))

        with pytest.raises(ValidationError):
            adapter.adapt(5)


class TestTypeAdapterReuse:
    """Test reusing TypeAdapter instances."""

    def test_adapter_reuse(self):
        """Test that TypeAdapter can be reused multiple times."""
        adapter = TypeAdapter(int)

        result1 = adapter.adapt("42")
        result2 = adapter.adapt("100")
        result3 = adapter.adapt("999")

        assert result1 == 42
        assert result2 == 100
        assert result3 == 999

    def test_adapter_reuse_with_validation(self):
        """Test reusing TypeAdapter with validation."""
        adapter = TypeAdapter(
            int,
            validator=attrib.validators.and_(
                attrib.validators.gt(0), attrib.validators.lt(100)
            ),
        )

        assert adapter.adapt(50) == 50
        assert adapter.adapt(25) == 25

        with pytest.raises(ValidationError):
            adapter.adapt(150)


class TestTypeAdapterDatetime:
    """Test TypeAdapter with datetime types."""

    def test_datetime_adapter(self):
        """Test TypeAdapter with datetime."""
        adapter = TypeAdapter(datetime, deserializer=lambda v, *_, **__: iso_parse(v))
        result = adapter.adapt("2024-01-01T12:00:00")
        assert isinstance(result, datetime)
        assert result.year == 2024

    def test_date_adapter(self):
        """Test TypeAdapter with date."""
        adapter = TypeAdapter(
            date, deserializer=lambda v, *_, **__: iso_parse(v).date()
        )
        result = adapter.adapt("2024-01-01")
        assert isinstance(result, date)
        assert result.year == 2024
