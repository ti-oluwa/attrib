import enum
import random
import typing
from datetime import datetime
import tracemalloc
import gc
import attrs
from memory_profiler import profile

import attrib
from attrib.descriptors.phonenumbers import PhoneNumber
from utils import timeit, profileit, log
from mock_data import course_data, student_data, year_data
from attrs_example import Student as AttrsStudent


_Dataclass_co = typing.TypeVar("_Dataclass_co", bound=attrib.Dataclass, covariant=True)


adapter = attrib.TypeAdapter(
    typing.Tuple[
        typing.List[typing.Optional["Person"]],
        typing.Dict[str, typing.List[int]],
        typing.Optional[str],
    ],
    defer=True,
)


class Person(attrib.Dataclass, slots=True, frozen=True):
    """Person data class"""

    name = attrib.String(max_length=100)
    age = attrib.Integer(min_value=0, max_value=30)
    friends = attrib.List(
        child=attrib.Nested("Person", lazy=False),
        default=attrib.Factory(list),
        allow_null=True,
    )


with timeit("build_adapter"):
    adapter.build(globalns=globals(), localns=locals())

with timeit("adapt_and_serialize"):
    adapted = adapter(
        ([{"name": "One", "age": 18}, None], {"scores": [10, 20, 30]}, None),
    )
    log(adapted)
    log(
        adapter.serialize(
            adapted,
            options={
                attrib.Option(Person, depth=1, strict=True),
            },
            astuple=True,
        )
    )


class Term(enum.Enum):
    """Academic term enumeration"""

    FIRST = "First"
    SECOND = "Second"
    THIRD = "Third"


class AcademicYear(attrib.Dataclass, slots=False):
    """Academic year data class"""

    id = attrib.Field(int, required=True)
    name = attrib.String(max_length=100)
    term = attrib.Choice(Term, default=Term.FIRST)
    start_date = attrib.Date(input_formats=["%d-%m-%Y", "%d/%m/%Y"])
    end_date = attrib.Date(input_formats=["%d-%m-%Y", "%d/%m/%Y"])
    created_at = attrib.DateTime(default=datetime.now, tz="Africa/Lagos")


class Course(attrib.Dataclass, slots=False):
    """Course data class"""

    id = attrib.Field(int, required=True, allow_null=True)
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
        slots=False,
        frozen=True,
        pickleable=True,
    )


class Student(PersonalInfo, slots=True, hash=True):
    """Student data class with multiple fields and a list of enrolled courses"""

    id = attrib.Integer(required=True)
    year = attrib.Nested(AcademicYear, lazy=False, allow_null=True)
    courses = attrib.List(
        child=attrib.Nested(Course, lazy=False),
        validator=attrib.validators.min_length(1),
    )
    gpa = attrib.Float(
        allow_null=True, default=attrib.Factory(random.uniform, a=1.5, b=5.0)
    )
    friend: attrib.Field["AttrsStudent"] = attrib.Field(
        AttrsStudent,
        lazy=False,
        default=lambda: attrib.serialize(dummy_student, fmt="python"),
        allow_null=True,
        serializers={"json": lambda x, *_: attrib.make_jsonable(x)},
        deserializer=lambda x, _: AttrsStudent(**x),
    )
    joined_at = attrib.DateTime(allow_null=True, tz="Africa/Lagos")
    created_at = attrib.DateTime(default=datetime.now, tz="Africa/Lagos")


dummy_student = Student(
    id=0,
    name="",
    age=0,
    email=None,
    phone=None,
    year=year_data[0],
    courses=course_data,
    joined_at=None,
    friend=None,
)

dummy_student.age


def load_data(
    data_list: typing.List[typing.Dict[str, typing.Any]],
    cls: typing.Type[_Dataclass_co],
) -> typing.List[_Dataclass_co]:
    """
    Load data into data classes

    :param data_list: List of dictionaries containing data
    :param cls: Data class to load data into
    :return: List of the data class instances
    """
    return [attrib.deserialize(cls, data) for data in data_list]


def example():
    """Run example usage of the data classes"""
    years = load_data(year_data, AcademicYear)
    courses = load_data(course_data, Course)
    students = load_data(student_data, Student)

    for student in students:
        attrib.serialize(
            student,
            fmt="json",
            # options=[
            #     attrib.Option(Course, depth=0, strict=True),
            #     attrib.Option(depth=1),
            # ],
        )

    for course in courses:
        attrib.serialize(
            course,
            fmt="python",
        )

    for year in years:
        attrib.serialize(
            year,
            fmt="python",
        )

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


# @profileit("attrib", max_rows=20, output="rich")
@timeit("attrib")
# @profile
def test(n: int = 1):
    """Run the attrib example multiple times"""
    # tracemalloc.start()
    for _ in range(n):
        # snapshot1 = tracemalloc.take_snapshot()
        example()
    #     snapshot2 = tracemalloc.take_snapshot()
    #     stats = snapshot2.compare_to(snapshot1, 'lineno')
    #     for stat in stats[:10]:
    #         print(stat)

    # print(tracemalloc.get_traced_memory())
    # tracemalloc.stop()
