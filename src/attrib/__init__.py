"""
`attrib` is a performant data desciption library for Python.

Setup structured data with fields that support type enforcement, validation, and serialization.
"""

from .dataclass import *  # noqa
from .descriptors.base import *  # noqa
from .descriptors.nested import Nested  # noqa
from .descriptors.colors import *  # noqa
from .descriptors.networks import *  # noqa
from .descriptors.datetime import *  # noqa
from .serializers import serialize, Option, Options  # noqa
from . import validators  # noqa
from ._utils import *  # noqa
from .adapters import TypeAdapter  # noqa
from ._typing import Empty, EMPTY  # noqa
from . import exceptions  # noqa
from .decorators import *  # noqa
from .contextmanagers import * # noqa


__version__ = "0.0.1"
