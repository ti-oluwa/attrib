import typing


P = typing.ParamSpec("P")
R = typing.TypeVar("R")
T = typing.TypeVar("T")


RawData: typing.TypeAlias = typing.Union[
    typing.Mapping[bytes, bytes],
    typing.Sequence[typing.Tuple[bytes, bytes]],
]

IterType = typing.TypeVar("IterType", bound=typing.Iterable[typing.Any])


@typing.runtime_checkable
class SupportsRichComparison(typing.Protocol):
    def __lt__(self, other: typing.Any, /) -> bool: ...
    def __le__(self, other: typing.Any, /) -> bool: ...
    def __gt__(self, other: typing.Any, /) -> bool: ...
    def __ge__(self, other: typing.Any, /) -> bool: ...
    def __eq__(self, other: typing.Any, /) -> bool: ...
    def __ne__(self, other: typing.Any, /) -> bool: ...


Serializer: typing.TypeAlias = typing.Callable[..., typing.Any]
Deserializer: typing.TypeAlias = typing.Callable[..., typing.Any]


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

    def validate(
        self,
        value: typing.Any,
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
class _empty:
    """Class to represent missing/empty values."""

    def __bool__(self):
        return False

    def __hash__(self) -> int:
        return id(self)


EMPTY = _empty()
