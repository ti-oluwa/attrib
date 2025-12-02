import typing
from datetime import date, datetime
from decimal import Decimal

import pytest

import attrib
from attrib._field import field, register
from attrib.descriptors.base import (
    Boolean,
    Field,
    Integer,
    String,
)
from attrib.descriptors.base import (
    Decimal as DecimalField,
)
from attrib.exceptions import DeserializationError, InvalidTypeError, ValidationError


class TestFieldCreation:
    """Test field creation function."""

    def test_field_from_builtin_type(self):
        """Test creating field from builtin types."""
        int_field = field(int)
        assert isinstance(int_field, Integer)

        str_field = field(str)
        assert isinstance(str_field, String)

        bool_field = field(bool)
        assert isinstance(bool_field, Boolean)

    def test_field_from_decimal(self):
        """Test creating field from Decimal."""
        dec_field = field(Decimal)
        assert isinstance(dec_field, DecimalField)

    def test_field_from_datetime(self):
        """Test creating field from datetime types."""
        dt_field = field(datetime)
        assert isinstance(dt_field, attrib.DateTime)

        date_field = field(date)
        assert isinstance(date_field, attrib.Date)

    def test_field_with_type_adapter(self):
        """Test creating field with TypeAdapter."""
        adapter = attrib.TypeAdapter(int, validator=attrib.validators.gt(0))
        field_instance = field(adapter)
        assert isinstance(field_instance, Field)

    def test_field_with_dataclass(self):
        """Test creating field from dataclass."""

        class Inner(attrib.Dataclass):
            value = field(int)

        nested_field = field(Inner)
        assert isinstance(nested_field, attrib.Nested)

    def test_field_with_generic_type(self):
        """Test creating field with generic type."""
        list_field = field(typing.List[int])
        assert isinstance(list_field, Field)

    def test_field_with_optional(self):
        """Test creating field with Optional type."""
        optional_field = field(typing.Optional[int])
        assert isinstance(optional_field, Field)


class TestFieldOptions:
    """Test field options and parameters."""

    def test_field_with_default(self):
        """Test field with default value."""

        class TestClass(attrib.Dataclass):
            default_field = field(int, default=42)

        instance = TestClass()
        assert instance.default_field == 42

    def test_field_with_factory(self):
        """Test field with Factory default."""

        class TestClass(attrib.Dataclass):
            list_field = field(typing.List[int], default=attrib.Factory(list))

        instance1 = TestClass()
        instance2 = TestClass()
        instance1.list_field.append(1)

        assert len(instance2.list_field) == 0

    def test_field_with_alias(self):
        """Test field with alias."""

        class TestClass(attrib.Dataclass):
            internal_name = field(str, alias="externalName")

        data = {"externalName": "test"}
        instance = attrib.deserialize(TestClass, data)
        assert instance.internal_name == "test"

    def test_field_with_serialization_alias(self):
        """Test field with serialization alias."""

        class TestClass(attrib.Dataclass):
            internal = field(str, serialization_alias="external")

        instance = TestClass(internal="value")
        result = attrib.serialize(instance, fmt="python", by_alias=True)
        assert "external" in result

    def test_field_with_allow_null(self):
        """Test field with allow_null."""

        class TestClass(attrib.Dataclass):
            nullable_field = field(int, allow_null=True, default=None)

        instance = TestClass()
        assert instance.nullable_field is None

    def test_field_with_validator(self):
        """Test field with validator."""

        class TestClass(attrib.Dataclass):
            positive = field(int, validator=attrib.validators.gt(0))

        instance = TestClass(positive=5)
        assert instance.positive == 5

        with pytest.raises(DeserializationError):
            TestClass(positive=-5)


class TestFieldRegistration:
    """Test custom field registration."""

    def test_register_custom_field_decorator(self):
        """Test registering custom field with decorator."""

        class CustomType:
            def __init__(self, value):
                self.value = value

        @register(CustomType)
        class CustomField(Field):
            pass

        # Now field() should create CustomField for CustomType
        custom_field = field(CustomType, CustomType)
        assert isinstance(custom_field, CustomField)

    def test_register_custom_field_direct(self):
        """Test registering custom field directly."""

        class AnotherType:
            def __init__(self, value):
                self.value = value

        class AnotherField(Field):
            pass

        register(AnotherType, AnotherField)

        another_field = field(AnotherType, AnotherType)
        assert isinstance(another_field, AnotherField)


class TestFieldWithComplexTypes:
    """Test field creation with complex types."""

    def test_field_with_list_type(self):
        """Test field with List type."""

        class TestClass(attrib.Dataclass):
            items = field(typing.List[str])

        instance = TestClass(items=["a", "b", "c"])
        assert instance.items == ["a", "b", "c"]

    def test_field_with_dict_type(self):
        """Test field with Dict type."""

        class TestClass(attrib.Dataclass):
            mapping = field(typing.Dict[str, int])

        instance = TestClass(mapping={"a": 1, "b": 2})
        assert instance.mapping == {"a": 1, "b": 2}

    def test_field_with_union_type(self):
        """Test field with Union type."""

        class TestClass(attrib.Dataclass):
            value = field(typing.Union[int, str])

        instance1 = TestClass(value=42)
        assert instance1.value == 42

        instance2 = TestClass(value="test")
        assert instance2.value == "test"


class TestFieldIntegration:
    """Test field integration with dataclasses."""

    def test_multiple_fields(self):
        """Test dataclass with multiple fields."""

        class TestClass(attrib.Dataclass):
            name = field(str)
            age = field(int)
            email = field(str, allow_null=True, default=None)

        instance = TestClass(name="Test", age=30)
        assert instance.name == "Test"
        assert instance.age == 30
        assert instance.email is None

    def test_nested_fields(self):
        """Test nested dataclass fields."""

        class Inner(attrib.Dataclass):
            value = field(int)

        class Outer(attrib.Dataclass):
            inner = field(Inner)

        data = {"inner": {"value": 42}}
        instance = attrib.deserialize(Outer, data)
        assert instance.inner.value == 42


class TestFieldEdgeCases:
    """Test edge cases in field creation."""

    def test_field_defer_build(self):
        """Test field with defer_build option."""

        # Forward reference handling
        class TestClass(attrib.Dataclass):
            value = field(int, defer_build=True)

        instance = TestClass(value=42)
        assert instance.value == 42

    def test_field_with_strict_mode(self):
        """Test field with strict mode."""

        class TestClass(attrib.Dataclass):
            strict_int = field(int, strict=True)

        # In strict mode, should not coerce types
        with pytest.raises(
            DeserializationError,
            check=lambda e: isinstance(e.error_list[0].origin, InvalidTypeError),
        ):
            attrib.deserialize(TestClass, {"strict_int": "42"})


class TestFieldDescriptor:
    """Test Field as descriptor."""

    def test_field_get_set(self):
        """Test getting and setting field value."""

        class TestClass(attrib.Dataclass):
            value = field(int)

        instance = TestClass(value=42)
        assert instance.value == 42

        instance.value = 100
        assert instance.value == 100

    def test_field_set_validates(self):
        """Test that setting field value validates."""

        class TestClass(attrib.Dataclass):
            positive = field(int, validator=attrib.validators.gt(0))

        instance = TestClass(positive=5)

        with pytest.raises(ValidationError):
            instance.positive = -5


class TestFieldTypeCoercion:
    """Test field type coercion."""

    def test_int_field_coerces_string(self):
        """Test that int field coerces string."""

        class TestClass(attrib.Dataclass):
            value = field(int)

        instance = attrib.deserialize(TestClass, {"value": "42"})
        assert instance.value == 42
        assert isinstance(instance.value, int)

    def test_float_field_coerces_int(self):
        """Test that float field coerces int."""

        class TestClass(attrib.Dataclass):
            value = field(float)

        instance = attrib.deserialize(TestClass, {"value": 42})
        assert instance.value == 42.0
        assert isinstance(instance.value, float)

    def test_bool_field_coerces(self):
        """Test that bool field coerces values."""

        class TestClass(attrib.Dataclass):
            flag = field(bool)

        # Test various truthy/falsy values
        instance1 = attrib.deserialize(TestClass, {"flag": 1})
        assert instance1.flag is True

        instance2 = attrib.deserialize(TestClass, {"flag": 0})
        assert instance2.flag is False
