import typing
from typing_extensions import Self

P = typing.ParamSpec("P")
R = typing.TypeVar("R")
T = typing.TypeVar("T")

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
JSONDict: typing.TypeAlias = typing.Dict[str, JSONValue]
JSONList: typing.TypeAlias = typing.List["JSONValue"]
JSONNamedDataTuple: typing.TypeAlias = typing.Tuple[typing.Tuple[str, JSONValue], ...]

Context: typing.TypeAlias = typing.Dict[str, typing.Any]

    
@typing.runtime_checkable
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
class TypeAdapter(typing.Generic[T], typing.Protocol):
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

    @typing.overload
    def validate(
        self,
        value: T,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> T: ...

    @typing.overload
    def validate(
        self,
        value: typing.Any,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Any: ...

    def validate(
        self,
        value: typing.Union[T, typing.Any],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Union[T, typing.Any]: ...

    def serialize(
        self,
        value: T,
        fmt: str,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Any: ...

    def deserialize(
        self,
        value: typing.Any,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> T: ...


@typing.runtime_checkable
class Validator(typing.Generic[T], typing.Protocol):
    """
    Validator protocol.

    A callable that takes two main arguments - a value, an optional adapter,
    and any other additional arguments or keyword arguments
    and performs validation on the value.
    """

    def __call__(
        self,
        value: typing.Any,
        adapter: typing.Optional[TypeAdapter[T]] = ...,
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


EMPTY = Empty()
