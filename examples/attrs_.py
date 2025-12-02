import enum
import random
import typing

import attrs
from cattrs import Converter
from cattrs.gen import make_dict_unstructure_fn, override

from mock_data import category_data, customer_data, product_data
from utils import timeit

################
# DATA CLASSES #
################


class ProductStatus(enum.Enum):
    """Product status enumeration"""

    AVAILABLE = "available"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"


@attrs.define()
class Category:
    """Product category data class"""

    id: int = attrs.field()
    name: typing.Optional[str] = attrs.field(
        default=None, validator=attrs.validators.max_len(100)
    )
    description: typing.Optional[str] = attrs.field(default=None)


@attrs.define()
class Product:
    """Product data class"""

    id: int = attrs.field()
    name: str = attrs.field(validator=attrs.validators.max_len(100))
    price: float = attrs.field(validator=attrs.validators.gt(0.0))
    quantity: int = attrs.field(validator=attrs.validators.ge(0))
    category: Category = attrs.field()
    status: ProductStatus = attrs.field(default=ProductStatus.AVAILABLE)


@attrs.define(kw_only=True)
class Customer:
    """Customer data class"""

    id: int = attrs.field()
    name: str = attrs.field(validator=attrs.validators.max_len(100))
    email: str = attrs.field()
    stock_level: int = attrs.field(
        default=attrs.Factory(lambda: random.randint(10, 100)),
    )
    products: typing.List[Product] = attrs.field(
        default=attrs.Factory(list),
        validator=attrs.validators.and_(
            attrs.validators.min_len(1),
            attrs.validators.max_len(50),
        ),
    )


@attrs.define()
class Order:
    """Order data class"""

    id: int = attrs.field()
    customer: Customer = attrs.field()
    items: typing.List[Product] = attrs.field(
        default=attrs.Factory(list),
        validator=attrs.validators.min_len(1),
    )
    order_total: float = attrs.field(
        default=attrs.Factory(lambda: random.uniform(10.0, 1000.0)),
    )


def configure_converters() -> Converter:
    """Configure cattrs converter for custom serialization/deserialization"""
    converter = Converter()

    converter.register_unstructure_hook(ProductStatus, lambda e: e.value)

    # For Customer class, rename 'products' to 'inventory' during serialization
    customer_unstruct_hook = make_dict_unstructure_fn(
        Customer,
        converter,
        _cattrs_omit_if_default=False,
        products=override(rename="inventory"),
    )
    converter.register_unstructure_hook(Customer, customer_unstruct_hook)

    return converter


converter = configure_converters()

AttrsclassT = typing.TypeVar("AttrsclassT")


def load(
    data_list: typing.List[typing.Dict[str, typing.Any]], cls: typing.Type[AttrsclassT]
) -> typing.List[AttrsclassT]:
    return [converter.structure(data, cls) for data in data_list]


categories = load(category_data, Category)
products = load(product_data, Product)
customers = load(customer_data, Customer)


def serialization_example():
    for customer in customers:
        converter.unstructure(customer)

    for product in products:
        converter.unstructure(product)

    for category in categories:
        converter.unstructure(category)


def deserialization_example():
    load(customer_data, Customer)
    load(product_data, Product)
    load(category_data, Category)


@timeit("attrs + cattrs")
def test_serialization(n: int, mode: str = "python") -> None:
    for _ in range(n):
        serialization_example()


@timeit("attrs + cattrs")
def test_deserialization(n: int) -> None:
    for _ in range(n):
        deserialization_example()
