import functools
import inspect
import typing
from collections.abc import (
    Iterable,
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
    Set,
)

from attrib._utils import coalesce, is_generic_type
from attrib.exceptions import (
    DeserializationError,
    InvalidTypeError,
    SerializationError,
    ValidationError,
)
from attrib.types import (
    Deserializer,
    JSONValue,
    NoneType,
    Serializer,
    SerializerMap,
    T,
    Validator,
)
from attrib.validators import (
    Or,
    is_,
    iterable,
    mapping,
    member_of,
    optional,
)


@functools.lru_cache(maxsize=512)
def get_type_info(
    target: typing.Any,
) -> typing.Tuple[typing.Any, typing.Tuple[typing.Any, ...]]:
    """Cache expensive typing.get_origin() and typing.get_args() calls."""
    return (typing.get_origin(target), typing.get_args(target))


@functools.lru_cache(maxsize=256)
def is_mapping_origin(origin: typing.Any) -> bool:
    """Cache expensive issubclass checks for Mapping types."""
    return inspect.isclass(origin) and issubclass(origin, Mapping)


@functools.lru_cache(maxsize=256)
def is_sequence_or_set_origin(origin: typing.Any) -> bool:
    """Cache expensive issubclass checks for Sequence/Set types."""
    return inspect.isclass(origin) and issubclass(origin, (Sequence, Set))


@functools.lru_cache(maxsize=128)
def build_generic_type_deserializer(
    target: typing.Union[typing.Type[T], T],
    depth: typing.Optional[int] = None,
) -> Deserializer[typing.Union[T, typing.Any]]:
    """
    Build a deserializer for a generic type.

    :param target: The target generic type to build deserializer for
    :return: A deserializer function for the target type
    """
    from attrib.adapters._concrete import build_concrete_type_deserializer

    next_depth = None
    if depth is not None:
        if depth <= 0:
            return lambda value, *args, **kwargs: value
        else:
            next_depth = depth - 1

    origin, type_args = get_type_info(target)
    if not (origin or type_args):
        raise TypeError(f"Cannot build deserializer for non-generic type {target!r}")

    if origin is None:
        if not type_args:
            raise TypeError(
                f"Cannot build deserializer for non-generic type {target!r}"
            )
        # If the origin is None, we need to use the first argument as the origin
        # and the rest as arguments.
        return coalesce(
            *(
                build_generic_type_deserializer(arg, depth=next_depth)
                if is_generic_type(arg)
                else build_concrete_type_deserializer(arg, depth=next_depth)
                for arg in type_args
            ),
            target=(
                TypeError,
                ValueError,
                DeserializationError,
            ),
            detailed_exc_type=DeserializationError,
        )
    elif origin and not type_args:
        return (
            build_generic_type_deserializer(origin, depth=next_depth)
            if is_generic_type(origin)
            else build_concrete_type_deserializer(origin, depth=next_depth)
        )

    if not inspect.isclass(origin):
        if origin is typing.Literal:
            # If the origin is Literal, the deserializer should just return the value as is
            return lambda value, *args, **kwargs: value

        if origin is typing.Union:
            # Fast path: Optional[X] is extremely common (Union with exactly 2 types, one being None)
            if len(type_args) == 2 and NoneType in type_args:
                # Get the non-None type
                inner_type = type_args[0] if type_args[1] is NoneType else type_args[1]

                # Build deserializer once
                inner_deserializer = (
                    build_generic_type_deserializer(inner_type, depth=next_depth)
                    if is_generic_type(inner_type)
                    else build_concrete_type_deserializer(inner_type, depth=next_depth)
                )

                # Return optimized optional deserializer
                def optional_deserializer(
                    value: typing.Any, *args: typing.Any, **kwargs: typing.Any
                ) -> typing.Optional[typing.Any]:
                    return (
                        None
                        if value is None
                        else inner_deserializer(value, *args, **kwargs)
                    )

                return optional_deserializer

            # General Union handling (multiple types including None, or multiple non-None types)
            if NoneType in type_args:
                # We have an optional type with multiple non-None types
                any_deserializer = coalesce(
                    *(
                        build_generic_type_deserializer(arg, depth=next_depth)
                        if is_generic_type(arg)
                        else build_concrete_type_deserializer(arg, depth=next_depth)
                        for arg in type_args
                        if arg is not NoneType
                    ),
                    target=(
                        TypeError,
                        ValueError,
                        DeserializationError,
                    ),
                    detailed_exc_type=DeserializationError,
                )

                def multi_optional_deserializer(
                    value: typing.Any, *args: typing.Any, **kwargs: typing.Any
                ) -> typing.Optional[typing.Any]:
                    if value is None:
                        return None
                    return any_deserializer(value, *args, **kwargs)

                return multi_optional_deserializer

        args_deserializers = tuple(
            build_generic_type_deserializer(arg, depth=next_depth)
            if is_generic_type(arg)
            else build_concrete_type_deserializer(arg, depth=next_depth)
            for arg in type_args
        )
        return coalesce(
            *args_deserializers,
            target=(
                TypeError,
                ValueError,
                DeserializationError,
            ),
            detailed_exc_type=DeserializationError,
        )

    args_deserializers = tuple(
        build_generic_type_deserializer(arg, depth=next_depth)
        if is_generic_type(arg)
        else build_concrete_type_deserializer(arg, depth=next_depth)
        for arg in type_args
    )
    if is_mapping_origin(origin):
        assert len(args_deserializers) == 2, (
            f"Deserializer count mismatch. Expected 2 but got {len(args_deserializers)}"
        )

        key_deserializer, value_deserializer = args_deserializers
        if inspect.isabstract(origin) or not issubclass(origin, MutableMapping):
            origin = dict

        def mapping_deserializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Mapping[typing.Any, typing.Any]:
            if not isinstance(value, (Mapping, Iterable)):
                raise InvalidTypeError(
                    "Expected a Mapping or Iterable.",
                    input_type=type(value),
                    expected_type=origin,
                )

            new_mapping = origin.__new__(origin)  # type: ignore[assignment]
            if isinstance(value, Mapping):
                items = value.items()
            else:
                items = iter(value)

            for key, item in items:
                try:
                    new_mapping[key_deserializer(key, *args, **kwargs)] = (
                        value_deserializer(item, *args, **kwargs)
                    )
                except (TypeError, ValueError, DeserializationError) as exc:
                    raise DeserializationError.from_exc(
                        exc,
                        input_type=type(value),
                        expected_type=origin,
                        location=[key],
                    ) from exc
            return new_mapping

        return mapping_deserializer

    if is_sequence_or_set_origin(origin):
        args_count = len(type_args)
        assert args_count == len(args_deserializers), (
            f"Deserializer count mismatch. Expected {args_count} but got {len(args_deserializers)}"
        )

        if issubclass(origin, tuple) and args_count > 1:

            def tuple_deserializer(
                value: typing.Any,
                *args: typing.Any,
                **kwargs: typing.Any,
            ) -> typing.Tuple[typing.Any, ...]:
                if not isinstance(value, Iterable) or len(value) != args_count:  # type: ignore
                    raise InvalidTypeError(
                        f"Expected an Iterable with {args_count} items.",
                        input_type=type(value),
                        expected_type=origin,
                    )

                new_tuple = []
                for index, item in enumerate(value):
                    try:
                        new_tuple.append(
                            args_deserializers[index](item, *args, **kwargs)
                        )
                    except (TypeError, ValueError, DeserializationError) as exc:
                        raise DeserializationError.from_exc(
                            exc,
                            input_type=type(value),
                            expected_type=type_args[index],
                            location=[index],
                        ) from exc

                return origin(new_tuple)  # type: ignore

            return tuple_deserializer

        if inspect.isabstract(origin) or not issubclass(origin, MutableSequence):
            origin = list

        def iterable_deserializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Iterable[typing.Any]:
            if not isinstance(value, Iterable):
                raise InvalidTypeError(
                    "Expected an Iterable.",
                    input_type=type(value),
                    expected_type=origin,
                )

            new_iterable = []
            for item_index, item in enumerate(value):
                error = None
                for args_index, deserializer in enumerate(args_deserializers):
                    try:
                        new_iterable.append(deserializer(item, *args, **kwargs))
                        break
                    except (TypeError, ValueError, DeserializationError) as exc:
                        if error is None:
                            error = DeserializationError.from_exc(
                                exc,
                                message="Failed to deserialize item at index",
                                input_type=type(value),
                                expected_type=type_args[args_index],
                                location=[item_index],
                            )
                        else:
                            error.add(
                                exc,
                                input_type=type(value),
                                expected_type=type_args[args_index],
                                location=[item_index],
                            )
                else:
                    if error is not None:
                        raise error

            return origin(new_iterable)  # type: ignore

        return iterable_deserializer

    raise TypeError(
        f"Cannot build deserializer for generic type {target!r} with origin {origin!r} and arguments {type_args!r}"
    )


@functools.lru_cache(maxsize=128)
def build_generic_type_validator(
    target: typing.Union[typing.Type[T], T],
    /,
    depth: typing.Optional[int] = None,
) -> Validator[typing.Union[T, typing.Any]]:
    """
    Build a validator for a generic type.

    :param target: The target generic type to build validator for
    :return: A validator function for the target type
    """
    from attrib.adapters._concrete import build_concrete_type_validator

    next_depth = None
    if depth is not None:
        if depth <= 0:
            return lambda value, *args, **kwargs: None
        else:
            next_depth = depth - 1

    origin, type_args = get_type_info(target)
    if not (origin or type_args):
        raise TypeError(f"Cannot build validator for non-generic type {target!r}")

    if origin is None:
        if not type_args:
            raise TypeError(
                f"Cannot build deserializer for non-generic type {target!r}"
            )
        args_validators = tuple(
            build_generic_type_validator(arg, depth=next_depth)
            if is_generic_type(arg)
            else build_concrete_type_validator(arg, depth=next_depth)
            for arg in type_args
        )
        if len(args_validators) == 1:
            return args_validators[0]
        return Or(args_validators)

    elif origin and not type_args:
        return (
            build_generic_type_validator(origin, depth=next_depth)
            if is_generic_type(origin)
            else build_concrete_type_validator(origin, depth=next_depth)
        )

    # If the origin is not a class, we can just build an Or validator
    # from the arguments validators.
    if not inspect.isclass(origin):
        if origin is typing.Literal:
            return is_(type_args[0]) if len(type_args) == 1 else member_of(type_args)

        if origin is typing.Union and NoneType in type_args:
            # If the origin is Union and NoneType is one of the arguments,
            # we have an optional type.
            args_validators = tuple(
                build_generic_type_validator(arg, depth=next_depth)
                if is_generic_type(arg)
                else build_concrete_type_validator(arg, depth=next_depth)
                for arg in type_args
                if arg is not NoneType
            )
            if not args_validators:
                raise TypeError(
                    f"Cannot build validator for generic type {target!r} with origin {origin!r} and arguments {type_args!r}"
                )
            if len(args_validators) == 1:
                return optional(args_validators[0])
            return optional(Or(args_validators))

        args_validators = tuple(
            build_generic_type_validator(arg, depth=next_depth)
            if is_generic_type(arg)
            else build_concrete_type_validator(arg, depth=next_depth)
            for arg in type_args
        )
        return Or(args_validators)

    args_validators = tuple(
        build_generic_type_validator(arg, depth=next_depth)
        if is_generic_type(arg)
        else build_concrete_type_validator(arg, depth=next_depth)
        for arg in type_args
    )
    if is_mapping_origin(origin):
        assert len(args_validators) == 2, (
            f"Validator count mismatch. Expected 2 but got {len(args_validators)}"
        )
        key_validator, value_validator = args_validators
        return mapping(key_validator, value_validator)

    if is_sequence_or_set_origin(origin):
        args_count = len(type_args)
        assert args_count == len(args_validators), (
            f"Validator count mismatch. Expected {args_count} but got {len(args_validators)}"
        )

        if issubclass(origin, tuple) and len(args_validators) > 1:

            def tuple_validator(
                value: typing.Any,
                *args: typing.Any,
                **kwargs: typing.Any,
            ) -> None:
                if not isinstance(value, Iterable) or len(value) != args_count:  # type: ignore
                    raise InvalidTypeError(
                        f"Expected an Iterable with {args_count} items.",
                        input_type=type(value),
                        expected_type=origin,
                    )

                for index, item in enumerate(value):
                    try:
                        args_validators[index](item, *args, **kwargs)
                    except (ValidationError, TypeError, ValueError) as exc:
                        raise ValidationError.from_exc(
                            exc,
                            input_type=type(value),
                            expected_type=type_args[index],
                            location=[index],
                        ) from exc

                return None

            return tuple_validator

        if len(args_validators) == 1:
            return iterable(args_validators[0])
        return iterable(Or(args_validators))

    raise TypeError(
        f"Cannot build validator for generic type {target!r} with origin {origin!r} and arguments {type_args!r}"
    )


@typing.overload
def build_generic_type_serializer(
    target: typing.Union[typing.Type[T], T, typing.Any],
    *,
    fmt: typing.Literal["python"] = ...,
    depth: typing.Optional[int] = None,
) -> Serializer[typing.Any]: ...


@typing.overload
def build_generic_type_serializer(
    target: typing.Union[typing.Type[T], T, typing.Any],
    *,
    fmt: typing.Literal["json"] = ...,
    depth: typing.Optional[int] = None,
) -> Serializer[JSONValue]: ...


@functools.lru_cache(maxsize=128)
def build_generic_type_serializer(
    target: typing.Union[typing.Type[T], T, typing.Any],
    *,
    fmt: typing.Literal["json", "python"] = "python",
    depth: typing.Optional[int] = None,
) -> Serializer[typing.Any]:
    """
    Build a python serializer for a generic type.

    :param target: The target generic type to build serializer for
    :param depth: Optional depth for serialization
    :return: A serializer function for the target type
    """
    from attrib.adapters._concrete import build_concrete_type_serializer

    next_depth = None
    if depth is not None:
        if depth <= 0:
            return lambda value, *args, **kwargs: value
        else:
            next_depth = depth - 1

    origin, type_args = get_type_info(target)

    if not (origin or type_args):
        raise TypeError(
            f"Cannot build {fmt!r} serializer for non-generic type {target!r}"
        )

    if origin is None:
        if not type_args:
            raise TypeError(
                f"Cannot build {fmt!r} serializer for non-generic type {target!r}"
            )
        return coalesce(
            *(
                build_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
                if is_generic_type(arg)
                else build_concrete_type_serializer(arg, fmt=fmt, depth=next_depth)
                for arg in type_args
            ),
            target=(
                TypeError,
                ValueError,
                SerializationError,
            ),
            detailed_exc_type=SerializationError,
        )

    elif origin and not type_args:
        return (
            build_generic_type_serializer(origin, fmt=fmt, depth=next_depth)
            if is_generic_type(origin)
            else build_concrete_type_serializer(origin, fmt=fmt, depth=next_depth)
        )

    args_serializers = tuple(
        build_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
        if is_generic_type(arg)
        else build_concrete_type_serializer(arg, fmt=fmt, depth=next_depth)
        for arg in type_args
    )

    if not inspect.isclass(origin):
        if origin is typing.Literal:
            return build_concrete_type_serializer(str, fmt=fmt, depth=next_depth)

        if origin is typing.Union and NoneType in type_args:
            # If the origin is Union and NoneType is one of the arguments,
            # we have an optional type.
            any_serializer = coalesce(
                *(
                    build_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
                    if is_generic_type(arg)
                    else build_concrete_type_serializer(arg, fmt=fmt, depth=next_depth)
                    for arg in type_args
                    if arg is not NoneType
                ),
                target=(
                    TypeError,
                    ValueError,
                    SerializationError,
                ),
                detailed_exc_type=SerializationError,
            )

            def optional_serializer(
                value: typing.Any, *args: typing.Any, **kwargs: typing.Any
            ) -> typing.Optional[typing.Any]:
                if value is None:
                    return None
                return any_serializer(value, *args, **kwargs)

            return optional_serializer

        args_serializers = tuple(
            build_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
            if is_generic_type(arg)
            else build_concrete_type_serializer(arg, fmt=fmt, depth=next_depth)
            for arg in type_args
        )
        return coalesce(
            *args_serializers,
            target=(
                TypeError,
                ValueError,
                SerializationError,
            ),
            detailed_exc_type=SerializationError,
        )

    args_serializers = tuple(
        build_generic_type_serializer(arg, fmt=fmt, depth=next_depth)
        if is_generic_type(arg)
        else build_concrete_type_serializer(arg, fmt=fmt, depth=next_depth)
        for arg in type_args
    )
    if is_mapping_origin(origin):
        assert len(args_serializers) == 2, (
            f"Serializer count mismatch. Expected 2 but got {len(args_serializers)}"
        )

        key_serializer, value_serializer = args_serializers
        if inspect.isabstract(origin) or not issubclass(origin, MutableMapping):
            origin = dict

        def mapping_serializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Mapping[typing.Any, typing.Any]:
            if not isinstance(value, (Mapping, Iterable)):
                raise InvalidTypeError(
                    "Expected a Mapping or Iterable.",
                    input_type=type(value),
                    expected_type=origin,
                )

            new_mapping = origin.__new__(origin)  # type: ignore[assignment]
            if isinstance(value, Mapping):
                items = value.items()
            else:
                items = iter(value)

            for key, item in items:
                try:
                    new_mapping[key_serializer(key, *args, **kwargs)] = (
                        value_serializer(item, *args, **kwargs)
                    )
                except (SerializationError, TypeError, ValueError) as exc:
                    raise SerializationError.from_exc(
                        exc,
                        input_type=type(value),
                        expected_type=origin,
                        location=[key],
                    ) from exc
            return new_mapping

        return mapping_serializer

    if is_sequence_or_set_origin(origin):
        args_count = len(type_args)
        serializers_count = len(args_serializers)
        assert args_count == serializers_count, (
            f"Serializer count mismatch. Expected {args_count} but got {serializers_count}"
        )

        if issubclass(origin, tuple) and args_count > 1:

            def tuple_serializer(
                value: typing.Any,
                *args: typing.Any,
                **kwargs: typing.Any,
            ) -> typing.Tuple[typing.Any, ...]:
                if not isinstance(value, Iterable) or len(value) != args_count:  # type: ignore
                    raise InvalidTypeError(
                        f"Expected an Iterable with {args_count} items.",
                        input_type=type(value),
                        expected_type=origin,
                    )

                new_tuple = []
                for index, item in enumerate(value):
                    try:
                        new_tuple.append(args_serializers[index](item, *args, **kwargs))
                    except (SerializationError, TypeError, ValueError) as exc:
                        raise SerializationError.from_exc(
                            exc,
                            input_type=type(value),
                            expected_type=type_args[index],
                            location=[index],
                        ) from exc
                return origin(new_tuple)  # type: ignore

            return tuple_serializer

        if inspect.isabstract(origin) or not issubclass(origin, MutableSequence):
            origin = list

        def iterable_serializer(
            value: typing.Any,
            *args: typing.Any,
            **kwargs: typing.Any,
        ) -> typing.Iterable[typing.Any]:
            if not isinstance(value, Iterable):
                raise InvalidTypeError(
                    "Expected an Iterable.",
                    input_type=type(value),
                    expected_type=origin,
                )
            new_iterable = []
            for item_index, item in enumerate(value):
                error = None
                for arg_index, serializer in enumerate(args_serializers):
                    try:
                        new_iterable.append(serializer(item, *args, **kwargs))
                        break
                    except (SerializationError, TypeError, ValueError) as exc:
                        if error is None:
                            error = SerializationError.from_exc(
                                exc,
                                message="Failed to serialize item at index",
                                input_type=type(value),
                                expected_type=type_args[arg_index],
                                location=[item_index],
                            )
                        else:
                            error.add(
                                exc,
                                input_type=type(value),
                                expected_type=type_args[arg_index],
                                location=[item_index],
                            )
                else:
                    if error:
                        raise error

            return origin(new_iterable)  # type: ignore

        return iterable_serializer

    raise TypeError(
        f"Cannot build {fmt!r} serializer for generic type {target!r} with origin {origin!r} and arguments {type_args!r}"
    )


def build_generic_type_serializers_map(
    target: typing.Union[typing.Type[T], T],
    /,
    serializers: typing.Optional[SerializerMap] = None,
    depth: typing.Optional[int] = None,
) -> typing.Dict[str, Serializer[typing.Any]]:
    """
    Build a serializer map for generic types.

    :param target: The target generic type.
    :param serializers: A mapping of serialization formats to their respective serializer functions
    :param depth: Optional depth for serialization
    """
    serializers_map = {**(serializers or {})}
    if "json" not in serializers_map:
        json_serializer = build_generic_type_serializer(
            target,
            fmt="json",
            depth=depth,
        )
        serializers_map["json"] = json_serializer
    if "python" not in serializers_map:
        python_serializer = build_generic_type_serializer(
            target,
            fmt="python",
            depth=depth,
        )
        serializers_map["python"] = python_serializer
    return serializers_map
