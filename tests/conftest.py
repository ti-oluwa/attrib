import datetime
from decimal import Decimal
import enum
import typing

import pytest

import attrib


class Status(enum.Enum):
    """Test status enumeration."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


class Priority(enum.IntEnum):
    """Test priority enumeration."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


class Address(attrib.Dataclass):
    """Simple address dataclass."""

    street = attrib.field(str)
    city = attrib.field(str)
    country = attrib.field(str, default="USA")
    zipcode = attrib.field(str, allow_null=True, default=None)


class Person(attrib.Dataclass, getitem=True, setitem=True):
    """Simple person dataclass."""

    name = attrib.field(str)
    age = attrib.field(int)
    email = attrib.field(str, allow_null=True, default=None)


class Company(attrib.Dataclass, frozen=True, hash=True):
    """Frozen company dataclass."""

    id = attrib.field(int, required=True)
    name = attrib.field(str)
    founded = attrib.field(datetime.date, allow_null=True, default=None)
    revenue = attrib.field(Decimal, allow_null=True, default=None)


class Employee(Person):
    """Employee inheriting from Person."""

    employee_id = attrib.field(int)
    company = attrib.field(Company, allow_null=True, default=None)
    hire_date = attrib.field(datetime.date, allow_null=True, default=None)
    status = attrib.field(attrib.Choice, Status, default=Status.ACTIVE)


class Project(attrib.Dataclass):
    """Project dataclass with nested relationships."""

    id = attrib.field(int)
    name = attrib.field(str)
    description = attrib.field(str, allow_null=True, default=None)
    lead = attrib.field(Employee, allow_null=True, default=None)
    members = attrib.field(typing.List[Employee], default=list)
    priority = attrib.field(attrib.Choice, Priority, default=Priority.MEDIUM)
    deadline = attrib.field(datetime.datetime, allow_null=True, default=None)
    tags = attrib.field(typing.List[str], default=list)


@pytest.fixture
def address_data() -> dict:
    """Address data dictionary."""
    return {
        "street": "123 Main St",
        "city": "New York",
        "country": "USA",
        "zipcode": "10001",
    }


@pytest.fixture
def person_data() -> dict:
    """Person data dictionary."""
    return {"name": "John Doe", "age": 30, "email": "john@example.com"}


@pytest.fixture
def company_data() -> dict:
    """Company data dictionary."""
    return {
        "id": 1,
        "name": "Tech Corp",
        "founded": "2020-01-15",
        "revenue": "1000000.50",
    }


@pytest.fixture
def employee_data(company_data: dict) -> dict:
    """Employee data dictionary."""
    return {
        "name": "Jane Smith",
        "age": 28,
        "email": "jane@techcorp.com",
        "employee_id": 1001,
        "company": company_data,
        "hire_date": "2022-03-01",
        "status": "active",
    }


@pytest.fixture
def project_data(employee_data: dict, company_data: dict) -> dict:
    """Project data with nested structures."""
    return {
        "id": 1,
        "name": "Awesome Project",
        "description": "A very cool project",
        "lead": employee_data,
        "members": [
            {
                "name": "Bob Johnson",
                "age": 35,
                "email": "bob@techcorp.com",
                "employee_id": 1002,
                "company": company_data,
                "hire_date": "2021-06-15",
                "status": "active",
            }
        ],
        "priority": 3,
        "deadline": "2024-12-31T23:59:59",
        "tags": ["important", "backend"],
    }


@pytest.fixture
def address(address_data: dict) -> Address:
    """Address instance."""
    return attrib.deserialize(Address, address_data)


@pytest.fixture
def person(person_data: dict) -> Person:
    """Person instance."""
    return attrib.deserialize(Person, person_data)


@pytest.fixture
def company(company_data: dict) -> Company:
    """Company instance."""
    return attrib.deserialize(Company, company_data)


@pytest.fixture
def employee(employee_data: dict) -> Employee:
    """Employee instance."""
    return attrib.deserialize(Employee, employee_data)


@pytest.fixture
def project(project_data: dict) -> Project:
    """Project instance."""
    return attrib.deserialize(Project, project_data)
