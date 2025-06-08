import enum
import random
import typing
from datetime import datetime
from dateutil.parser import parse
import pydantic
from pydantic import Field, field_validator, ConfigDict

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


class AcademicYear(pydantic.BaseModel):
    """Academic year data class"""

    id: int
    name: str = Field(max_length=100)
    term: Term = Term.FIRST
    start_date: datetime
    end_date: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now())

    model_config = ConfigDict(extra="ignore", strict=False)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return parse(v).date()
            except Exception:
                pass
        return v

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        if not v:
            return v
        return str(v).strip()


class Course(pydantic.BaseModel):
    """Course data class"""

    id: typing.Optional[int] = None
    name: str = Field(max_length=100)
    code: str = Field(max_length=20)
    year: AcademicYear
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(extra="ignore", strict=False)

    @field_validator("code", mode="before")
    @classmethod
    def validate_code(cls, v):
        if not v:
            return v
        return str(v).strip().upper()


class PersonalInfo(pydantic.BaseModel):
    """Personal information data class"""

    name: str = Field(max_length=100)
    age: int = Field(ge=0, le=30)
    email: typing.Optional[str] = None
    phone: typing.Optional[str] = None

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        strict=False,
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if v is None:
            return v
        if "@" not in v:
            raise ValueError("Invalid email address")
        return v


class Student(PersonalInfo):
    """Student data class"""

    id: int
    year: typing.Optional[AcademicYear] = None
    courses: typing.List[Course] = Field(
        min_length=1,
        max_length=15,
        fail_fast=True,
        serialization_alias="enrolled_in",
    )
    gpa: typing.Optional[float] = Field(
        default_factory=lambda: random.uniform(1.5, 5.0)
    )
    joined_at: typing.Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        strict=False,
    )

    @field_validator("joined_at", "created_at", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return parse(v).date()
            except Exception:
                pass
        return v


ModelTco = typing.TypeVar("ModelTco", bound=pydantic.BaseModel, covariant=True)


def load_data(
    data_list: typing.List[typing.Dict[str, typing.Any]],
    cls: typing.Type[ModelTco],
) -> typing.List[ModelTco]:
    """
    Load data into pydantic models

    :param data_list: List of dictionaries containing data
    :param cls: Pydantic model class to load data into
    :return: List of the model instances
    """
    return [cls.model_validate(data, by_name=True) for data in data_list]


def example() -> None:
    """Run example usage of the data classes"""
    years = load_data(year_data, AcademicYear)
    courses = load_data(course_data, Course)
    students = load_data(student_data, Student)

    for student in students:
        student.model_dump(mode="python", by_alias=True)

    for course in courses:
        course.model_dump(mode="python")

    for year in years:
        year.model_dump(mode="python")


@timeit("pydantic")
def test(n: int = 1) -> None:
    """Run the pydantic example multiple times"""
    for _ in range(n):
        example()
