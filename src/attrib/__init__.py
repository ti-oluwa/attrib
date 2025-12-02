"""
`attrib` is a performant data desciption library for Python.

Setup structured data with fields that support type enforcement, validation, and serialization.
"""

from .dataclasses import *  # noqa
from .descriptors.base import *  # noqa
from .descriptors.nested import *  # noqa
from .descriptors.colors import *  # noqa
from .descriptors.networks import *  # noqa
from .descriptors.datetime import *  # noqa
from .serializers import *  # noqa
from . import validators  # noqa
from ._utils import *  # noqa
from ._field import field  # noqa
from .adapters import TypeAdapter  # noqa
from .types import Empty, EMPTY  # noqa
from . import exceptions  # noqa
from .decorators import *  # noqa
from .exceptions import *  # noqa


__version__ = "0.0.1a0"
