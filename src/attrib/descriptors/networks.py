import typing
import ipaddress
from typing_extensions import Unpack
from urllib.parse import urlparse, ParseResult as Url, ParseResultBytes as UrlBytes

from attrib.descriptors.base import Field, FieldKwargs, to_string_serializer
from attrib.exceptions import ValidationError


__all__ = [
    "URL",
    "IPAddress",
    "allowed_schemes",
    "allowed_hosts",
    "allowed_ports",
]


def url_deserializer(
    value: typing.Any,
    *_: typing.Any,
    **__: typing.Any,
) -> typing.Union[Url, UrlBytes]:
    """Deserialize URL data to the specified type."""
    return urlparse(value)


class URL(Field[typing.Union[Url, UrlBytes]]):
    """Field for handling URL values."""

    default_serializers = {
        "json": to_string_serializer,
    }
    default_deserializer = url_deserializer

    def __init__(self, **kwargs: Unpack[FieldKwargs]) -> None:
        super().__init__(field_type=(Url, UrlBytes), **kwargs)


def ip_address_deserializer(
    value: typing.Any,
    *_: typing.Any,
    **__: typing.Any,
) -> typing.Any:
    """Deserialize IP address data to an IP address object."""
    return ipaddress.ip_address(value)


class IPAddress(Field[typing.Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]):
    """Field for handling IP addresses."""

    default_serializers = {
        "json": to_string_serializer,
    }
    default_deserializer = ip_address_deserializer

    def __init__(
        self,
        **kwargs: Unpack[FieldKwargs],
    ):
        super().__init__(
            field_type=(
                ipaddress.IPv4Address,
                ipaddress.IPv6Address,
            ),
            **kwargs,
        )


############################
######## Validators ########
############################


def allowed_schemes(
    http: bool = False,
    https: bool = False,
    ftp: bool = False,
    file: bool = False,
    data: bool = False,
    ws: bool = False,
    wss: bool = False,
    custom: typing.Optional[typing.List[str]] = None,
    allow_empty: bool = True,
    message: typing.Optional[str] = None,
):
    """
    Allow specified URL schemes only.

    :param http: Allow HTTP scheme.
    :param https: Allow HTTPS scheme.
    :param ftp: Allow FTP scheme.
    :param file: Allow FILE scheme.
    :param data: Allow DATA scheme.
    :param ws: Allow WS scheme.
    :param wss: Allow WSS scheme.
    :param custom: Allow custom schemes.
    :param message: Custom error message.
    :return: A validator function that checks the URL scheme.

    Example:
    ```
    import attrib
    from attrib.descriptors.urls import allowed_schemes

    class Website(attrib.Dataclass):
        '''Website Info '''
        name = attrib.String(allow_null=True, default=None)
        url = attrib.URL(
            validator=allowed_schemes(
                https=True,
                custom=["mycustomscheme"],
            )
            required=True,
        )

    website = Website(
        name="My Website",
        url="http://example.com",
    )

    # raises ValidationError since only https and custom schemes are allowed
    ```
    """
    if not any(
        (
            http,
            https,
            ftp,
            file,
            data,
            ws,
            wss,
            custom,
        )
    ):
        raise ValueError("At least one scheme must be specified.")

    schemes = []
    if http:
        schemes.append("http")
    if https:
        schemes.append("https")
    if ftp:
        schemes.append("ftp")
    if file:
        schemes.append("file")
    if data:
        schemes.append("data")
    if ws:
        schemes.append("ws")
    if wss:
        schemes.append("wss")
    if custom:
        schemes.extend(custom)

    msg = message or "Scheme not allowed."
    schemes = set(schemes)

    def validator(
        value: typing.Any,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        scheme: typing.Optional[str] = getattr(value, "scheme", None)
        if scheme is None and isinstance(value, str):
            parsed_url = urlparse(value)
            scheme = parsed_url.scheme

        if not allow_empty and not scheme:
            raise ValidationError(
                "Empty scheme not allowed.",
                input_type=type(value),
                expected_type="url",
                code="invalid_url",
            )

        if scheme and scheme.lower() not in schemes:
            raise ValidationError(
                msg.format(value=value, scheme=scheme),
                input_type=type(value),
                expected_type="url",
                code="invalid_scheme",
                context={"scheme": scheme},
            )
        return None

    return validator


def allowed_hosts(
    allowed_hosts: typing.Iterable[str],
    allow_empty: bool = True,
    message: typing.Optional[str] = None,
):
    """
    URL host must be one of the allowed hosts.

    :param allowed_hosts: List of allowed hosts.
    :param allow_empty: Allow empty host.
    :param message: Custom error message.
    :return: A validator function that checks if the URL host is allowed.

    Example:
    ```
    import attrib
    from attrib.descriptors.urls import allowed_hosts

    class Website(attrib.Dataclass):
        '''Website Info '''
        name = attrib.String(allow_null=True, default=None)
        url = attrib.URL(
            validator=allowed_hosts(["example.com", "mywebsite.com"]),
            required=True,
        )

    website1 = Website(
        name="My Website",
        url="http://example.com",
    ) # Valid host

    website2 = Website(
        name="My Website",
        url="http://notallowed.com",
    ) # raises ValidationError since the host is not allowed
    ```
    """
    msg = message or "Host not allowed."
    allowed_hosts = set(allowed_hosts)

    def validator(
        value: typing.Any,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        host: typing.Optional[str] = getattr(value, "hostname", None)
        if host is None and isinstance(value, str):
            parsed_url = urlparse(value)
            host = parsed_url.hostname

        if not allow_empty and not host:
            raise ValidationError(
                "Empty host not allowed.",
                input_type=type(value),
                expected_type="url",
                code="invalid_url",
            )

        if host and host.lower() not in allowed_hosts:
            raise ValidationError(
                msg.format(value=value, host=host),
                input_type=type(value),
                expected_type="url",
                code="disallowed_host",
                context={"host": host},
            )
        return None

    return validator


def allowed_ports(
    allowed_ports: typing.Iterable[int],
    allow_empty: bool = True,
    message: typing.Optional[str] = None,
):
    """
    URL port must be one of the allowed ports.

    :param allowed_ports: List of allowed ports.
    :param allow_empty: Allow empty port.
    :param message: Custom error message.
    :return: A validator function that checks if the URL port is allowed.

    Example:
    ```
    import attrib
    from attrib.descriptors.urls import allowed_ports

    class Website(attrib.Dataclass):
        '''Website Info '''
        name = attrib.String(allow_null=True, default=None)
        url = attrib.URL(
            validator=allowed_ports([80, 443]),
            required=True,
        )

    website1 = Website(
        name="My Website",
        url="http://example.com:80",
    ) # Valid port

    website2 = Website(
        name="My Website",
        url="http://example.com:8080",
    ) # raises ValidationError since the port is not allowed
    ```
    """
    msg = message or "Port not allowed."
    allowed_ports = set(allowed_ports)

    def validator(
        value: typing.Any,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        port: typing.Optional[int] = getattr(value, "port", None)
        if port is None and isinstance(value, str):
            parsed_url = urlparse(value)
            port = parsed_url.port

        if not allow_empty and port is None:
            raise ValidationError(
                "Empty port not allowed.",
                input_type=type(value),
                expected_type="url",
                code="invalid_url",
            )
        if port not in allowed_ports:
            raise ValidationError(
                msg.format(value=value, port=port),
                input_type=type(value),
                expected_type="url",
                code="disallowed_port",
                context={"port": port},
            )
        return None

    return validator
