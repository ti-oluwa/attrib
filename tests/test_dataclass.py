import typing

import pytest

import attrib
from attrib.exceptions import DeserializationError, FrozenInstanceError, ValidationError
from tests.conftest import Address, Company, Employee, Person, Project


class TestDataclassBasics:
    """Test basic dataclass functionality."""

    def test_simple_dataclass_creation(self, person_data: dict):
        """Test creating a simple dataclass instance."""
        person = attrib.deserialize(Person, person_data)
        assert person.name == "John Doe"
        assert person.age == 30
        assert person.email == "john@example.com"

    def test_dataclass_with_defaults(self):
        """Test dataclass with default values."""
        address = Address(street="123 Main", city="NYC")
        assert address.country == "USA"
        assert address.zipcode is None

    def test_dataclass_required_fields(self):
        """Test that required fields are enforced."""
        with pytest.raises(
            DeserializationError,
            check=lambda e: isinstance(e.error_list[0].origin, ValidationError),
        ):
            attrib.deserialize(Company, {"name": "Test"})

    def test_dataclass_repr(self, person: Person):
        """Test dataclass __repr__ method."""
        repr_str = repr(person)
        assert "Person" in repr_str

    def test_dataclass_equality(self, person_data: dict):
        """Test dataclass equality comparison."""
        person1 = attrib.deserialize(Person, person_data)
        person2 = attrib.deserialize(Person, person_data)
        assert person1 == person2

    def test_dataclass_getitem(self, person: Person):
        """Test dataclass item access."""
        assert person["name"] == "John Doe"
        assert person["age"] == 30

    def test_dataclass_setitem(self, person: Person):
        """Test dataclass item assignment."""
        person["age"] = 31
        assert person.age == 31


class TestFrozenDataclass:
    """Test frozen dataclass functionality."""

    def test_frozen_dataclass_immutable(self, company: Company):
        """Test that frozen dataclass cannot be modified."""
        with pytest.raises(FrozenInstanceError):
            company.name = "New Name"

    def test_frozen_dataclass_delete_attr(self, company: Company):
        """Test that frozen dataclass attributes cannot be deleted."""
        with pytest.raises(FrozenInstanceError):
            del company.name

    def test_frozen_dataclass_hash(self, company_data: dict):
        """Test that frozen dataclass is hashable."""
        company1 = attrib.deserialize(Company, company_data)
        company2 = attrib.deserialize(Company, company_data)
        assert hash(company1) == hash(company2)
        # Test can be used in set
        companies = {company1, company2}
        assert len(companies) == 1


class TestDataclassInheritance:
    """Test dataclass inheritance."""

    def test_inherited_fields(self, employee: Employee):
        """Test that inherited fields are accessible."""
        assert employee.name == "Jane Smith"
        assert employee.age == 28
        assert employee.employee_id == 1001


class TestNestedDataclasses:
    """Test nested dataclass structures."""

    def test_nested_deserialization(self, employee: Employee):
        """Test deserializing nested dataclasses."""
        assert isinstance(employee.company, Company)
        assert employee.company.name == "Tech Corp"

    def test_deeply_nested_deserialization(self, project: Project):
        """Test deserializing deeply nested structures."""
        assert isinstance(project.lead, Employee)
        assert isinstance(project.lead.company, Company)
        assert len(project.members) == 1
        assert all(isinstance(m, Employee) for m in project.members)

    def test_nested_list_deserialization(self, project: Project):
        """Test deserializing lists of nested dataclasses."""
        assert len(project.members) == 1
        assert project.members[0].name == "Bob Johnson"


class TestDataclassValidation:
    """Test dataclass field validation."""

    def test_allow_null_validation(self):
        """Test allow_null field option."""
        person = Person(name="Test", age=30, email=None)
        assert person.email is None

    def test_type_validation(self):
        """Test type checking."""
        with pytest.raises(DeserializationError):
            attrib.deserialize(Person, {"name": "Test", "age": "not an int"})


class TestDataclassCopy:
    """Test dataclass copy functionality."""

    def test_copy_dataclass(self, person: Person):
        """Test copying a dataclass instance."""
        person_copy = attrib.copy(person)
        assert person_copy == person
        assert person_copy is not person

    def test_evolve_dataclass(self, person: Person):
        """Test evolving a dataclass with new values."""
        evolved = attrib.evolve(person, age=31)
        assert evolved.age == 31
        assert evolved.name == person.name
        assert evolved is not person

    def test_evolve_frozen_dataclass(self, company: Company):
        """Test evolving a frozen dataclass."""
        evolved = attrib.evolve(company, name="New Company")
        assert evolved.name == "New Company"
        assert evolved.id == company.id


class TestDataclassUtils:
    """Test dataclass utility functions."""

    def test_is_dataclass(self):
        """Test is_dataclass function."""
        assert attrib.is_dataclass(Person)
        assert not attrib.is_dataclass(dict)
        assert not attrib.is_dataclass({})

    def test_get_fields(self):
        """Test get_fields function."""
        fields = attrib.get_fields(Person)
        assert isinstance(fields, dict)
        assert "name" in fields
        assert "age" in fields
        assert "email" in fields

    def test_get_field(self):
        """Test get_field function."""
        name_field = attrib.get_field(Person, "name")
        assert name_field is not None
        assert name_field.name == "name"
        assert name_field.field_type is str


class TestDataclassConfig:
    """Test dataclass configuration."""

    def test_config_frozen(self):
        """Test frozen configuration."""

        class FrozenTest(attrib.Dataclass):
            value = attrib.field(int)
            __config__ = attrib.MetaConfig(frozen=True)

        instance = FrozenTest(value=1)
        with pytest.raises(FrozenInstanceError):
            instance.value = 2

    def test_config_sort(self):
        """Test sort configuration."""

        class SortTest(attrib.Dataclass):
            id = attrib.field(int, order=True)
            name = attrib.field(str, order=True)
            __config__ = attrib.MetaConfig(sort=True, order=True)

        instance1 = SortTest(id=1, name="A")
        instance2 = SortTest(id=2, name="B")
        assert instance1 < instance2

    def test_config_repr(self):
        """Test repr configuration."""

        class NoReprTest(attrib.Dataclass):
            value = attrib.field(int)
            __config__ = attrib.MetaConfig(repr=False)

        instance = NoReprTest(value=1)
        repr_str = repr(instance)
        assert "NoReprTest" in repr_str


class TestDataclassFactory:
    """Test Factory default values."""

    def test_factory_list(self):
        """Test Factory with list."""

        class TestClass(attrib.Dataclass):
            items = attrib.field(typing.List[str], default=attrib.Factory(list))

        instance1 = TestClass()
        instance2 = TestClass()
        instance1.items.append("test")
        assert len(instance2.items) == 0  # Ensure separate instances

    def test_factory_with_args(self):
        """Test Factory with arguments."""
        import random

        class TestClass(attrib.Dataclass):
            value = attrib.field(
                float, default=attrib.Factory(random.uniform, a=0, b=1)
            )

        instance = TestClass()
        assert 0 <= instance.value <= 1


class TestDataclassAliases:
    """Test field aliases."""

    def test_deserialization_alias(self):
        """Test deserialization with alias."""

        class TestClass(attrib.Dataclass):
            internal_name = attrib.field(str, alias="externalName")

        data = {"externalName": "test"}
        instance = attrib.deserialize(TestClass, data)
        assert instance.internal_name == "test"

    def test_serialization_alias(self):
        """Test serialization with alias."""

        class TestClass(attrib.Dataclass):
            internal_name = attrib.field(str, serialization_alias="outputName")

        instance = TestClass(internal_name="test")
        result = attrib.serialize(instance, fmt="python", by_alias=True)
        assert "outputName" in result
        assert result["outputName"] == "test"


class TestDataclassFieldsSet:
    """Test __fields_set__ tracking."""

    def test_fields_set_tracking(self, person: Person):
        """Test that __fields_set__ tracks explicitly set fields."""
        if hasattr(person, "__fields_set__"):
            assert "name" in person.__fields_set__
            assert "age" in person.__fields_set__

    def test_fields_set_with_defaults(self):
        """Test __fields_set__ with default values."""
        address = Address(street="123 Main", city="NYC")
        if hasattr(address, "__fields_set__"):
            assert "street" in address.__fields_set__
            assert "city" in address.__fields_set__
