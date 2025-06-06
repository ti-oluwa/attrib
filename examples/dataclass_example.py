import copy
import enum
import random
import typing
from datetime import datetime, date
import functools
from dataclasses import dataclass, field
from cattrs import Converter
from cattrs.gen import make_dict_unstructure_fn, override
from dateutil.parser import parse

from utils import timeit, log
from mock_data import course_data, student_data, year_data


########################
##### Data Classes #####
########################


class Term(enum.Enum):
    """Academic term enumeration"""

    FIRST = "First"
    SECOND = "Second"
    THIRD = "Third"


@dataclass(frozen=True)
class AcademicYear:
    """Academic year data class"""

    id: int
    name: str
    term: Term = Term.FIRST
    start_date: typing.Optional[date] = field(default=None)
    end_date: typing.Optional[date] = field(default=None)
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        # Validate name length
        if len(self.name) > 100:
            raise ValueError("Name must be at most 100 characters")


@dataclass()
class Course:
    """Course data class"""

    id: typing.Optional[int]
    name: str
    code: str
    year: AcademicYear
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        # Validate name length
        if len(self.name) > 100:
            raise ValueError("Name must be at most 100 characters")

        # Validate code length and format
        if len(self.code) > 20:
            raise ValueError("Code must be at most 20 characters")

        # Convert code to uppercase
        self.code = self.code.strip().upper()


@dataclass(frozen=True)
class PersonalInfo:
    """Personal information data class"""

    name: str
    age: int
    email: typing.Optional[str] = None
    phone: typing.Optional[str] = None

    def __post_init__(self):
        # Validate name length
        if len(self.name) > 100:
            raise ValueError("Name must be at most 100 characters")

        # Validate age range
        if self.age < 0 or self.age > 30:
            raise ValueError("Age must be between 0 and 30")

        # Validate email format if provided
        if self.email is not None and "@" not in self.email:
            raise ValueError("Invalid email format")


@dataclass(frozen=True)
class Student(PersonalInfo):
    """Student data class"""

    id: typing.Optional[int] = None
    year: typing.Optional[AcademicYear] = None
    courses: typing.List[Course] = field(
        default_factory=list, metadata={"alias": "enrolled_in"}
    )
    gpa: typing.Optional[float] = field(
        default_factory=lambda: random.uniform(1.5, 5.0)
    )
    joined_at: typing.Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        super().__post_init__()

        # Validate courses
        if not self.courses:
            raise ValueError("Student must be enrolled in at least one course")
        if len(self.courses) > 15:
            raise ValueError("Student can be enrolled in at most 15 courses")

    @functools.cached_property
    def full_name(self) -> str:
        """Return the full name of the student"""
        return f"{self.name} (ID: {self.id})"


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

DataclassT = typing.TypeVar("DataclassT")


def load_data(
    data_list: typing.List[typing.Dict[str, typing.Any]],
    cls: typing.Type[DataclassT],
) -> typing.List[DataclassT]:
    """
    Load data into dataclasses using cattrs

    :param data_list: List of dictionaries containing data
    :param cls: Dataclass to load data into
    :return: List of the dataclass instances
    """
    return [converter.structure(data, cls) for data in data_list]


def example():
    """Run example usage of the data classes"""
    years = load_data(year_data, AcademicYear)
    courses = load_data(course_data, Course)
    students = load_data(student_data, Student)

    for student in students:
        converter.unstructure(student)

    for course in courses:
        converter.unstructure(course)

    for year in years:
        converter.unstructure(year)


@timeit("dataclasses + cattrs")
def test(n: int = 1) -> None:
    """Run the dataclasses example multiple times"""
    for _ in range(n):
        example()
