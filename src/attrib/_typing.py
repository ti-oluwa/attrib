import typing
from typing_extensions import Self

P = typing.ParamSpec("P")
R = typing.TypeVar("R")
T = typing.TypeVar("T")
V = typing.TypeVar("V")
Tco = typing.TypeVar("Tco", covariant=True)


class KwArg(typing.Protocol[Tco]):
    """Protocol for dataclass field keyword arguments."""

    def __class_getitem__(cls, item: typing.Any) -> typing.Any: ...


RawData: typing.TypeAlias = typing.Union[
    typing.Mapping[str, typing.Any],
    typing.Mapping[bytes, bytes],
    typing.Sequence[typing.Tuple[str, typing.Any]],
    typing.Sequence[typing.Tuple[bytes, bytes]],
]
IterType = typing.TypeVar("IterType", bound=typing.Iterable[typing.Any])
DataDict: typing.TypeAlias = typing.Dict[str, typing.Any]
NamedDataTuple: typing.TypeAlias = typing.Tuple[typing.Tuple[str, typing.Any], ...]

JSONValue: typing.TypeAlias = typing.Union[
    int, float, str, bool, None, "JSONDict", "JSONList"
]
JSONDict: typing.TypeAlias = typing.Dict[str, "JSONValue"]
JSONList: typing.TypeAlias = typing.List["JSONValue"]
JSONNamedDataTuple: typing.TypeAlias = typing.Tuple[typing.Tuple[str, "JSONValue"], ...]

Context: typing.TypeAlias = typing.Dict[str, typing.Any]


class SupportsRichComparison(typing.Protocol):
    def __lt__(self, other: typing.Any, /) -> bool: ...
    def __le__(self, other: typing.Any, /) -> bool: ...
    def __gt__(self, other: typing.Any, /) -> bool: ...
    def __ge__(self, other: typing.Any, /) -> bool: ...
    def __eq__(self, other: typing.Any, /) -> bool: ...
    def __ne__(self, other: typing.Any, /) -> bool: ...


Serializer: typing.TypeAlias = typing.Callable[..., R]
Deserializer: typing.TypeAlias = typing.Callable[..., R]


@typing.runtime_checkable
class TypeAdapter(typing.Generic[Tco], typing.Protocol):
    """
    Type adapter protocol.

    A type adapter is a pseudo-type. It defines type-like behavior using 3 methods:
    - validate: Validates the value
    - serialize: Serializes the value to a specific format
    - deserialize: Coerces the value to a specific type
    """

    name: typing.Optional[str]

    def build(
        self,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Builds any necessary components or itenaries for the type adapter to function.
        """
        ...

    def validate(
        self,
        value: typing.Union[Tco, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None: ...

    def serialize(
        self,
        value: typing.Union[Tco, typing.Any],
        fmt: str,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Optional[typing.Any]: ...

    def deserialize(
        self,
        value: typing.Union[Tco, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Optional[Tco]: ...


@typing.runtime_checkable
class Validator(typing.Generic[Tco], typing.Protocol):
    """
    Validator protocol.

    A callable that takes two main arguments - a value, an optional adapter,
    and any other additional arguments or keyword arguments
    and performs validation on the value.
    """

    def __call__(
        self,
        value: typing.Any,
        adapter: typing.Optional[
            typing.Union[TypeAdapter[Tco], TypeAdapter[typing.Any]]
        ],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        ...

        :param value: The value to validate
        :param adapter: The type adapter being used
        """
        ...


@typing.final
class Empty:
    """Type representing missing/empty values."""

    _instance: typing.Optional[Self] = None

    def __new__(cls) -> Self:
        if cls._instance is not None:
            raise TypeError("Singleton `Empty` can no longer be created")
        instance = super().__new__(cls)
        cls._instance = instance
        return instance

    def __bool__(self):
        return False

    def __hash__(self) -> int:
        return id(self)

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(
        self, memo: typing.Optional[typing.Dict[int, typing.Any]] = None
    ) -> Self:
        return self


EMPTY = Empty()
