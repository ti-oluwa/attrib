import copy
import typing
import enum
from datetime import date, datetime
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo  # type: ignore[import]
import attrs
from cattrs import Converter
from cattrs.gen import make_dict_unstructure_fn, override
import random

from utils import timeit, profileit, log
from mock_data import course_data, student_data, year_data
from dateutil.parser import parse


################
# DATA CLASSES #
################


class Term(enum.Enum):
    """Academic term enumeration"""

    FIRST = "First"
    SECOND = "Second"
    THIRD = "Third"


@attrs.define()
class AcademicYear:
    """Academic year data class"""

    id: int = attrs.field()
    name: typing.Optional[str] = attrs.field(
        default=None, validator=attrs.validators.max_len(100)
    )
    term: Term = attrs.field(default=Term.FIRST)
    start_date: typing.Optional[date] = attrs.field(
        default=None,
    )
    end_date: typing.Optional[date] = attrs.field(
        default=None,
    )
    created_at: datetime = attrs.field(
        factory=lambda: datetime.now(zoneinfo.ZoneInfo("Africa/Lagos"))
    )


@attrs.define()
class Course:
    """Course data class"""

    id: int = attrs.field()
    name: str = attrs.field(validator=attrs.validators.max_len(100))
    code: str = attrs.field(validator=attrs.validators.max_len(20))
    year: AcademicYear = attrs.field()
    created_at: datetime = attrs.field(
        factory=lambda: datetime.now(zoneinfo.ZoneInfo("Africa/Lagos"))
    )


@attrs.define(kw_only=True)
class PersonalInfo:
    """Personal information data class"""

    name: str = attrs.field(validator=attrs.validators.max_len(100))
    age: int = attrs.field(validator=attrs.validators.in_(range(0, 31)))
    email: typing.Optional[str] = attrs.field(default=None)
    phone: typing.Optional[str] = attrs.field(default=None)


@attrs.define(kw_only=True)
class Student(PersonalInfo):
    """Student data class"""

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


def configure_converters() -> Converter:
    """Configure cattrs converter for custom serialization/deserialization"""
    converter = Converter()

    converter.register_unstructure_hook(Term, lambda e: e.value)
    converter.register_unstructure_hook(
        datetime, lambda dt: dt.isoformat() if dt else None
    )
    converter.register_unstructure_hook(date, lambda d: d.isoformat() if d else None)

    # For StudentClass, rename 'courses' to 'enrolled_in' during serialization
    student_unstruct_hook = make_dict_unstructure_fn(
        Student,
        converter,
        _cattrs_omit_if_default=False,
        courses=override(rename="enrolled_in"),
    )
    converter.register_unstructure_hook(Student, student_unstruct_hook)

    def structure_datetime(val, _) -> datetime:
        if isinstance(val, datetime):
            return val
        return parse(val)

    def structure_date(val, _) -> date:
        if isinstance(val, datetime):
            return val.date()
        return parse(val).date()

    converter.register_structure_hook(datetime, structure_datetime)
    converter.register_structure_hook(date, structure_date)
    return converter


converter = configure_converters()

AttrsclassT = typing.TypeVar("AttrsclassT")


def load_data(
    data_list: typing.List[typing.Dict[str, typing.Any]], cls: typing.Type[AttrsclassT]
) -> typing.List[AttrsclassT]:
    return [converter.structure(data, cls) for data in data_list]


def example():
    years = load_data(year_data, AcademicYear)
    courses = load_data(course_data, Course)
    students = load_data(student_data, Student)

    for student in students:
        converter.unstructure(student)

    for course in courses:
        converter.unstructure(course)

    for year in years:
        converter.unstructure(year)


@timeit("attrs + cattrs")
def test(n: int) -> None:
    for _ in range(n):
        example()
