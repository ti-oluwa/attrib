"""Tests for attrib decorator functions."""

import datetime

import pytest

import attrib
from attrib.exceptions import (
    ConfigurationError,
    DeserializationError,
    FrozenInstanceError,
)
from tests.conftest import Person


class TestMakeDecorator:
    """Test the make decorator/factory function."""

    def test_make_simple_dataclass(self):
        """Test creating a simple dataclass dynamically."""
        User = attrib.make(
            "User",
            fields={
                "id": int,
                "username": str,
                "email": str,
            },
        )
        user = User(id=1, username="alice", email="alice@example.com")
        assert user.id == 1
        assert user.username == "alice"
        assert user.email == "alice@example.com"

    def test_make_with_field_instances(self):
        """Test creating dataclass with Field instances."""
        Product = attrib.make(
            "Product",
            fields={
                "id": attrib.field(int, required=True),
                "name": attrib.field(str, max_length=100),
                "price": attrib.field(float, min_value=0),
                "stock": attrib.field(int, default=0),
            },
        )
        product = Product(id=1, name="Widget", price=19.99)
        assert product.id == 1
        assert product.name == "Widget"
        assert product.price == 19.99
        assert product.stock == 0

    def test_make_with_copy_fields(self):
        """Test that copy_fields prevents shared state."""
        base_field = attrib.field(str, max_length=50)
        Config = attrib.make(
            "Config",
            fields={
                "key": base_field,
                "value": base_field,
            },
            copy_fields=True,
        )
        # Fields should be independent copies
        assert (
            Config.__dataclass_fields__["key"]
            is not Config.__dataclass_fields__["value"]
        )

    def test_make_with_meta_kwargs(self):
        """Test creating dataclass with metaclass kwargs."""
        ImmutableUser = attrib.hashable(
            attrib.make(
                "ImmutableUser",
                fields={
                    "id": int,
                    "name": str,
                },
                frozen=True,
            ),
            include=["id", "name"],
        )
        user = ImmutableUser(id=1, name="Bob")
        assert hash(user) is not None
        with pytest.raises(FrozenInstanceError):
            user.name = "Alice"

    def test_make_with_module(self):
        """Test creating dataclass with custom module."""
        TestModel = attrib.make(
            "TestModel",
            fields={"value": int},
            module="custom.module",
        )
        assert TestModel.__module__ == "custom.module"


class TestDefineDecorator:
    """Test the define/dataclass decorator."""

    def test_define_basic_class(self):
        """Test converting a class to dataclass."""

        @attrib.define
        class Book:
            title = attrib.field(str)
            author = attrib.field(str)
            year = attrib.field(int, allow_null=True, default=None)

        book = Book(title="1984", author="George Orwell")
        assert book.title == "1984"
        assert book.author == "George Orwell"
        assert book.year is None

    def test_define_with_type_annotations_only(self):
        """Test define with type annotations but no fields."""

        @attrib.define
        class Point:
            x = attrib.field(int)
            y = attrib.field(int)

        point = Point(x=10, y=20)
        assert point.x == 10
        assert point.y == 20

    def test_define_with_meta_config(self):
        """Test define with MetaConfig."""

        @attrib.define
        class Record:
            id = attrib.field(int, required=True, hash=True)
            name = attrib.field(str)

            __config__ = attrib.MetaConfig(frozen=True, hash=True)

        record = Record(id=1, name="Test")
        assert hash(record) is not None
        with pytest.raises(FrozenInstanceError):
            record.name = "Changed"

    def test_define_with_meta_kwargs(self):
        """Test define with meta kwargs override."""

        @attrib.define(repr=True, frozen=True)
        class Item:
            id = attrib.field(int)
            name = attrib.field(str)

        item = Item(id=1, name="Widget")
        assert "id=1" in repr(item)
        with pytest.raises(FrozenInstanceError):
            item.name = "Gadget"

    def test_define_already_dataclass(self):
        """Test that defining an already-dataclass returns it unchanged."""
        result = attrib.define(Person)
        assert result is Person

    def test_dataclass_alias(self):
        """Test that dataclass is an alias for define."""

        @attrib.dataclass
        class Tag:
            name: str

        tag = Tag(name="important")
        assert tag.name == "important"


class TestModifyDecorator:
    """Test the modify decorator."""

    def test_modify_with_strict(self):
        """Test modifying fields to be strict."""

        @attrib.define
        class User:
            id = attrib.field(int)
            name = attrib.field(str)
            age = attrib.field(int)

        StrictUser = attrib.modify(User, strict=True, prefix="Strict")

        # Should not coerce types when strict
        with pytest.raises(DeserializationError):
            attrib.deserialize(StrictUser, {"id": "123", "name": "Alice", "age": 30})

    def test_modify_with_include(self):
        """Test modifying only included fields."""

        @attrib.define
        class Product:
            id = attrib.field(int, required=True)
            name = attrib.field(str)
            price = attrib.field(float)
            stock = attrib.field(int)

        StrictProduct = attrib.modify(
            Product,
            include=["name", "price"],
            strict=True,
            prefix="Strict",
        )

        # Only name and price should be strict
        assert StrictProduct.__dataclass_fields__["name"].strict is True
        assert StrictProduct.__dataclass_fields__["price"].strict is True
        assert StrictProduct.__dataclass_fields__["id"].strict is False
        assert StrictProduct.__dataclass_fields__["stock"].strict is False

    def test_modify_with_exclude(self):
        """Test modifying with excluded fields."""

        @attrib.define
        class Config:
            host = attrib.field(str)
            port = attrib.field(int)
            timeout = attrib.field(int, default=30)
            debug = attrib.field(bool, default=False)

        RequiredConfig = attrib.modify(
            Config,
            exclude=["debug"],
            required=True,
            prefix="Required",
        )

        # debug should not be modified
        assert RequiredConfig.__dataclass_fields__["host"].required is True
        assert RequiredConfig.__dataclass_fields__["port"].required is True
        assert RequiredConfig.__dataclass_fields__["timeout"].required is True
        assert RequiredConfig.__dataclass_fields__["debug"].required is False

    def test_modify_with_selector(self):
        """Test modifying with a selector function."""

        @attrib.define
        class Record:
            id = attrib.field(int, required=True)
            name = attrib.field(str)
            age = attrib.field(int, allow_null=True)
            email = attrib.field(str, allow_null=True)

        # Only modify fields that allow null
        NullableStrict = attrib.modify(
            Record,
            selector=lambda name, field: field.allow_null,
            strict=True,
            prefix="NullableStrict",
        )

        assert NullableStrict.__dataclass_fields__["id"].strict is False
        assert NullableStrict.__dataclass_fields__["name"].strict is False
        assert NullableStrict.__dataclass_fields__["age"].strict is True
        assert NullableStrict.__dataclass_fields__["email"].strict is True

    def test_modify_with_iterator_values(self):
        """Test modifying with iterator attribute values."""

        @attrib.define
        class Task:
            id = attrib.field(int)
            title = attrib.field(str)
            priority = attrib.field(int)
            status = attrib.field(str)

        # Use iter() to create an iterator
        order = iter((0, 1, 2, 3))
        OrderedTask = attrib.modify(
            Task,
            order=order,
            prefix="Ordered",
            meta_kwargs={"order": True},
        )

        assert OrderedTask.__dataclass_fields__["id"].order == 0
        assert OrderedTask.__dataclass_fields__["title"].order == 1
        assert OrderedTask.__dataclass_fields__["priority"].order == 2
        assert OrderedTask.__dataclass_fields__["status"].order == 3

    def test_modify_with_required(self):
        """Test modifying fields to be required."""

        @attrib.define
        class Form:
            name = attrib.field(str, default="")
            email = attrib.field(str, default="")
            message = attrib.field(str, default="")

        RequiredForm = attrib.modify(Form, required=True, prefix="Required")

        # All fields should now be required (no defaults)
        assert RequiredForm.__dataclass_fields__["name"].default is attrib.EMPTY
        assert RequiredForm.__dataclass_fields__["email"].default is attrib.EMPTY
        assert RequiredForm.__dataclass_fields__["message"].default is attrib.EMPTY

    def test_modify_as_decorator(self):
        """Test using modify as a decorator."""

        @attrib.define
        class Base:
            x = attrib.field(int)
            y = attrib.field(int)

        @attrib.modify(strict=True, prefix="Strict")
        class StrictBase(Base):
            pass

        assert StrictBase.__dataclass_fields__["x"].strict is True
        assert StrictBase.__dataclass_fields__["y"].strict is True

    def test_modify_with_meta_kwargs(self):
        """Test modifying with metaclass kwargs."""

        @attrib.define
        class Mutable:
            id = attrib.field(int)
            value = attrib.field(str)

        Immutable = attrib.modify(
            Mutable,
            hash=True,
            prefix="Immutable",
            meta_kwargs={"frozen": True, "hash": True},
        )

        immutable = Immutable(id=1, value="test")
        assert hash(immutable) is not None
        with pytest.raises(FrozenInstanceError):
            immutable.value = "changed"

    def test_modify_error_no_modifications(self):
        """Test that modify raises error when no modifications provided."""
        with pytest.raises(ConfigurationError, match="No modifications"):
            attrib.modify(Person)

    def test_modify_error_invalid_attributes(self):
        """Test that modify raises error for invalid attributes."""
        with pytest.raises(ConfigurationError, match="Invalid field attributes"):
            attrib.modify(Person, invalid_attr=True, prefix="Test")

    def test_modify_error_include_and_exclude(self):
        """Test that modify raises error when both include and exclude used."""
        with pytest.raises(ConfigurationError, match="Cannot use both"):
            attrib.modify(
                Person, include=["name"], exclude=["age"], strict=True, prefix="Test"
            )

    def test_modify_error_selector_with_include(self):
        """Test that modify raises error when selector used with include."""
        with pytest.raises(ConfigurationError, match="Cannot use 'selector'"):
            attrib.modify(
                Person,
                selector=lambda n, f: True,
                include=["name"],
                strict=True,
                prefix="Test",
            )

    def test_modify_error_no_fields_to_modify(self):
        """Test that modify raises error when no fields match filters."""
        with pytest.raises(ConfigurationError, match="No fields to modify"):
            attrib.modify(Person, include=["nonexistent"], strict=True, prefix="Test")

    def test_modify_error_iterator_exhausted(self):
        """Test that modify raises error when iterator is exhausted."""

        @attrib.define
        class Multi:
            a = attrib.field(int)
            b = attrib.field(int)
            c = attrib.field(int)

        with pytest.raises(ConfigurationError, match="exhausted"):
            attrib.modify(
                Multi, order=iter([0, 1]), prefix="Test"
            )  # Only 2 values for 3 fields


class TestStrictDecorator:
    """Test the strict convenience decorator."""

    def test_strict_all_fields(self):
        """Test making all fields strict."""

        @attrib.define
        class Loose:
            id = attrib.field(int)
            count = attrib.field(int)

        StrictLoose = attrib.strict(Loose, prefix="Strict")

        assert StrictLoose.__dataclass_fields__["id"].strict is True
        assert StrictLoose.__dataclass_fields__["count"].strict is True

    def test_strict_with_include(self):
        """Test making only specific fields strict."""

        @attrib.define
        class Mixed:
            id = attrib.field(int)
            name = attrib.field(str)
            age = attrib.field(int)

        PartialStrict = attrib.strict(Mixed, include=["id"], prefix="PartialStrict")

        assert PartialStrict.__dataclass_fields__["id"].strict is True
        assert PartialStrict.__dataclass_fields__["name"].strict is False
        assert PartialStrict.__dataclass_fields__["age"].strict is False


class TestPartialDecorator:
    """Test the partial convenience decorator."""

    def test_partial_all_fields(self):
        """Test making all fields optional."""

        @attrib.define
        class Required:
            name = attrib.field(str, required=True)
            email = attrib.field(str, required=True)
            age = attrib.field(int, required=True)

        OptionalRequired = attrib.partial(Required, prefix="Optional")

        assert OptionalRequired.__dataclass_fields__["name"].required is False
        assert OptionalRequired.__dataclass_fields__["name"].allow_null is True
        assert OptionalRequired.__dataclass_fields__["email"].required is False
        assert OptionalRequired.__dataclass_fields__["age"].required is False

    def test_partial_for_update_schema(self):
        """Test partial decorator for creating update schemas."""

        @attrib.define
        class CreateUser:
            username = attrib.field(str, max_length=50, required=True)
            email = attrib.field(str, required=True)
            password = attrib.field(str, min_length=8, required=True)
            age = attrib.field(int, min_value=0, required=True)

        UpdateUser = attrib.partial(CreateUser, prefix="Update")

        # Should be able to create instance with no required fields
        user_update = attrib.deserialize(UpdateUser, {"username": "newname"})
        assert user_update.username == "newname"
        assert user_update.email is None
        assert user_update.password is None
        assert user_update.age is None

    def test_partial_with_exclude(self):
        """Test partial with excluded fields."""

        @attrib.define
        class Entity:
            id = attrib.field(int, required=True)
            name = attrib.field(str, required=True)
            description = attrib.field(str, required=True)

        PartialEntity = attrib.partial(Entity, exclude=["id"], prefix="Partial")

        # ID should still be required
        assert PartialEntity.__dataclass_fields__["id"].required is True
        assert PartialEntity.__dataclass_fields__["name"].required is False
        assert PartialEntity.__dataclass_fields__["description"].required is False


class TestOrderedDecorator:
    """Test the ordered convenience decorator."""

    def test_ordered_all_fields(self):
        """Test ordering all fields."""

        @attrib.define
        class Unordered:
            z = attrib.field(int)
            y = attrib.field(int)
            x = attrib.field(int)

        OrderedClass = attrib.ordered(Unordered, prefix="Ordered")

        # Fields should have sequential order values
        assert OrderedClass.__dataclass_fields__["z"].order == 0
        assert OrderedClass.__dataclass_fields__["y"].order == 1
        assert OrderedClass.__dataclass_fields__["x"].order == 2

    def test_ordered_comparison(self):
        """Test that ordered dataclasses can be compared."""

        @attrib.define
        class Score:
            points = attrib.field(int)
            bonus = attrib.field(int, default=0)

        OrderedScore = attrib.ordered(Score, prefix="Ordered")

        score1 = OrderedScore(points=100, bonus=10)
        score2 = OrderedScore(points=100, bonus=20)
        score3 = OrderedScore(points=200, bonus=10)

        assert score1 < score2  # Same points, less bonus
        assert score1 < score3  # Less points
        assert score2 < score3

    def test_ordered_fresh_iterator(self):
        """Test that ordered creates fresh iterators for multiple uses."""

        @attrib.define
        class Item:
            a = attrib.field(int)
            b = attrib.field(int)

        # Should be able to create multiple ordered classes
        Ordered1 = attrib.ordered(Item, prefix="Ordered1")
        Ordered2 = attrib.ordered(Item, prefix="Ordered2")

        # Both should have proper ordering starting from 0
        assert Ordered1.__dataclass_fields__["a"].order == 0
        assert Ordered1.__dataclass_fields__["b"].order == 1
        assert Ordered2.__dataclass_fields__["a"].order == 0
        assert Ordered2.__dataclass_fields__["b"].order == 1


class TestHashableDecorator:
    """Test the hashable convenience decorator."""

    def test_hashable_creates_immutable(self):
        """Test that hashable creates frozen dataclass."""

        @attrib.define
        class Mutable:
            id = attrib.field(int)
            value = attrib.field(str)

        Immutable = attrib.hashable(Mutable, prefix="Immutable")

        instance = Immutable(id=1, value="test")

        # Should be hashable
        assert hash(instance) is not None

        # Should be frozen
        with pytest.raises(FrozenInstanceError):
            instance.value = "changed"

    def test_hashable_usable_in_set(self):
        """Test that hashable dataclass can be used in sets."""

        @attrib.define
        class Key:
            id = attrib.field(int)
            name = attrib.field(str)

        HashableKey = attrib.hashable(Key, prefix="Hashable")

        key1 = HashableKey(id=1, name="first")
        key2 = HashableKey(id=1, name="first")
        key3 = HashableKey(id=2, name="second")

        keys = {key1, key2, key3}
        assert len(keys) == 2  # key1 and key2 are equal

    def test_hashable_with_include(self):
        """Test hashable with specific fields."""

        @attrib.define
        class Record:
            id = attrib.field(int)
            value = attrib.field(str)
            metadata = attrib.field(str)

        HashableRecord = attrib.hashable(
            Record, include=["id", "value"], prefix="Hashable"
        )

        # Only specified fields should have hash=True
        assert HashableRecord.__dataclass_fields__["id"].hash is True
        assert HashableRecord.__dataclass_fields__["value"].hash is True
        assert HashableRecord.__dataclass_fields__["metadata"].hash is False


class TestFrozenDecorator:
    """Test the frozen convenience decorator."""

    def test_frozen_creates_immutable(self):
        """Test that frozen creates immutable dataclass."""

        @attrib.define
        class Mutable:
            x = attrib.field(int)
            y = attrib.field(int)

        Immutable = attrib.frozen(Mutable, prefix="Immutable")

        instance = Immutable(x=1, y=2)

        with pytest.raises(attrib.exceptions.FrozenInstanceError):
            instance.x = 10

    def test_frozen_prevents_deletion(self):
        """Test that frozen prevents attribute deletion."""

        @attrib.define
        class Data:
            value = attrib.field(int)

        FrozenData = attrib.frozen(Data, prefix="Frozen")

        instance = FrozenData(value=42)

        with pytest.raises(attrib.exceptions.FrozenInstanceError):
            del instance.value


class TestDecoratorCombinations:
    """Test combining multiple decorators."""

    def test_strict_and_partial(self):
        """Test combining strict and partial decorators."""

        @attrib.define
        class Base:
            id = attrib.field(int, required=True)
            name = attrib.field(str, required=True)
            value = attrib.field(int, required=True)

        # First make partial (optional)
        PartialBase = attrib.partial(Base, prefix="Partial")
        # Then make strict
        StrictPartial = attrib.strict(PartialBase, prefix="Strict")

        assert StrictPartial.__dataclass_fields__["id"].strict is True
        assert StrictPartial.__dataclass_fields__["id"].required is False
        assert StrictPartial.__dataclass_fields__["id"].allow_null is True

    def test_ordered_and_hashable(self):
        """Test combining ordered and hashable decorators."""

        @attrib.define
        class Item:
            priority = attrib.field(int)
            name = attrib.field(str)

        OrderedItem = attrib.ordered(Item, prefix="Ordered")
        HashableOrdered = attrib.hashable(OrderedItem, prefix="Hashable")

        item1 = HashableOrdered(priority=1, name="first")
        item2 = HashableOrdered(priority=2, name="second")

        # Should be comparable (ordered)
        assert item1 < item2

        # Should be hashable
        items = {item1, item2}
        assert len(items) == 2


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_api_request_response_schemas(self):
        """Test creating API request/response schemas."""

        @attrib.define
        class UserCreateRequest:
            username = attrib.field(str, max_length=50, required=True)
            email = attrib.field(str, required=True)
            password = attrib.field(str, min_length=8, required=True)
            age = attrib.field(int, min_value=0, allow_null=True, default=None)

        # Update schema allows partial updates
        UserUpdateRequest = attrib.partial(UserCreateRequest, prefix="UserUpdate")

        # Can update just username
        update = attrib.deserialize(UserUpdateRequest, {"username": "newuser"})
        assert update.username == "newuser"
        assert update.email is None

    def test_strict_validation_mode(self):
        """Test strict validation for production data."""

        @attrib.define
        class Transaction:
            id = attrib.field(int)
            amount = attrib.field(float)
            timestamp = attrib.field(datetime.datetime)

        StrictTransaction = attrib.strict(Transaction, prefix="Strict")

        # Should reject string values in strict mode
        with pytest.raises(DeserializationError):
            attrib.deserialize(
                StrictTransaction,
                {"id": "123", "amount": 99.99, "timestamp": datetime.datetime.now()},
            )

    def test_sortable_entities(self):
        """Test creating sortable entities with ordered decorator."""

        @attrib.define
        class Task:
            priority = attrib.field(int)
            created_at = attrib.field(datetime.datetime)
            title = attrib.field(str)

        SortableTask = attrib.ordered(Task, prefix="Sortable")

        now = datetime.datetime.now()
        task1 = SortableTask(priority=1, created_at=now, title="Low priority")
        task2 = SortableTask(priority=5, created_at=now, title="High priority")
        task3 = SortableTask(priority=3, created_at=now, title="Medium priority")

        tasks = sorted([task3, task1, task2])
        assert tasks[0].priority == 1
        assert tasks[1].priority == 3
        assert tasks[2].priority == 5

    def test_cache_key_dataclasses(self):
        """Test creating hashable dataclasses for cache keys."""

        @attrib.define
        class CacheKey:
            user_id = attrib.field(int)
            resource_type = attrib.field(str)
            resource_id = attrib.field(int)

        HashableCacheKey = attrib.hashable(CacheKey, prefix="Hashable")

        # Can use as dict keys
        cache = {}
        key1 = HashableCacheKey(user_id=1, resource_type="post", resource_id=100)
        key2 = HashableCacheKey(user_id=1, resource_type="post", resource_id=100)

        cache[key1] = "cached_data"
        # Same key should retrieve same data
        assert cache[key2] == "cached_data"

    def test_field_isolation(self):
        """Test that modified dataclasses don't share field state."""

        @attrib.define
        class Original:
            value = attrib.field(str)

        Modified1 = attrib.modify(Original, strict=True, prefix="Modified1")
        Modified2 = attrib.modify(Original, strict=False, prefix="Modified2")

        # Fields should be independent
        assert Modified1.__dataclass_fields__["value"].strict is True
        assert Modified2.__dataclass_fields__["value"].strict is False
        # Original should be unchanged
        assert Original.__dataclass_fields__["value"].strict is False
