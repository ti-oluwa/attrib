"""
`attrib` is a performant data desciption library for Python.

Setup structured data with fields that support type enforcement, validation, and serialization.
"""

from .dataclass import Dataclass, Config, load, deserialize, from_attributes  # noqa
from .descriptors import *  # noqa
from .nested import Nested  # noqa
from .serializers import serialize, Option  # noqa
from . import validators  # noqa
from ._utils import make_jsonable, SerializerRegistry, iexact  # noqa


__version__ = "0.0.1"
