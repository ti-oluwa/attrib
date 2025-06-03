import enum
import random
import typing
import functools
from datetime import datetime
import tracemalloc
import gc
from memory_profiler import profile

import attrib
from attrib.descriptors.phonenumbers import PhoneNumber
from attrib._utils import _unsupported_serializer
from utils import timeit, profileit, log
from mock_data import course_data, student_data, year_data

DataclassTco = typing.TypeVar(
    "DataclassTco",
    bound=attrib.Dataclass,
    covariant=True,
)


########################
##### Data Classes #####
########################


class Term(enum.Enum):
    """Academic term enumeration"""

    FIRST = "First"
    SECOND = "Second"
    THIRD = "Third"


class AcademicYear(attrib.Dataclass, slots=True, repr=True):
    """Academic year data class"""

    id = attrib.Integer(required=True)
    name = attrib.String(max_length=100)
    term = attrib.Choice(Term, default=Term.FIRST)
    start_date = attrib.Date(input_formats=["%d-%m-%Y", "%d/%m/%Y"])
    end_date = attrib.Date(input_formats=["%d-%m-%Y", "%d/%m/%Y"])
    created_at = attrib.DateTime(default=datetime.now, tz="Africa/Lagos")


class Course(attrib.Dataclass, slots=True, sort=True):
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
        slots=True,
        frozen=True,
        pickleable=True,
    )


@attrib.partial
class Student(PersonalInfo):
    """Student data class with multiple fields and a list of enrolled courses"""

    id = attrib.Integer(required=True)
    level = attrib.Nested(AcademicYear, lazy=True, allow_null=True, alias="year")
    courses = attrib.List(
        child=attrib.Nested(Course, lazy=False),
        validator=attrib.validators.and_(
            attrib.validators.min_length(1), attrib.validators.max_length(15)
        ),
        fail_fast=True,
        serialization_alias="enrolled_in",
    )
    gpa = attrib.Float(
        allow_null=True, default=attrib.Factory(random.randint, a=1, b=5)
    )
    joined_at = attrib.DateTime(allow_null=True, tz="Africa/Lagos")
    created_at = attrib.DateTime(default=datetime.now, tz="Africa/Lagos")

    __config__ = attrib.Config(
        slots=("__dict__",),
    )

    @functools.cached_property
    def full_name(self) -> str:
        """Return the full name of the student"""
        return f"{self.name} (ID: {self.id})"


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


def example():
    """Run example usage of the data classes"""
    with attrib.deserialization_context(
        # fail_fast=True,
        # by_name=True,
        ignore_extras=True,
    ):
        students = load_data(student_data, Student)
        courses = load_data(course_data, Course)
        years = load_data(year_data, AcademicYear)

    for student in students:
        # log(
            attrib.serialize(
                student,
                fmt="json",
                # options=attrib.Options(
                #     attrib.Option(
                #         Student,
                #         include={"courses", "name", "age", "gpa", "level"},
                #         depth=1,
                #     ),
                #     attrib.Option(
                #         Course,
                #         include={"code", "name", "year"},
                #         depth=0,
                #         strict=True,
                #     ),
                #     attrib.Option(exclude={"created_at", "id"}, depth=1),
                # ), 
                astuple=False,
                # by_alias=True,
                # exclude_unset=True,
            )
        # )

    for course in courses:
        attrib.serialize(course, fmt="json", astuple=False)

    for year in years:
        attrib.serialize(year, fmt="json", astuple=False)

    # import pickle

    # dump = pickle.dumps(students)
    # loaded_students = pickle.loads(dump)
    # log(
    #     "Loaded Students: ",
    #     [attrib.serialize(student, fmt="json") for student in loaded_students],
    # )

    # # Access and print a student's information
    # student = students[0]  # e.g., first student in the list
    # log(
    #     attrib.serialize(student, options=attrib.Options(attrib.Option(depth=2)))
    # )  # View student details in dictionary format
    # # Modify the student's academic year
    # student.year = years[1]  # Update academic year to next year
    # log(f"Updated Academic Year for {student.name}: ", attrib.serialize(student))

    # # Serialize the student's data to JSON format
    # student_json = attrib.serialize(
    #     student, fmt="json", options=attrib.Options(attrib.Option(depth=0))
    # )
    # log("Serialized Student JSON: ", student_json)

    # # Nesting and Data Validation Example
    # # Changing a course's academic year in a nested structure
    # courses[0].year = years[1]  # Update the academic year for a course
    # log(f"Updated Course Year for {courses[0].name}: ", attrib.serialize(courses[0]))

    # # Update the `year` attribute directly with a new dictionary
    # student.year = {
    #     "id": 4,
    #     "name": "2022/2023",
    #     "start_date": "2022-09-01",
    #     "end_date": "2023-06-30",
    # }
    # log(
    #     f"Updated Academic Year for {student.name}: ",
    #     attrib.serialize(student, options=attrib.Options(attrib.Option(depth=2))),
    # )

    # # Adding a new course to a student and displaying
    # new_course = Course(
    #     {
    #         "id": 4,
    #         "name": "Organic Chemistry",
    #         "code": "CHEM121",
    #         "year": year_data[1],
    #     }
    # )
    # student.courses.append(new_course)
    # log(
    #     f"Updated Courses for {student.name}: ",
    #     [
    #         attrib.serialize(
    #             course, fmt="json", options=attrib.Options(attrib.Option(depth=3))
    #         )
    #         for course in student.courses
    #     ],
    # )

    # # Update student age
    # log(student.name, "is", student.age, "years old")
    # student.age += 3
    # log(student.name, "is now", student.age, "years old")


# @profileit("attrib", max_rows=20, output="rich")
@timeit("attrib")
# @profile
def test(n: int = 1):
    """Run the attrib example multiple times"""
    for _ in range(n):
        example()
