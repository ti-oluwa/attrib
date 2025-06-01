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
        typing.List[typing.Optional["Person"]],
        typing.Dict[str, typing.List[typing.Union[int, str]]],
        typing.Optional[str],
    ],
    defer_build=True,
)

# pydantic_adapter = pydantic.TypeAdapter(
#     typing.Tuple[
#         typing.List[typing.Optional["PersonTuple"]],
#         typing.Dict[str, typing.List[int]],
#         typing.Optional[str],
#     ],
#     config=pydantic.ConfigDict(
#         defer_build=True,
#         arbitrary_types_allowed=True,
#     ),
# )


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
                {"name": "Two", "age": "20", "friends": {}},
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
    # with timeit("build_pydantic_adapter"):
    #     pydantic_adapter.rebuild()

    with timeit("build_adapter"):
        attrib_adapter.build(depth=None, globalns=globals())

    # with timeit("adapt_and_serialize_pydantic"):
    #     adapted_pydantic = pydantic_adapter.validate_python(raw_data)
    #     log(adapted_pydantic)

    with timeit("adapt_and_serialize"):
        adapted = attrib_adapter.adapt(raw_data, fail_fast=True)
        log(attrib_adapter.serialize(
            adapted,
            fmt="python",
            astuple=False,
            fail_fast=True,
            options=attrib.Options(attrib.Option(Person, depth=1)),
        ))


if __name__ == "__main__":
    main()
