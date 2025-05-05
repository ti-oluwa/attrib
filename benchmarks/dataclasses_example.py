# Import necessary packages and modules
import pickle
import time
import typing
from datetime import datetime

import attrib
from utils import timeit, profileit
from mock_data import course_data, student_data, year_data


_DataClass_co = typing.TypeVar("_DataClass_co", bound=attrib.DataClass, covariant=True)


################
# DATA CLASSES #
################
class AcademicYear(
    attrib.DataClass,
    eq=True,
    hash=True,
    slots=True,
):
    """Academic year data class"""

    id = attrib.Field(int, required=True)
    name = attrib.StringField(max_length=100)
    start_date = attrib.DateField(input_formats=["%d-%m-%Y", "%d/%m/%Y"])
    end_date = attrib.DateField(input_formats=["%d-%m-%Y", "%d/%m/%Y"])
    created_at = attrib.DateTimeField(
        default=attrib.Factory(datetime.now), tz="Africa/Lagos"
    )


class Course(
    attrib.DataClass,
    eq=True,
    hash=True,
    slots=True,
):
    """Course data class"""

    id = attrib.Field(int, required=True, allow_null=True)
    name = attrib.StringField(max_length=100)
    code = attrib.StringField(max_length=20)
    year = attrib.NestedField(AcademicYear, lazy=False)
    created_at = attrib.DateTimeField(default=attrib.Factory(datetime.now))


class PersonalInfo(
    attrib.DataClass,
    eq=True,
    hash=True,
    slots=True,
):
    """Personal information data class"""

    name = attrib.StringField(max_length=100)
    age = attrib.IntegerField(min_value=0, max_value=100)
    email = attrib.EmailField(allow_null=True, default=None)
    phone = attrib.PhoneNumberField(allow_null=True, default=None)


class Student(
    PersonalInfo,
    eq=True,
    hash=True,
    slots=True,
):
    """Student data class with multiple fields and a list of enrolled courses"""

    id = attrib.IntegerField(required=True)
    year = attrib.NestedField(AcademicYear, lazy=False)
    courses = attrib.ListField(
        child=attrib.NestedField(Course, lazy=False),
    )
    joined_at = attrib.DateTimeField(allow_null=True, tz="Africa/Lagos")
    created_at = attrib.DateTimeField(
        default=attrib.Factory(datetime.now), tz="Africa/Lagos"
    )


def load_data(
    data_list: typing.List[typing.Dict[str, typing.Any]],
    cls: typing.Type[_DataClass_co],
) -> typing.List[_DataClass_co]:
    """
    Load data into data classes

    :param data_list: List of dictionaries containing data
    :param cls: Data class to load data into
    :return: List of the data class instances
    """
    # raise
    return [attrib.deserialize(cls, data) for data in data_list]


def example():
    """Run example usage of the data classes"""
    years = load_data(year_data, AcademicYear)
    courses = load_data(course_data, Course)
    students = load_data(student_data, Student)

    for student in students:
        attrib.serialize(student, fmt="json", depth=2)

    for course in courses:
        attrib.serialize(course, fmt="json", depth=2)

    for year in years:
        attrib.serialize(year, fmt="json", depth=2)

    # dump = pickle.dumps(students)
    # loaded_students = pickle.loads(dump)
    # log(
    #     "Loaded Students: ",
    #     [attrib.serialize(student, fmt="python") for student in loaded_students],
    # )

    # # Access and print a student's information
    # student = students[0]  # e.g., first student in the list
    # log(attrib.serialize(student, depth=2))  # View student details in dictionary format
    # Modify the student's academic year
    # student.year = years[1]  # Update academic year to next year
    # log(f"Updated Academic Year for {student.name}: ", attrib.serialize(student))

    # # Serialize the student's data to JSON format
    # student_json = attrib.serialize(student, fmt="json", depth=2)
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
    # log(f"Updated Academic Year for {student.name}: ", attrib.serialize(student, depth=2))

    # # Adding a new course to a student and displaying
    # new_course = Course(
    #     {"id": 4, "name": "Organic Chemistry", "code": "CHEM121", "year": year_data[1]}
    # )
    # student.courses.append(new_course)
    # log(
    #     f"Updated Courses for {student.name}: ",
    #     [attrib.serialize(course, fmt="json", depth=2) for course in student.courses],
    # )

    # # Update student age
    # log(student.name, "is", student.age, "years old")
    # student.age += 3
    # log(student.name, "is now", student.age, "years old")


@timeit("dataclasses_test")
def test(n: int = 1):
    """Run the dataclasses example multiple times"""
    for _ in range(n):
        example()
