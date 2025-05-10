# Import necessary packages and modules
from re import S
import typing
from datetime import date, datetime
import zoneinfo
import attrs
import random
from memory_profiler import profile

from utils import timeit, profileit
from mock_data import course_data, student_data, year_data
from dateutil.parser import parse

################
# DATA CLASSES #
################


@attrs.define(slots=True)
class AcademicYear:
    """Academic year data class"""

    id: int = attrs.field()
    name: typing.Optional[str] = attrs.field(
        default=None,
        validator=attrs.validators.optional(attrs.validators.max_len(100)),
        converter=str,
    )
    start_date: date = attrs.field(default=None, converter=lambda x: parse(x).date())
    end_date: date = attrs.field(default=None, converter=lambda x: parse(x).date())
    created_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(slots=True)
class Course:
    """Course data class"""

    id: int = attrs.field()
    name: str = attrs.field(validator=attrs.validators.max_len(100), converter=str)
    code: str = attrs.field(
        validator=attrs.validators.and_(
            attrs.validators.max_len(20), attrs.validators.instance_of(str)
        ),
        converter=str,
    )
    year: AcademicYear = attrs.field()
    created_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(slots=True, kw_only=True)
class PersonalInfo:
    """Personal information data class"""

    name: str = attrs.field(validator=attrs.validators.max_len(100), converter=str)
    age: int = attrs.field(validator=attrs.validators.in_(range(0, 31)), converter=int)
    email: typing.Optional[str] = attrs.field(default=None)
    phone: typing.Optional[str] = attrs.field(default=None)


@attrs.define(slots=True, kw_only=True)
class Student(PersonalInfo):
    """Student data class with multiple fields and a list of enrolled courses"""

    id: int = attrs.field()
    year: typing.Optional[AcademicYear] = attrs.field()
    gpa: float = attrs.field(
        default=attrs.Factory(lambda: random.uniform(1.5, 5.0)),
    )
    courses: typing.List[Course] = attrs.field(
        default=attrs.Factory(list),
        converter=lambda x: [Course(**course) for course in x],
    )
    friend: typing.Optional["Student"] = attrs.field(factory=lambda: dummy_student)
    joined_at: typing.Optional[datetime] = attrs.field(
        default=None,
        converter=lambda x: datetime.now() if x is None else parse(x),
    )
    created_at: datetime = attrs.field(
        factory=lambda: datetime.now().astimezone(zoneinfo.ZoneInfo("Africa/Lagos"))
    )


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


def load_data(
    data_list: typing.List[typing.Dict[str, typing.Any]], datacls: typing.Type
) -> typing.List:
    return [datacls(**data) for data in data_list]


def example():
    years = load_data(year_data, AcademicYear)
    courses = load_data(course_data, Course)
    students = load_data(student_data, Student)

    for student in students:
        attrs.asdict(student, recurse=True)

    for course in courses:
        attrs.asdict(course, recurse=True)

    for year in years:
        attrs.asdict(year, recurse=True)


@timeit("attrs")
# @profile
def test(n: int):
    for _ in range(n):
        example()
