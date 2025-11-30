"""Tests for validators module."""

import re
import pytest

from attrib import validators
from attrib.exceptions import ValidationError


class TestNumberValidators:
    """Test number comparison validators."""

    def test_gt_validator(self):
        """Test gt (greater than) validator."""
        validator = validators.gt(5)
        validator(10, None)  # Should pass

        with pytest.raises(ValidationError):
            validator(3, None)

    def test_gte_validator(self):
        """Test gte (greater than or equal) validator."""
        validator = validators.gte(5)
        validator(5, None)  # Should pass
        validator(10, None)  # Should pass

        with pytest.raises(ValidationError):
            validator(3, None)

    def test_lt_validator(self):
        """Test lt (less than) validator."""
        validator = validators.lt(10)
        validator(5, None)  # Should pass

        with pytest.raises(ValidationError):
            validator(15, None)

    def test_lte_validator(self):
        """Test lte (less than or equal) validator."""
        validator = validators.lte(10)
        validator(10, None)  # Should pass
        validator(5, None)  # Should pass

        with pytest.raises(ValidationError):
            validator(15, None)

    def test_eq_validator(self):
        """Test eq (equal) validator."""
        validator = validators.eq(5)
        validator(5, None)  # Should pass

        with pytest.raises(ValidationError):
            validator(3, None)

    def test_range_validator(self):
        """Test range_ validator."""
        validator = validators.range_(1, 10)
        validator(5, None)  # Should pass
        validator(1, None)  # Should pass
        validator(10, None)  # Should pass

        with pytest.raises(ValidationError):
            validator(0, None)

        with pytest.raises(ValidationError):
            validator(11, None)


class TestLengthValidators:
    """Test length validators."""

    def test_min_length_validator(self):
        """Test min_length validator."""
        validator = validators.min_length(3)
        validator("hello", None)  # Should pass
        validator([1, 2, 3], None)  # Should pass

        with pytest.raises(ValidationError):
            validator("hi", None)

    def test_max_length_validator(self):
        """Test max_length validator."""
        validator = validators.max_length(5)
        validator("hello", None)  # Should pass
        validator([1, 2], None)  # Should pass

        with pytest.raises(ValidationError):
            validator("too long", None)

    def test_length_validator(self):
        """Test length (exact) validator."""
        validator = validators.length(5)
        validator("hello", None)  # Should pass
        validator([1, 2, 3, 4, 5], None)  # Should pass

        with pytest.raises(ValidationError):
            validator("hi", None)


class TestTypeValidators:
    """Test type validators."""

    def test_instance_of_single_type(self):
        """Test instance_of with single type."""
        validator = validators.instance_of(int)
        validator(5, None)  # Should pass

        with pytest.raises(ValidationError):
            validator("not an int", None)

    def test_instance_of_multiple_types(self):
        """Test instance_of with multiple types."""
        validator = validators.instance_of((int, str))
        validator(5, None)  # Should pass
        validator("hello", None)  # Should pass

        with pytest.raises(ValidationError):
            validator([1, 2], None)


class TestCollectionValidators:
    """Test collection validators."""

    def test_member_of_validator(self):
        """Test member_of validator."""
        validator = validators.member_of([1, 2, 3, 4, 5])
        validator(3, None)  # Should pass

        with pytest.raises(ValidationError):
            validator(10, None)

    def test_iterable_validator(self):
        """Test iterable validator with child validator."""
        validator = validators.iterable(validators.instance_of(int))
        validator([1, 2, 3], None)  # Should pass

        with pytest.raises(ValidationError):
            validator([1, "two", 3], None)

    def test_iterable_validator_not_iterable(self):
        """Test iterable validator with non-iterable value."""
        validator = validators.iterable(validators.instance_of(int))

        with pytest.raises(ValidationError):
            validator(42, None)

    def test_iterable_validator_deep(self):
        """Test iterable validator with deep=True."""
        validator = validators.iterable(validators.instance_of(int), deep=True)
        validator([[1, 2], [3, 4]], None)  # Should pass nested

    def test_mapping_validator(self):
        """Test mapping validator with key and value validators."""
        validator = validators.mapping(
            key_validator=validators.instance_of(str),
            value_validator=validators.instance_of(int),
        )
        validator({"a": 1, "b": 2}, None)  # Should pass

        with pytest.raises(ValidationError):
            validator({"a": 1, "b": "not int"}, None)

    def test_mapping_validator_key_only(self):
        """Test mapping validator with only key validator."""
        validator = validators.mapping(
            key_validator=validators.instance_of(str), value_validator=None
        )
        validator({"a": 1, "b": "anything"}, None)  # Should pass

        with pytest.raises(ValidationError):
            validator({1: "value"}, None)

    def test_mapping_validator_value_only(self):
        """Test mapping validator with only value validator."""
        validator = validators.mapping(
            key_validator=None, value_validator=validators.instance_of(int)
        )
        validator({"a": 1, 2: 3}, None)  # Should pass (any key type)

        with pytest.raises(ValidationError):
            validator({"a": "not int"}, None)

    def test_mapping_validator_not_mapping(self):
        """Test mapping validator with non-mapping value."""
        validator = validators.mapping(
            key_validator=None, value_validator=validators.instance_of(int)
        )

        with pytest.raises(ValidationError):
            validator([1, 2, 3], None)

    def test_mapping_validator_deep(self):
        """Test mapping validator with deep=True."""
        validator = validators.mapping(
            key_validator=validators.instance_of(str),
            value_validator=validators.instance_of(int),
            deep=True,
        )
        # Nested mappings with int leaf values
        validator({"a": {"x": 1, "y": 2}, "b": {"z": 3}}, None)  # Should pass


class TestStringValidators:
    """Test string validators."""

    def test_pattern_with_string(self):
        """Test pattern validator with string pattern."""
        validator = validators.pattern(r"^\d{3}-\d{4}$")
        validator("123-4567", None)  # Should pass

        with pytest.raises(ValidationError):
            validator("invalid", None)

    def test_pattern_with_compiled_regex(self):
        """Test pattern validator with compiled regex."""
        regex = re.compile(r"^\d{3}-\d{4}$")
        validator = validators.pattern(regex)
        validator("123-4567", None)  # Should pass

        with pytest.raises(ValidationError):
            validator("invalid", None)


class TestOptionalValidator:
    """Test optional validator."""

    def test_optional_with_none(self):
        """Test optional validator allows None."""
        validator = validators.optional(validators.instance_of(int))
        validator(None, None)  # Should pass

    def test_optional_with_valid_value(self):
        """Test optional validator with valid non-None value."""
        validator = validators.optional(validators.gt(5))
        validator(10, None)  # Should pass

    def test_optional_with_invalid_value(self):
        """Test optional validator with invalid non-None value."""
        validator = validators.optional(validators.gt(5))

        with pytest.raises(ValidationError):
            validator(3, None)


class TestPipelineValidator:
    """Test pipe validator (combines validators with AND logic)."""

    def test_pipe_all_pass(self):
        """Test pipe with all validators passing."""
        validator = validators.pipe(
            validators.instance_of(int), validators.gt(5), validators.lt(20)
        )
        validator(10, None)  # Should pass

    def test_pipe_fail_first(self):
        """Test pipe failing on first validator."""
        validator = validators.pipe(
            validators.instance_of(str), validators.min_length(5)
        )
        with pytest.raises(ValidationError):
            validator(123, None)

    def test_pipe_fail_later(self):
        """Test pipe failing on later validator."""
        validator = validators.pipe(
            validators.instance_of(str), validators.min_length(5)
        )

        with pytest.raises(ValidationError):
            validator("hi", None)


class TestOrValidator:
    """Test or_ validator (combines validators with OR logic)."""

    def test_or_pass_first(self):
        """Test or_ passing on first validator."""
        validator = validators.or_(
            validators.instance_of(int), validators.instance_of(str)
        )
        validator(123, None)  # Should pass

    def test_or_pass_second(self):
        """Test or_ passing on second validator."""
        validator = validators.or_(
            validators.instance_of(int), validators.instance_of(str)
        )
        validator("hello", None)  # Should pass

    def test_or_fail_all(self):
        """Test or_ failing on all validators."""
        validator = validators.or_(
            validators.instance_of(int), validators.instance_of(str)
        )

        with pytest.raises(ValidationError):
            validator([1, 2, 3], None)


class TestNotValidator:
    """Test not_ validator (negates a validator)."""

    def test_not_validator_pass(self):
        """Test not_ validator with passing value."""
        validator = validators.not_(validators.instance_of(int))
        validator("hello", None)  # Should pass

    def test_not_validator_fail(self):
        """Test not_ validator with failing value."""
        validator = validators.not_(validators.instance_of(int))

        with pytest.raises(ValidationError):
            validator(123, None)


class TestIsValidator:
    """Test is_ validator (identity check)."""

    def test_is_validator_pass(self):
        """Test is_ validator with same object."""
        sentinel = object()
        validator = validators.is_(sentinel)
        validator(sentinel, None)  # Should pass

    def test_is_validator_fail(self):
        """Test is_ validator with different object."""
        sentinel = object()
        validator = validators.is_(sentinel)

        with pytest.raises(ValidationError):
            validator(object(), None)


class TestSubclassValidator:
    """Test subclass_of validator."""

    def test_subclass_of_pass(self):
        """Test subclass_of with valid subclass."""
        validator = validators.subclass_of(Exception)
        validator(ValueError, None)  # Should pass

    def test_subclass_of_fail(self):
        """Test subclass_of with non-subclass."""
        validator = validators.subclass_of(Exception)

        with pytest.raises(ValidationError):
            validator(str, None)
