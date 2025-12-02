import enum
import random
import typing

import attrib
from mock_data import category_data, customer_data, product_data
from utils import timeit, profileit


class ProductStatus(enum.Enum):
    """Product status enumeration"""

    AVAILABLE = "available"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"


@attrib.define(repr=True)
class Category:
    """Product category data class"""

    id = attrib.field(int, required=True)
    name = attrib.field(str, max_length=100)
    description = attrib.field(str, allow_null=True, default=None)


class Product(attrib.Dataclass, sort=True, repr=False, hash=True, frozen=True):
    """Product data class"""

    id = attrib.field(int, required=True, hash=True)
    name = attrib.field(str, max_length=100, hash=True)
    price = attrib.field(float, min_value=0.01, hash=True)
    quantity = attrib.field(int, min_value=0, default=0)
    category = attrib.field(Category)
    status = attrib.field(attrib.Choice[ProductStatus], default=ProductStatus.AVAILABLE)


@attrib.define(repr=True)
class Customer:
    """Customer data class"""

    id = attrib.field(int, required=True)
    name = attrib.field(str, max_length=100)
    email = attrib.field(str)
    stock_level = attrib.field(
        int, min_value=0, default=attrib.Factory(random.randint, a=10, b=100)
    )
    products = attrib.List(
        child=attrib.field(Product),
        validator=attrib.validators.and_(
            attrib.validators.min_length(1),
            attrib.validators.max_length(50),
        ),
        serialization_alias="inventory",
    )

    __config__ = attrib.MetaConfig(sort=True)


@attrib.define(repr=True)
class Order:
    """Order data class"""

    id = attrib.field(int, required=True)
    customer = attrib.field(Customer)
    items = attrib.List(
        child=attrib.field(Product),
        validator=attrib.validators.min_length(1),
    )
    order_total = attrib.field(
        float, min_value=0.0, default=attrib.Factory(random.uniform, a=10.0, b=1000.0)
    )


DataclassTco = typing.TypeVar("DataclassTco", bound=attrib.Dataclass, covariant=True)


def load(
    data_list: typing.List[typing.Dict[str, typing.Any]],
    cls: typing.Type[DataclassTco],
) -> typing.List[DataclassTco]:
    """
    Load data into data classes

    :param data_list: List of dictionaries containing data
    :param cls: Data class to load data into
    :return: List of the data class instances
    """
    return [
        attrib.deserialize(cls, data, config=attrib.InitConfig(fail_fast=True))
        for data in data_list
    ]


customers = load(customer_data, Customer)
products = load(product_data, Product)
categories = load(category_data, Category)


def serialization_example(mode: typing.Literal["json", "python"] = "python") -> None:
    """Run example usage of the data classes"""
    for customer in customers:
        attrib.serialize(
            customer,
            fmt=mode,
            # options=customer_options,
        )

    for product in products:
        attrib.serialize(product, fmt=mode)

    for category in categories:
        attrib.serialize(category, fmt=mode)


def deserialization_example() -> None:
    """Run example usage of the data classes"""
    load(customer_data, Customer)
    load(product_data, Product)
    load(category_data, Category)


@timeit("attrib")
def test_serialization(
    n: int = 1, mode: typing.Literal["json", "python"] = "python"
) -> None:
    """Run the attrib example multiple times"""
    for _ in range(n):
        serialization_example(mode=mode)


@timeit("attrib")
def test_deserialization(n: int = 1) -> None:
    """Run the attrib example multiple times"""
    for _ in range(n):
        deserialization_example()
