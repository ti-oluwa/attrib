import typing
import pydantic

import attrib
from utils import timeit, log


#######################
#### Type Adapters ####
#######################

attrib_adapter = attrib.TypeAdapter(
    typing.Tuple[
        typing.List[typing.Optional["PersonTuple"]],
        typing.Dict[str, typing.List[int]],
        typing.Optional[str],
    ],
    defer_build=True,
)

pydantic_adapter = pydantic.TypeAdapter(
    typing.Tuple[
        typing.List[typing.Optional["PersonTuple"]],
        typing.Dict[str, typing.List[int]],
        typing.Optional[str],
    ],
    config=pydantic.ConfigDict(
        defer_build=True,
        arbitrary_types_allowed=True,
    ),
)


class Person(attrib.Dataclass, slots=True, frozen=True):
    """Person data class"""

    name = attrib.String(max_length=100)
    age = attrib.Integer(min_value=0, max_value=100)
    friends = attrib.List(
        child=attrib.Nested("Person", lazy=False),
        default=attrib.Factory(list),
        allow_null=True,
    )


class PersonTuple(typing.NamedTuple):
    """TypedDict for Person"""

    name: str
    age: int
    friends: typing.List[typing.Optional["PersonTuple"]]


raw_data = (
    (
        {
            "name": "One",
            "age": "18",
            "friends": [
                {"name": "Two", "age": 20, "friends": []},
                {"name": "Three", "age": "30", "friends": []},
                {
                    "name": "Four",
                    "age": 40,
                    "friends": (
                        {"name": "Five", "age": 50, "friends": [None]},
                        {"name": "Six", "age": 60, "friends": [None]},
                    ),
                },
            ],
        },
        {"name": "Seven", "age": "70", "friends": []},
        None,
    ),
    {"scores": [10, 20, 30]},
    None,
)


def main():
    with timeit("build_pydantic_adapter"):
        pydantic_adapter.rebuild()

    with timeit("build_adapter"):
        attrib_adapter.build(depth=10, globalns=globals())

    with timeit("adapt_and_serialize_pydantic"):
        adapted_pydantic = pydantic_adapter.validate_python(raw_data)
        log(adapted_pydantic)

    with timeit("adapt_and_serialize"):
        adapted = attrib_adapter.adapt(raw_data)
        log(attrib_adapter.serialize(adapted, fmt="python"))


if __name__ == "__main__":
    main()
