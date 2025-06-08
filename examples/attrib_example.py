import enum
import random
import typing
from datetime import datetime

import attrib
from attrib.descriptors.phonenumbers import PhoneNumber
from utils import timeit
from mock_data import course_data, student_data, year_data


########################
##### Data Classes #####
########################


class Term(enum.Enum):
    """Academic term enumeration"""

    FIRST = "First"
    SECOND = "Second"
    THIRD = "Third"


class AcademicYear(attrib.Dataclass, repr=True):
    """Academic year data class"""

    id = attrib.Field(int, required=True)
    name = attrib.String(max_length=100)
    term = attrib.Choice(Term, default=Term.FIRST)
    start_date = attrib.Date(input_formats=["%d-%m-%Y", "%d/%m/%Y"])
    end_date = attrib.Date(input_formats=["%d-%m-%Y", "%d/%m/%Y"])
    created_at = attrib.DateTime(default=datetime.now)


class Course(attrib.Dataclass, sort=True):
    """Course data class"""

    id = attrib.Integer(required=True, allow_null=True)
    name = attrib.String(max_length=100)
    code = attrib.String(max_length=20)
    year = attrib.Nested(AcademicYear, lazy=False)
    created_at = attrib.DateTime(default=datetime.now)


class PersonalInfo(attrib.Dataclass):
    """Personal information data class"""

    name = attrib.String(max_length=100)
    age = attrib.Integer(min_value=0, max_value=30)
    email = attrib.Email(allow_null=True, default=None)
    phone = PhoneNumber(allow_null=True, default=None)

    __config__ = attrib.Config(
        frozen=True,
        hash=True,
        pickleable=True,
    )


@attrib.ordered(include=["id", "name", "level", "gpa"])
class Student(PersonalInfo):
    """Student data class"""

    id = attrib.Integer(required=True)
    level = attrib.Nested(AcademicYear, allow_null=True, alias="year")
    courses = attrib.List(
        child=attrib.Nested(Course, lazy=False),
        validator=attrib.validators.and_(
            attrib.validators.min_length(1), attrib.validators.max_length(15)
        ),
        fail_fast=True,
        serialization_alias="enrolled_in",
    )
    gpa = attrib.Float(
        allow_null=True, default=attrib.Factory(random.uniform, a=1, b=5)
    )
    joined_at = attrib.DateTime(allow_null=True, tz="Africa/Lagos")
    created_at = attrib.DateTime(default=datetime.now)


DataclassTco = typing.TypeVar(
    "DataclassTco",
    bound=attrib.Dataclass,
    covariant=True,
)

def load_data(
    data_list: typing.List[typing.Dict[str, typing.Any]],
    cls: typing.Type[DataclassTco],
) -> typing.List[DataclassTco]:
    """
    Load data into data classes

    :param data_list: List of dictionaries containing data
    :param cls: Data class to load data into
    :return: List of the data class instances
    """
    return [attrib.deserialize(cls, data) for data in data_list]


def example() -> None:
    """Run example usage of the data classes"""
    with attrib.deserialization_context(
        fail_fast=True,
        ignore_extras=True,
    ):
        students = load_data(student_data, Student)
        courses = load_data(course_data, Course)
        years = load_data(year_data, AcademicYear)

    for student in students:
        attrib.serialize(student, fmt="python", by_alias=True)

    for course in courses:
        attrib.serialize(course, fmt="python")

    for year in years:
        attrib.serialize(year, fmt="python")


@timeit("attrib")
def test(n: int = 1) -> None:
    """Run the attrib example multiple times"""
    for _ in range(n):
        example()
