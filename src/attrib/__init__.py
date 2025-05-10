"""
`attrib` is a data desciption library for Python.

Setup structured data with fields that support type enforcement, validation, and serialization.
"""

from .dataclass import Dataclass, load, deserialize, from_dict, from_attributes  # noqa
from .descriptors import *  # noqa
from .nested import Nested  # noqa
from .serializers import serialize, Option  # noqa
from . import validators  # noqa


__version__ = "0.0.1"
