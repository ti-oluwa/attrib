from pathlib import Path
import typing
import sys
from datetime import date, datetime
import zoneinfo
import attrs
import cattrs
import random
from memory_profiler import profile

from utils import timeit, profileit, log
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
        default=None, validator=attrs.validators.max_len(100)
    )
    start_date: date = attrs.field(
        default=None,
    )
    end_date: date = attrs.field(
        default=None,
    )
    created_at: datetime = attrs.field(
        factory=lambda: datetime.now(zoneinfo.ZoneInfo("Africa/Lagos"))
    )


@attrs.define(slots=True)
class Course:
    """Course data class"""

    id: int = attrs.field()
    name: str = attrs.field(validator=attrs.validators.max_len(100))
    code: str = attrs.field(validator=attrs.validators.max_len(20))
    year: AcademicYear = attrs.field()
    created_at: datetime = attrs.field(
        factory=lambda: datetime.now(zoneinfo.ZoneInfo("Africa/Lagos"))
    )


@attrs.define(slots=True, kw_only=True)
class PersonalInfo:
    """Personal information data class"""

    name: str = attrs.field(validator=attrs.validators.max_len(100))
    age: int = attrs.field(validator=attrs.validators.in_(range(0, 31)))
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
        validator=attrs.validators.and_(
            attrs.validators.min_len(1),
            attrs.validators.max_len(15),
        ),
    )
    joined_at: typing.Optional[datetime] = attrs.field(
        default=None,
    )
    created_at: datetime = attrs.field(
        factory=lambda: datetime.now(zoneinfo.ZoneInfo("Africa/Lagos"))
    )


converter = cattrs.Converter()
converter.register_structure_hook(
    datetime, lambda d, _: parse(d) if isinstance(d, str) else d
)
converter.register_structure_hook(
    date, lambda d, _: parse(d).date() if isinstance(d, str) else d
)


def load_data(
    data_list: typing.List[typing.Dict[str, typing.Any]], cls: typing.Type
) -> typing.List:
    return [converter.structure(data, cls) for data in data_list]


def example():
    years = load_data(year_data, AcademicYear)
    courses = load_data(course_data, Course)
    students = load_data(student_data, Student)

    for student in students:
        converter.unstructure_attrs_asdict(student)

    for course in courses:
        converter.unstructure_attrs_asdict(course)

    for year in years:
        converter.unstructure_attrs_asdict(year)


@timeit("attrs + cattrs")
# @profile
def test(n: int):
    for _ in range(n):
        example()
