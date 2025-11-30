# attrib

`attrib` is a data description and validation library for Python that focuses on being intuitive, deterministic, and transparent. Built on Python's descriptor protocol, it lets you define structured data with type enforcement, validation, and serialization—all without hidden runtime magic.

## Why attrib?

- **Declarative & Intuitive** - Define your data structures the way you think about them
- **Transparent & Predictable** - No hidden behaviors, just descriptors doing their thing
- **Flexible Validation** - Compose validators functionally, apply them where you need them
- **Nested Structures** - Recursive deserialization and validation out of the box
- **Rich Field Types** - DateTime, Email, IP addresses, Enums, and more built-in
- **Detailed Error Handling** - Know exactly what went wrong and where
- **Well-Typed** - Good IDE support with proper type hints
- **Serialization Control** - Choose what gets serialized and how

> **Note**: This library is in early development (v0.0.1a0). APIs may change, but the core concepts are stable. Use it for testing and experimentation.

## Quick Setup

Clone the repository and ensure you have `uv` installed. If not, visit [uv's installation guide](https://docs.astral.sh/uv/getting-started/installation/).

Check available Python versions:

```bash
uv python list
```

Install Python (if needed):

```bash
uv python install 3.10
```

Sync dependencies:

```bash
uv sync --dev
```

Run examples:

```bash
uv run python examples/main.py
```

## Getting Started

### Your First Dataclass

Let's start simple. Here's how you define a dataclass with `attrib`:

```python
import attrib

class Person(attrib.Dataclass):
    name = attrib.field(str)
    age = attrib.field(int)
    email = attrib.field(str, allow_null=True, default=None)
```

That's it. Now you can deserialize data into it:

```python
person = attrib.deserialize(Person, {
    "name": "Alice",
    "age": 30,
    "email": "alice@example.com"
})

print(person.name)  # Alice
print(person.age)   # 30
```

### Two Ways to Define Fields

`attrib` gives you two ways to define fields, depending on what feels right for your use case:

**1. Using `attrib.field()` (recommended for most cases)**

```python
class User(attrib.Dataclass):
    username = attrib.field(str, max_length=50)
    age = attrib.field(int, min_value=0, max_value=120)
```

**2. Using Field classes directly**

```python
class User(attrib.Dataclass):
    username = attrib.String(max_length=50)
    age = attrib.Integer(min_value=0, max_value=120)
```

Both approaches work identically - `attrib.field()` is just a smart factory that picks the right Field class for you. Use direct Field classes when you want to be explicit or need specialized fields like `attrib.Email`, `attrib.IPAddress`, or `attrib.DateTime`.

### Field Validation

Fields validate on assignment, not just during deserialization:

```python
class Product(attrib.Dataclass):
    name = attrib.field(str, min_length=3, max_length=100)
    price = attrib.field(float, min_value=0.0)
    stock = attrib.field(int, min_value=0)

product = Product(name="Widget", price=9.99, stock=100)
product.price = -5.0  # Raises ValidationError!
```

### Default Values and Factories

```python
from datetime import datetime
import random

class Article(attrib.Dataclass):
    title = attrib.field(str)
    content = attrib.field(str)
    published = attrib.field(bool, default=False)
    created_at = attrib.field(datetime, default=datetime.now)
    view_count = attrib.field(int, default=0)
    rating = attrib.field(
        float, 
        default=attrib.Factory(random.random)  # Generate random rating
    )
```

Use `attrib.Factory()` when your default value needs to be computed or when you need to pass arguments to a callable. For simple immutable defaults like `0`, `False`, or `None`, just use them directly.

### Instantiation: Direct vs Deserialize

You can create dataclass instances in two ways:

```python
class User(attrib.Dataclass):
    name = attrib.field(str)
    age = attrib.field(int)
    email = attrib.field(str, allow_null=True, default=None)

# Option 1: Direct instantiation (like regular classes)
user = User(name="Alice", age=30, email="alice@example.com")

# Or pass a dict
user = User({"name": "Alice", "age": 30})

# Or mix both
user = User({"name": "Alice"}, age=30)

# Option 2: Using deserialize (recommended)
user = attrib.deserialize(User, {"name": "Alice", "age": 30})
```

While both work, `deserialize()` is preferred because:

- It gives you more control with `InitConfig` options
- It's more explicit about data transformation
- The intent is clearer when reading code

Use direct instantiation for simple cases and when creating instances programmatically. Use `deserialize()` when loading external data (JSON, APIs, config files, etc.).

### Nested Dataclasses

Nested structures just work:

```python
class Address(attrib.Dataclass):
    street = attrib.field(str)
    city = attrib.field(str)
    country = attrib.field(str, default="USA")

class Company(attrib.Dataclass):
    name = attrib.field(str)
    address = attrib.field(Address)

company_data = {
    "name": "Tech Corp",
    "address": {
        "street": "123 Main St",
        "city": "San Francisco"
    }
}

company = attrib.deserialize(Company, company_data)
print(company.address.city)  # San Francisco
```

### Enums and Choices

```python
import enum

class Status(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"

class Task(attrib.Dataclass):
    title = attrib.field(str)
    status = attrib.field(attrib.Choice[Status], default=Status.PENDING)

task = attrib.deserialize(Task, {"title": "Deploy", "status": "active"})
print(task.status)  # Status.ACTIVE
```

### Lists and Collections

```python
from typing import List

class Team(attrib.Dataclass):
    name = attrib.field(str)
    members = attrib.field(List[Person])
    tags = attrib.field(List[str], default=list)

team_data = {
    "name": "Engineering",
    "members": [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25}
    ]
}

team = attrib.deserialize(Team, team_data)
print(len(team.members))  # 2
```

## Validation Deep Dive

### Built-in Validators

`attrib` comes with a rich set of validators:

```python
import attrib.validators as v

class User(attrib.Dataclass):
    username = attrib.field(
        str,
        validator=v.and_(
            v.min_length(3),
            v.max_length(20),
            v.pattern(r"^[a-zA-Z0-9_]+$")
        )
    )
    age = attrib.field(int, validator=v.range_(18, 65))
    email = attrib.field(str, validator=v.pattern(r".+@.+\..+"))
```

Available validators include:

- `gt()`, `gte()`, `lt()`, `lte()`, `eq()` - Numeric comparisons
- `min_length()`, `max_length()`, `length()` - Length validation
- `range_()` - Value range validation
- `pattern()` - Regex matching
- `instance_of()` - Type checking
- `member_of()` - Membership validation
- `and_()`, `or_()`, `not_()` - Logical composition
- `optional()` - Allow None values
- `iterable()`, `mapping()` - Collection validation

### Custom Validators

Write your own validators easily:

```python
def is_even(value, adapter=None, *args, **kwargs):
    if value % 2 != 0:
        raise ValueError(f"{value} is not even")

class EvenNumbers(attrib.Dataclass):
    value = attrib.field(int, validator=is_even)
```

### Composing Validators

Chain validators together:

```python
import attrib.validators as v

class SecurePassword(attrib.Dataclass):
    password = attrib.field(
        str,
        validator=v.and_(
            v.min_length(8),
            v.pattern(r".*[A-Z].*"),  # Must have uppercase
            v.pattern(r".*[0-9].*"),  # Must have number
        )
    )
```

## Special Field Types

### DateTime Fields

```python
from datetime import datetime, date

class Event(attrib.Dataclass):
    name = attrib.field(str)
    date = attrib.field(date, input_formats=["%Y-%m-%d", "%d/%m/%Y"])
    start_time = attrib.field(datetime)
    created_at = attrib.field(datetime, default=datetime.now)
```

### Network Fields

```python
class Server(attrib.Dataclass):
    hostname = attrib.field(str)
    ip_address = attrib.IPAddress()
    subnet = attrib.IPNetwork()
```

### Email Fields

```python
class Contact(attrib.Dataclass):
    name = attrib.field(str)
    email = attrib.Email()
```

## Serialization

### Basic Serialization

```python
person = Person(name="Alice", age=30, email="alice@example.com")

# To Python dict
data = attrib.serialize(person, fmt="python")

# To JSON-compatible dict
json_data = attrib.serialize(person, fmt="json")
```

### Serialization Aliases

Control field names in serialized output:

```python
class User(attrib.Dataclass):
    internal_id = attrib.field(int, serialization_alias="id")
    user_name = attrib.field(str, serialization_alias="username")

user = User(internal_id=1, user_name="alice")
data = attrib.serialize(user, fmt="python", by_alias=True)
# {"id": 1, "username": "alice"}
```

### Controlling Serialization with Options

Fine-tune what gets serialized:

```python
# Exclude specific fields
student_options = attrib.Options(
    attrib.Option(Student, exclude={"internal_notes"}),
    attrib.Option(Course, recurse=False)  # Don't serialize nested courses
)

serialized = attrib.serialize(student, options=student_options)
```

### Exclude Unset Fields

Only serialize fields that were explicitly set:

```python
person = Person(name="Alice", age=30)  # email not set
data = attrib.serialize(person, exclude_unset=True)
# {"name": "Alice", "age": 30}  # email excluded
```

## Dataclass Configuration

### Class-level Config

```python
class ImmutableUser(attrib.Dataclass, frozen=True, hash=True):
    id = attrib.field(int)
    username = attrib.field(str)

# This will raise FrozenInstanceError
user = ImmutableUser(id=1, username="alice")
user.username = "bob"  # Error!
```

### Meta Configuration

```python
class Student(attrib.Dataclass):
    name = attrib.field(str)
    age = attrib.field(int)
    
    __config__ = attrib.MetaConfig(
        sort=True,      # Sort fields alphabetically
        repr=True,      # Generate __repr__
        frozen=False    # Mutable instances
    )
```

### Inheritance

```python
class Person(attrib.Dataclass):
    name = attrib.field(str)
    age = attrib.field(int)

class Employee(Person):
    employee_id = attrib.field(int)
    department = attrib.field(str)

# Employee has all Person fields plus its own
```

## Deserialization Options

### InitConfig

Control how data is deserialized:

```python
# Use field names instead of aliases
person = attrib.deserialize(
    Person,
    data,
    config=attrib.InitConfig(by_name=True)
)

# Fail fast on first error
person = attrib.deserialize(
    Person,
    data,
    config=attrib.InitConfig(fail_fast=True)
)

# Skip validation (data already validated)
person = attrib.deserialize(
    Person,
    data,
    config=attrib.InitConfig(is_valid=True)
)
```

## Utility Functions

### Copy with Updates

```python
person = Person(name="Alice", age=30)
updated = attrib.copy(person, update={"age": 31})
```

### Evolve (Immutable Update)

This works similarly to `copy` with updates.

```python
updated = attrib.evolve(person, age=31)
```

### Field Introspection

```python
# Get a specific field
field = attrib.get_field(Person, "name")

# Get all fields
fields = attrib.get_fields(Person)

# Check if it's a dataclass
if attrib.is_dataclass(Person):
    print("It's a dataclass!")
```

## Error Handling

`attrib` provides detailed error information to help you debug deserialization and validation issues quickly.

### Exception Types

**`AttribException`** - Base exception for all attrib errors

**`ConfigurationError`** - Raised when there's an issue with dataclass or field configuration

```python
# Example: Using both include and exclude in Options
attrib.Option(MyClass, include={"a"}, exclude={"b"})  # ConfigurationError!
```

**`FieldError`** - Raised for field-specific errors like invalid configuration

```python
# Example: Invalid field type
class Bad(attrib.Dataclass):
    value = attrib.field("not a type")  # Will raise FieldError during build
```

**`ValidationError`** - Raised when field validation fails

```python
class User(attrib.Dataclass):
    age = attrib.field(int, min_value=0)

user = User(age=30)
user.age = -5  # ValidationError: Value must be >= 0
```

**`DeserializationError`** - Raised when deserialization fails (wraps multiple errors)

```python
try:
    person = attrib.deserialize(Person, {
        "name": "A",    # Too short (min_length=3)
        "age": -5       # Negative (min_value=0)
    })
except attrib.DeserializationError as e:
    print(f"Parent: {e.parent_name}")
    print(f"Total errors: {len(e.error_list)}")
    
    for error in e.error_list:
        print(f"\nLocation: {'.'.join(map(str, error.location))}")
        print(f"Message: {error.message}")
        print(f"Code: {error.code}")
        print(f"Expected: {error.expected_type}")
        print(f"Got: {error.input_type}")
```

**`SerializationError`** - Raised when serialization fails

**`FrozenInstanceError`** - Raised when trying to modify a frozen dataclass

```python
class Immutable(attrib.Dataclass, frozen=True):
    value = attrib.field(int)

obj = Immutable(value=10)
obj.value = 20  # FrozenInstanceError!
```

### Error Details

Every error comes with rich context via the `ErrorDetail` named tuple:

```python
error = ErrorDetail(
    location=["user", "address", "zipcode"],  # Path to error
    message="Invalid zipcode format",          # Human-readable message
    expected_type=str,                         # What was expected
    input_type=int,                            # What was received
    code="invalid_format",                     # Machine-readable error code
    context={"pattern": r"\d{5}"},            # Additional context
    origin=ValueError("...")                   # Original exception
)

# Get formatted string
print(error.as_string())
# user.address.zipcode
#   Invalid zipcode format [input_type='int', expected_type='str', code='invalid_format', origin=ValueError]

# Get JSON representation
error_json = error.as_json()
```

### Error Codes

Common error codes you'll encounter:

- `invalid_type` - Value doesn't match expected type
- `coercion_failed` - Failed to convert value to target type
- `validation_failed` - Validator rejected the value
- `required_field` - Required field is missing
- `null_not_allowed` - None provided but `allow_null=False`
- `invalid_format` - String format doesn't match pattern
- `value_too_small` - Number below `min_value`
- `value_too_large` - Number above `max_value`
- `length_too_short` - String/collection below `min_length`
- `length_too_long` - String/collection above `max_length`

### Collecting vs Failing Fast

By default, `attrib` collects all errors. Use `fail_fast=True` to stop at the first error:

```python
# Collect all errors (default)
try:
    data = attrib.deserialize(ComplexClass, bad_data)
except attrib.DeserializationError as e:
    print(f"Found {len(e.error_list)} errors")

# Fail on first error
try:
    data = attrib.deserialize(
        ComplexClass, 
        bad_data,
        config=attrib.InitConfig(fail_fast=True)
    )
except attrib.DeserializationError as e:
    print(f"First error: {e.error_list[0].message}")
```

## Type Adapters

Type adapters are `attrib`'s way of handling any Python type - not just the built-in ones. Think of them as translators that know how to deserialize, validate, and serialize a specific type.

### Why Type Adapters?

When you use `attrib.field(list[int])`, behind the scenes `attrib` creates a `TypeAdapter[list[int]]` that knows how to:

1. **Deserialize**: Convert strings like `["42", "43"]` into an actual list of integers
2. **Validate**: Check that the value is actually an int
3. **Serialize**: Convert the int back to regular and JSON-compatible formats

For custom types or complex generic types, you can create your own adapters.

### Basic Usage

```python
from attrib import TypeAdapter
import attrib.validators as v

# Simple adapter with validation
age_adapter = TypeAdapter(
    int,
    name="Age",
    validator=v.range_(0, 150),
    strict=False  # Allow coercion from strings
)

# Use it
value = age_adapter.adapt("25")  # Deserializes and validates
print(value)  # 25 (int)

# Or validate without deserialization
age_adapter.validate(25)  # OK
age_adapter.validate(200)  # ValidationError!
```

### Complex Types with Adapters

Adapters shine with complex generic types:

```python
from typing import List, Dict, Optional, Tuple
from collections import namedtuple

PersonTuple = namedtuple("PersonTuple", ["name", "age", "friends"])

# Adapter for complex nested structure
adapter = TypeAdapter(
    Tuple[
        List[Optional[PersonTuple]],
        Dict[str, List[int]],
        Optional[str]
    ],
    defer_build=True  # Resolve forward references later
)

# Build it when ready
adapter.build(globalns=globals(), depth=10)

# Now adapt complex data
raw_data = (
    [
        {"name": "Alice", "age": 30, "friends": []},
        {"name": "Bob", "age": 25, "friends": []},
        None
    ],
    {"scores": [10, 20, 30]},
    "metadata"
)

adapted = adapter.adapt(raw_data)
print(type(adapted[0][0]))  # PersonTuple
```

### Using Adapters in Fields

You can pass adapters directly to fields:

```python
# Create a reusable adapter
email_adapter = TypeAdapter(
    str,
    validator=v.pattern(r".+@.+\..+"),
    deserializer=lambda v, f: v.lower().strip()
)

class User(attrib.Dataclass):
    email = attrib.field(email_adapter)
    # Or inline
    verified = attrib.field(
        TypeAdapter(
            bool,
            deserializer=lambda v, f: str(v).lower() in ("1", "true", "yes")
        )
    )
```

### Adapter Methods

**`adapt(value)`** - Full pipeline: deserialize → validate → return

```python
result = adapter.adapt("42")  # Returns int(42)
```

**`deserialize(value)`** - Convert to target type without validation

```python
result = adapter.deserialize("42")  # Returns int(42), no validation
```

**`validate(value)`** - Validate an already-typed value

```python
adapter.validate(42)  # OK
adapter.validate("42")  # ValidationError
```

**`serialize(value, fmt)`** - Convert to output format

```python
json_val = adapter.serialize(42, "json")  
python_val = adapter.serialize(42, "python")  # Usually unchanged
```

**`build(...)`** - Build/resolve the adapter (for forward references)

```python
adapter = TypeAdapter(
    "MyClass",  # Forward reference
    defer_build=True
)
# Later, when MyClass is defined
adapter.build(globalns=globals())
```

### Custom Deserializers & Serializers

```python
from datetime import datetime

def parse_timestamp(value, field):
    """Custom deserializer"""
    if isinstance(value, int):
        return datetime.fromtimestamp(value)
    return datetime.fromisoformat(value)

def format_timestamp(value, field, context):
    """Custom serializer"""
    return int(value.timestamp())

timestamp_adapter = TypeAdapter(
    datetime,
    deserializer=parse_timestamp,
    serializers={
        "json": format_timestamp,
        "python": lambda v, f, ctx: v  # Keep as datetime
    }
)

class Event(attrib.Dataclass):
    created_at = attrib.field(timestamp_adapter)
```

### Strict Mode

Strict mode disables type coercion:

```python
strict_int = TypeAdapter(int, strict=True)
strict_int.adapt(42)    # OK
strict_int.adapt("42")  # ValidationError: expected int, got str

lenient_int = TypeAdapter(int, strict=False)
lenient_int.adapt("42")  # OK, returns 42
```

## Field Configuration Reference

Every field accepts these parameters (from `FieldKwargs`):

### Type and Validation

**`field_type`** - The expected Python type (required)

```python
attrib.field(int)
attrib.field(List[str])
attrib.field(Optional[datetime])
```

**`strict`** (bool, default=`False`) - Only accept exact type, no coercion

```python
value = attrib.field(int, strict=True)  # "42" will fail
```

**`validator`** (callable, optional) - Custom validation function

```python
value = attrib.field(int, validator=v.range_(0, 100))
```

**`allow_null`** (bool, default=`False`) - Allow None values

```python
email = attrib.field(str, allow_null=True)  # Can be None
```

**`required`** (bool, default=`False`) - Must be explicitly provided

```python
id = attrib.field(int, required=True)  # Can't use default
```

### Defaults

**`default`** (value or Factory) - Default value when not provided

```python
active = attrib.field(bool, default=False)
created = attrib.field(datetime, default=datetime.now)
items = attrib.field(list, default=attrib.Factory(list))
```

**`validate_default`** (bool, default=`False`) - Validate the default value

```python
# Useful to catch config errors early
value = attrib.field(int, default=-5, min_value=0, validate_default=True)  # Error!
```

### Serialization & Deserialization

**`alias`** (str, optional) - Alternative name for deserialization

```python
user_id = attrib.field(int, alias="userId")
# {"userId": 123} deserializes to user_id=123
```

**`serialization_alias`** (str, optional) - Alternative name for serialization

```python
internal_id = attrib.field(int, serialization_alias="id")
# Serializes as {"id": 123} instead of {"internal_id": 123}
```

**`deserializer`** (callable, optional) - Custom deserialization function

```python
def parse_date(value, field):
    return datetime.strptime(value, "%Y-%m-%d")

date = attrib.field(datetime, deserializer=parse_date)
```

**`serializers`** (dict, optional) - Format-specific serializers

```python
timestamp = attrib.field(
    datetime,
    serializers={
        "json": lambda v, f, ctx: v.isoformat(),
        "python": lambda v, f, ctx: v
    }
)
```

**`always_coerce`** (bool, default=`False`) - Always run deserializer

```python
# Even if value is already correct type
lower_str = attrib.field(
    str, 
    deserializer=lambda v, f: v.lower(),
    always_coerce=True  # Always lowercase
)
```

**`check_coerced`** (bool, default=`False`) - Verify deserializer output type

```python
# Safety check for custom deserializers
value = attrib.field(int, deserializer=my_parser, check_coerced=True)
```

**`skip_validator`** (bool, default=`False`) - Skip validation after deserialization

```python
# Use when you trust the deserializer output
value = attrib.field(int, skip_validator=True)
```

### Behavior Control

**`fail_fast`** (bool, default=`False`) - Stop on first validation error

```python
strict_field = attrib.field(int, validator=v.range_(0, 100), fail_fast=True)
```

**`init`** (bool, default=`True`) - Include in `__init__` parameters

```python
computed = attrib.field(int, init=False)  # Not in __init__
```

**`repr`** (bool, default=`True`) - Include in `__repr__` output

```python
password = attrib.field(str, repr=False)  # Hidden in repr
```

**`hash`** (bool, default=`True`) - Include in `__hash__` calculation

```python
id = attrib.field(int, hash=True)
metadata = attrib.field(dict, hash=False)  # Not hashable anyway
```

**`eq`** (bool, default=`True`) - Include in equality comparison

```python
id = attrib.field(int, eq=True)
timestamp = attrib.field(datetime, eq=False)  # Ignored in ==
```

**`order`** (int >= 0, optional) - Ordering priority for comparisons

```python
priority = attrib.field(int, order=0)  # Compared first
name = attrib.field(str, order=1)      # Compared second
```

### Example: Kitchen Sink

```python
class Article(attrib.Dataclass):
    # Minimal
    title = attrib.field(str)
    
    # With constraints
    word_count = attrib.field(int, min_value=0, max_value=100000)
    
    # With validation
    slug = attrib.field(
        str,
        validator=v.pattern(r"^[a-z0-9-]+$"),
        deserializer=lambda v, f: v.lower().replace(" ", "-")
    )
    
    # With defaults
    published = attrib.field(bool, default=False)
    views = attrib.field(int, default=0)
    
    # With aliases
    author_id = attrib.field(
        int,
        alias="authorId",
        serialization_alias="author"
    )
    
    # Complex
    tags = attrib.field(
        List[str],
        default=attrib.Factory(list),
        validator=v.and_(
            v.min_length(1),
            v.max_length(10)
        )
    )
    
    # Internal use only
    internal_notes = attrib.field(
        str,
        allow_null=True,
        default=None,
        repr=False,
        eq=False,
        hash=False
    )
```

## Dataclass Configuration Reference

Configure dataclass behavior with class parameters or `MetaConfig`:

### Class Parameters (Inline)

```python
class MyClass(attrib.Dataclass, frozen=True, hash=True, repr=True):
    pass
```

### MetaConfig (Explicit)

```python
class MyClass(attrib.Dataclass):
    field1 = attrib.field(str)
    
    __config__ = attrib.MetaConfig(
        frozen=True,
        hash=True,
        repr=True
    )
```

### Available Options

**`frozen`** (bool, default=`False`) - Make instances immutable

```python
class ImmutableUser(attrib.Dataclass, frozen=True):
    id = attrib.field(int)

user = ImmutableUser(id=1)
user.id = 2  # FrozenInstanceError!
```

**`slots`** (bool or tuple, default=`False`) - Use `__slots__` for memory efficiency

```python
# Boolean: automatic slots
class Compact(attrib.Dataclass, slots=True):
    pass

# Tuple: add custom slots
class Custom(attrib.Dataclass, slots=("_cache", "_state")):
    pass
```

**`repr`** (bool, default=`False`) - Generate `__repr__` method

```python
class User(attrib.Dataclass, repr=True):
    name = attrib.field(str)
    age = attrib.field(int)

print(User(name="Alice", age=30))
# User(name='Alice', age=30)
```

**`str`** (bool, default=`False`) - Generate `__str__` method

```python
class User(attrib.Dataclass, str=True):
    name = attrib.field(str)
```

**`hash`** (bool, default=`False`) - Generate `__hash__` method

```python
# Usually paired with frozen=True
class HashableUser(attrib.Dataclass, frozen=True, hash=True):
    id = attrib.field(int)

users = {HashableUser(id=1), HashableUser(id=2)}  # Can use in sets
```

**`eq`** (bool, default=`True`) - Generate `__eq__` method

```python
class User(attrib.Dataclass, eq=True):
    id = attrib.field(int)

User(id=1) == User(id=1)  # True
```

**`order`** (bool, default=`False`) - Generate comparison methods (`__lt__`, `__le__`, etc.)

```python
class Priority(attrib.Dataclass, order=True):
    level = attrib.field(int, order=0)
    name = attrib.field(str, order=1)

Priority(level=1, name="Low") < Priority(level=2, name="High")  # True
```

**`sort`** (bool or callable, default=`False`) - Sort fields

```python
# Sort alphabetically
class Sorted(attrib.Dataclass, sort=True):
    pass

# Custom sort key
class CustomSort(attrib.Dataclass, sort=lambda item: item[1].order):
    pass
```

**`getitem`** (bool, default=`False`) - Enable `__getitem__` access

```python
class User(attrib.Dataclass, getitem=True):
    name = attrib.field(str)

user = User(name="Alice")
print(user["name"])  # Alice
```

**`setitem`** (bool, default=`False`) - Enable `__setitem__` assignment

```python
class User(attrib.Dataclass, setitem=True):
    name = attrib.field(str)

user = User(name="Alice")
user["name"] = "Bob"
```

**`pickleable`** (bool, default=`True`) - Add pickle support methods

```python
import pickle

class Pickleable(attrib.Dataclass, pickleable=True):
    data = attrib.field(dict)

obj = Pickleable(data={"key": "value"})
pickled = pickle.dumps(obj)
restored = pickle.loads(pickled)
```

## Optional External Field Types

Some specialized fields require external libraries. Install them as needed:

### Phone Numbers (requires `phonenumbers`)

```bash
pip install attrib[phonenumbers]
```

```python
from phonenumbers import PhoneNumberFormat

class Contact(attrib.Dataclass):
    # Phone number object
    mobile = attrib.PhoneNumber(
        output_format=PhoneNumberFormat.E164  # +1234567890
    )
    
    # Or as formatted string
    landline = attrib.PhoneNumberString(
        output_format=PhoneNumberFormat.INTERNATIONAL  # +1 234-567-8900
    )

contact = attrib.deserialize(Contact, {
    "mobile": "+1234567890",
    "landline": "123-456-7890"
})
```

Available formats:

- `PhoneNumberFormat.E164` - `+1234567890`
- `PhoneNumberFormat.INTERNATIONAL` - `+1 234-567-8900`
- `PhoneNumberFormat.NATIONAL` - `(234) 567-8900`
- `PhoneNumberFormat.RFC3966` - `tel:+1-234-567-8900`

### Physical Quantities (requires `quantities`)

```bash
pip install attrib[quantities]
```

```python
import quantities as pq

class Measurement(attrib.Dataclass):
    # Physical quantity with unit
    distance = attrib.Quantity(unit="meter")
    weight = attrib.Quantity(unit=pq.kilogram)
    ratio = attrib.Quantity()  # Dimensionless

# Multiple input formats
measurement = attrib.deserialize(Measurement, {
    "distance": "100 meter",      # String with unit
    "weight": [75, "kg"],          # List [magnitude, unit]
    "ratio": 1.5                   # Number (dimensionless)
})

# Or with quantities directly
measurement = Measurement(
    distance=100 * pq.meter,
    weight=pq.Quantity(75, "kg"),
    ratio=1.5
)

print(measurement.distance)  # 100.0 m
print(measurement.weight.rescale("g"))  # 75000.0 g
```

Input formats:

- String: `"10 meter"`, `"10 m"`
- Quantity object: `10 * pq.meter`
- List/tuple: `[10, "meter"]`, `["10", "m"]`
- Number: `10` (uses field's default unit or dimensionless)

## Examples

Check out the [examples](/examples) directory for real-world usage patterns:

- `attrib_.py` - Complete example with nested structures
- `dataclass_.py` - Standard library dataclasses comparison
- `attrs_.py` - attrs library comparison
- `adapter.py` - Custom type adapter example

## Contributing

This library is in active development, and contributions are welcome! Whether it's:

- Bug reports and fixes
- New field types or validators
- Documentation improvements
- Performance optimizations
- Feature suggestions

Feel free to open an issue or submit a pull request.

## Requirements

- Python 3.8+
- `typing-extensions`
- `annotated-types`
