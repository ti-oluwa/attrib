import numbers
import typing

from typing_extensions import ParamSpec, Self, TypeAlias

P = ParamSpec("P")
R = typing.TypeVar("R")
T = typing.TypeVar("T")
V = typing.TypeVar("V")
Tco = typing.TypeVar("Tco", covariant=True)
T_con = typing.TypeVar("T_con", contravariant=True)


class KwArg(typing.Protocol[Tco]):
    """Protocol for dataclass field keyword arguments."""

    def __class_getitem__(cls, item: typing.Any) -> typing.Any: ...


RawData: TypeAlias = typing.Union[
    typing.Mapping[str, typing.Any],
    typing.Mapping[bytes, bytes],
    typing.Sequence[typing.Tuple[str, typing.Any]],
    typing.Sequence[typing.Tuple[bytes, bytes]],
]
IterT = typing.TypeVar("IterT", bound=typing.Iterable[typing.Any])
IterTco = typing.TypeVar("IterTco", bound=typing.Iterable[typing.Any], covariant=True)
DataDict: TypeAlias = typing.Dict[str, typing.Any]
NamedDataTuple: TypeAlias = typing.Tuple[typing.Tuple[str, typing.Any], ...]

JSONValue: TypeAlias = typing.Union[int, float, str, bool, None, "JSONDict", "JSONList"]
JSONDict: TypeAlias = typing.Dict[str, "JSONValue"]
JSONList: TypeAlias = typing.List["JSONValue"]
JSONNamedDataTuple: TypeAlias = typing.Tuple[typing.Tuple[str, "JSONValue"], ...]

Context: TypeAlias = typing.MutableMapping[str, typing.Any]
NoneType = type(None)

RealNumberT = typing.TypeVar("RealNumberT", bound=numbers.Real)


class SupportsRichComparison(typing.Protocol):
    def __lt__(self, other: typing.Any, /) -> bool: ...
    def __le__(self, other: typing.Any, /) -> bool: ...
    # def __gt__(self, other: typing.Any, /) -> bool: ...
    # def __ge__(self, other: typing.Any, /) -> bool: ...
    def __eq__(self, other: typing.Any, /) -> bool: ...
    def __ne__(self, other: typing.Any, /) -> bool: ...


Serializer: TypeAlias = typing.Callable[..., R]
"""A serializer takes in a value, an optional adapter, and any other args and kwargs, and returns a serialized representation of the value."""
Deserializer: TypeAlias = typing.Callable[..., R]
"""A deserializer takes in a value, an optional adapter, and any other args and kwargs, and returns a deserialized representation of the value."""
SerializerMap: TypeAlias = typing.Mapping[str, Serializer[typing.Any]]
"""A mapping of format names to serializer callables."""


@typing.runtime_checkable
class TypeAdapter(typing.Generic[Tco], typing.Protocol):
    """
    Type adapter protocol.

    A type adapter is a pseudo-type. It defines type-like behavior using 5 methods:

    - build: Builds any necessary components for the type adapter to function
    - check_type: Checks if the value is of the adapted type
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

    def check_type(self, value: typing.Any) -> bool:
        """
        Check if the value is of the adapted type.

        :param value: The value to check
        :return: True if the value is of the adapted type, False otherwise
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
class Validator(typing.Generic[T_con], typing.Protocol):
    """
    Validator protocol.

    A callable that takes two main arguments - a value, an optional adapter,
    and any other additional arguments or keyword arguments
    and performs validation on the value.
    """

    def __call__(
        self,
        value: typing.Any,
        adapter: typing.Optional[TypeAdapter[T_con]],
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


@typing.final
class AnyType:
    """Type representing any type."""

    def __init_subclass__(cls):
        raise TypeError("AnyType cannot be subclassed.")

    def __new__(cls):
        raise TypeError("AnyType cannot be instantiated.")

    def __instancecheck__(self, instance: typing.Any) -> bool:
        return True

    def __subclasscheck__(self, subclass: typing.Type[typing.Any]) -> bool:
        return True
