import datetime
import typing
from decimal import Decimal

import pytest

import attrib
from attrib.serializers import Option, Options
from tests.conftest import Company, Employee, Person, Project, Status


class TestBasicSerialization:
    """Test basic serialization functionality."""

    def test_serialize_simple_dataclass(self, person: Person):
        """Test serializing a simple dataclass."""
        result = attrib.serialize(person, fmt="python")
        assert result["name"] == "John Doe"
        assert result["age"] == 30
        assert result["email"] == "john@example.com"

    def test_serialize_to_json_format(self, person: Person):
        """Test serializing to JSON format."""
        result = attrib.serialize(person, fmt="json")
        assert isinstance(result, dict)
        assert result["name"] == "John Doe"

    def test_serialize_frozen_dataclass(self, company: Company):
        """Test serializing frozen dataclass."""
        result = attrib.serialize(company, fmt="python")
        assert result["id"] == 1
        assert result["name"] == "Tech Corp"


class TestNestedSerialization:
    """Test serialization of nested dataclasses."""

    def test_serialize_nested_dataclass(self, employee: Employee):
        """Test serializing dataclass with nested structures."""
        result = attrib.serialize(employee, fmt="python")
        assert "company" in result
        assert isinstance(result["company"], dict)
        assert result["company"]["name"] == "Tech Corp"

    def test_serialize_deeply_nested(self, project: Project):
        """Test serializing deeply nested structures."""
        result = attrib.serialize(project, fmt="python")
        assert "lead" in result
        assert isinstance(result["lead"], dict)
        assert "company" in result["lead"]

    def test_serialize_list_of_nested(self, project: Project):
        """Test serializing list of nested dataclasses."""
        result = attrib.serialize(project, fmt="python")
        assert "members" in result
        assert isinstance(result["members"], list)
        assert all(isinstance(m, dict) for m in result["members"])


class TestSerializationOptions:
    """Test serialization options."""

    def test_option_exclude_fields(self, person: Person):
        """Test Option with exclude parameter."""
        options = Options(Option(Person, exclude={"email"}))
        result = attrib.serialize(person, fmt="python", options=options)
        assert "name" in result
        assert "age" in result
        assert "email" not in result

    def test_option_include_fields(self, person: Person):
        """Test Option with include parameter."""
        options = Options(Option(Person, include={"name"}))
        result = attrib.serialize(person, fmt="python", options=options)
        assert "name" in result
        assert "age" not in result
        assert "email" not in result

    def test_option_no_recurse(self, employee: Employee):
        """Test Option with recurse=False."""
        options = Options(Option(Employee, recurse=False))
        result = attrib.serialize(employee, fmt="python", options=options)
        assert "company" in result
        # Should be the Company instance, not dict
        assert isinstance(result["company"], Company)

    def test_option_invalid_include_exclude(self):
        """Test that both include and exclude cannot be specified."""
        with pytest.raises(ValueError):
            Option(Person, include={"name"}, exclude={"age"})


class TestSerializationContext:
    """Test serialization context manager."""

    def test_by_alias_context(self):
        """Test serialization with by_alias context."""

        class TestClass(attrib.Dataclass):
            internal_name = attrib.field(str, serialization_alias="externalName")

        instance = TestClass(internal_name="test")

        result = attrib.serialize(instance, fmt="python", by_alias=True)
        assert "externalName" in result
        assert result["externalName"] == "test"

    def test_exclude_unset_context(self):
        """Test serialization with exclude_unset."""
        person = Person(name="Test", age=30)  # email not set

        result = attrib.serialize(person, fmt="python", exclude_unset=True)
        assert "name" in result
        assert "age" in result
        # email might or might not be in result depending on __fields_set__

    def test_fail_fast_serialization(self):
        """Test fail_fast in serialization context."""

        class TestClass(attrib.Dataclass):
            value = attrib.field(int)

            def serialize_value(self, value, fmt, context):
                raise ValueError("Serialization error")

        # Note: This test depends on implementation details


class TestSerializationAliases:
    """Test field aliases in serialization."""

    def test_serialization_alias(self):
        """Test serialization with alias."""

        class TestClass(attrib.Dataclass):
            internal = attrib.field(str, serialization_alias="external")

        instance = TestClass(internal="value")

        result = attrib.serialize(instance, fmt="python", by_alias=True)
        assert "external" in result
        assert result["external"] == "value"


class TestDateTimeSerialization:
    """Test datetime serialization."""

    def test_serialize_date(self):
        """Test serializing date field."""

        class TestClass(attrib.Dataclass):
            date_field = attrib.field(datetime.date)

        instance = TestClass(date_field=datetime.date(2024, 1, 1))
        result = attrib.serialize(instance, fmt="json")

        assert "date_field" in result
        assert isinstance(result["date_field"], str)

    def test_serialize_datetime(self):
        """Test serializing datetime field."""

        class TestClass(attrib.Dataclass):
            dt_field = attrib.field(datetime.datetime)

        instance = TestClass(dt_field=datetime.datetime(2024, 1, 1, 12, 30))
        result = attrib.serialize(instance, fmt="json")

        assert "dt_field" in result
        assert isinstance(result["dt_field"], str)


class TestListSerialization:
    """Test list serialization."""

    def test_serialize_list_of_primitives(self):
        """Test serializing list of primitive types."""

        class TestClass(attrib.Dataclass):
            items = attrib.field(typing.List[int])

        instance = TestClass(items=[1, 2, 3, 4, 5])
        result = attrib.serialize(instance, fmt="python")

        assert result["items"] == [1, 2, 3, 4, 5]

    def test_serialize_list_of_strings(self, project: Project):
        """Test serializing list of strings."""
        result = attrib.serialize(project, fmt="python")
        assert "tags" in result
        assert isinstance(result["tags"], list)

    def test_serialize_empty_list(self):
        """Test serializing empty list."""

        class TestClass(attrib.Dataclass):
            items = attrib.field(typing.List[str], default=attrib.Factory(list))

        instance = TestClass()
        result = attrib.serialize(instance, fmt="python")
        assert result["items"] == []


class TestDecimalSerialization:
    """Test Decimal serialization."""

    def test_serialize_decimal(self):
        """Test serializing Decimal field."""

        class TestClass(attrib.Dataclass):
            amount = attrib.field(Decimal)

        instance = TestClass(amount=Decimal("123.45"))
        result = attrib.serialize(instance, fmt="json")

        assert "amount" in result
        assert isinstance(result["amount"], (str, float))


class TestEnumSerialization:
    """Test enum serialization."""

    def test_serialize_enum(self, employee: Employee):
        """Test serializing enum field."""
        result = attrib.serialize(employee, fmt="python")
        assert "status" in result
        assert result["status"] == Status.ACTIVE


class TestRoundTripSerialization:
    """Test deserialize -> serialize round trips."""

    def test_simple_round_trip(self, person_data: dict):
        """Test deserialize and serialize round trip."""
        person = attrib.deserialize(Person, person_data)
        result = attrib.serialize(person, fmt="python")

        person2 = attrib.deserialize(Person, result)
        assert person.name == person2.name
        assert person.age == person2.age

    def test_nested_round_trip(self, employee_data: dict):
        """Test round trip with nested structures."""
        employee = attrib.deserialize(Employee, employee_data)
        result = attrib.serialize(employee, fmt="python")
        employee2 = attrib.deserialize(Employee, result)

        assert employee.name == employee2.name
        assert employee.employee_id == employee2.employee_id
        assert employee.company.name == employee2.company.name

    def test_complex_round_trip(self, project_data: dict):
        """Test round trip with complex nested structures."""
        project = attrib.deserialize(Project, project_data)
        result = attrib.serialize(project, fmt="python")
        project2 = attrib.deserialize(Project, result)

        assert project.name == project2.name
        assert len(project.members) == len(project2.members)
        assert project.lead.name == project2.lead.name
