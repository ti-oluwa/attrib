import typing
import pydantic
import collections

import attrib
from utils import timeit, log


#######################
#### Type Adapters ####
#######################

attrib_adapter = attrib.TypeAdapter(
    typing.Tuple[
        typing.List[typing.Optional["PersonTuple"]],
        typing.Dict[str, typing.List[typing.Union[int, str]]],
        typing.Optional[str],
    ],
    defer_build=True,
)

pydantic_adapter = pydantic.TypeAdapter(
    typing.Tuple[
        typing.List[typing.Optional["PersonTuple"]],
        typing.Dict[str, typing.List[typing.Union[int, str]]],
        typing.Optional[str],
    ],
    config=pydantic.ConfigDict(
        defer_build=True,
        arbitrary_types_allowed=True,
    ),
)


class PersonTuple(typing.NamedTuple):
    """TypedDict for Person"""

    name: str
    age: int
    friends: typing.List[typing.Optional["PersonTuple"]]


class Person(attrib.Dataclass, slots=True, frozen=True):
    """Person data class"""

    name = attrib.String(max_length=100)
    age = attrib.Integer(min_value=0, max_value=100)
    friends = attrib.Iterable[collections.deque["Person"], "Person"](
        collections.deque,
        child=attrib.Nested(
            "Person",
            lazy=True,
        ),
        default=attrib.Factory(list),
        allow_null=True,
    )


raw_data = (
    (
        {
            "name": "One",
            "age": "18",
            "friends": [
                {"name": "Two", "age": "20", "friends": set()},
                {"name": "Three", "age": "30", "friends": []},
                {
                    "name": "Four",
                    "age": 40,
                    "friends": (
                        {"name": "Five", "age": "30", "friends": [None]},
                        {"name": "Six", "age": "60", "friends": [None]},
                    ),
                },
            ],
        },
        {"name": "Seven", "age": "70", "friends": []},
        None,
    ),
    {"scores": [10, "20", 30]},
    None,
)


def main():
    with timeit("build_pydantic_adapter"):
        pydantic_adapter.rebuild()

    with timeit("build_adapter"):
        attrib_adapter.build(depth=10, globalns=globals())

    with timeit("adapt_and_serialize_pydantic"):
        adapted_pydantic = pydantic_adapter.validate_python(raw_data)
        serialized_pydantic = pydantic_adapter.dump_python(
            adapted_pydantic, mode="python"
        )
        log(adapted_pydantic)
        log(serialized_pydantic)

    with timeit("adapt_and_serialize"):
        adapted_attrib = attrib_adapter.adapt(raw_data)
        serialized_attrib = attrib_adapter.serialize(adapted_attrib, fmt="python")
        log(adapted_attrib)
        log(serialized_attrib)


if __name__ == "__main__":
    main()
