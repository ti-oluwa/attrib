import enum
import random
import typing
from datetime import datetime, date

import attrib
from utils import timeit, profileit, log
from mock_data import course_data, student_data, year_data


########################
##### Data Classes #####
########################


class Term(enum.Enum):
    """Academic term enumeration"""

    FIRST = "First"
    SECOND = "Second"
    THIRD = "Third"


class AcademicYear(attrib.Dataclass, repr=False):
    """Academic year data class"""

    id = attrib.field(int, required=True)
    name = attrib.field(str, max_length=100)
    term = attrib.field(attrib.Choice[Term], default=Term.FIRST)
    start_date = attrib.field(date, input_formats=["%d-%m-%Y", "%d/%m/%Y"])
    end_date = attrib.field(date, input_formats=["%d-%m-%Y", "%d/%m/%Y"])
    created_at = attrib.field(datetime, default=datetime.now)


class Course(attrib.Dataclass, sort=True, repr=False, hash=True, frozen=True):
    """Course data class"""

    id = attrib.field(int, required=True, allow_null=True)
    name = attrib.field(str, max_length=100)
    code = attrib.field(str, max_length=20)
    year = attrib.field(AcademicYear)
    created_at = attrib.field(datetime, default=datetime.now)


class PersonalInfo(attrib.Dataclass):
    """Personal information data class"""

    name = attrib.field(str, max_length=100)
    age = attrib.field(int, min_value=0, max_value=30)
    email = attrib.field(str, allow_null=True, default=None)
    phone = attrib.field(str, allow_null=True, default=None)

    __config__ = attrib.MetaConfig(sort=True)


class Student(PersonalInfo):
    """Student data class"""

    id = attrib.field(int, required=True)
    level = attrib.field(AcademicYear, allow_null=True, alias="year")
    courses = attrib.field(
        typing.List[Course],
        validator=attrib.validators.and_(
            attrib.validators.min_length(1),
            attrib.validators.max_length(15),
        ),
        serialization_alias="enrolled_in",
    )
    # courses = attrib.List(
    #     child=attrib.field(Course),
    #     validator=attrib.validators.and_(
    #         attrib.validators.min_length(1),
    #         attrib.validators.max_length(15),
    #     ),
    #     serialization_alias="enrolled_in",
    # )
    gpa = attrib.field(
        float, allow_null=True, default=attrib.Factory(random.uniform, a=1, b=5)
    )
    joined_at = attrib.field(datetime, allow_null=True, tz="Africa/Lagos")
    created_at = attrib.field(datetime, default=datetime.now)


DataclassTco = typing.TypeVar("DataclassTco", bound=attrib.Dataclass, covariant=True)


def load(
    data_list: typing.List[typing.Dict[str, typing.Any]],
    cls: typing.Type[DataclassTco],
) -> typing.List[DataclassTco]:
    """
    Load data into data classes

    :param data_list: List of dictionaries containing data
    :param cls: Data class to load data into
    :return: List of the data class instances
    """
    return [
        attrib.deserialize(cls, data, config=attrib.InitConfig(fail_fast=True))
        for data in data_list
    ]


student_options = attrib.Options(
    attrib.Option(Course, recurse=False, exclude={"created_at"})
)

students = load(student_data, Student)
courses = load(course_data, Course)
years = load(year_data, AcademicYear)

# print(
#     attrib.serialize(
#         Student(
#             name="Test",
#             age=20,
#             id=1,
#             courses=courses[2:],
#             level=years[0],
#         ),
#         fmt="json",
#         options=student_options,
#     )
# )


def example(mode: typing.Literal["json", "python"] = "python") -> None:
    """Run example usage of the data classes"""
    for student in students:
        attrib.serialize(
            student,
            fmt=mode,
            # options=student_options,
        )

    for course in courses:
        attrib.serialize(course, fmt=mode)

    for year in years:
        attrib.serialize(year, fmt=mode)


@timeit("attrib")
def test(n: int = 1, mode: str = "python") -> None:
    """Run the attrib example multiple times"""
    for _ in range(n):
        example()
