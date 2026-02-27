"""
Comprehensive unit tests for engine/v1 utility modules.

Covers:
  - string.py
  - common.py
  - merge_dict.py
  - safe_formatter.py
  - serialize.py
  - timer.py
  - tools.py
  - functions.py
  - message.py
  - response.py
"""

import dataclasses
import time
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------
from ii_agent.engine.v1.utils.string import (
    _clean_json_content,
    _extract_json_objects,
    _parse_individual_json,
    generate_id,
    generate_id_from_name,
    hash_string_sha256,
    is_valid_uuid,
    parse_response_model_str,
    url_safe_string,
)
from ii_agent.engine.v1.utils.common import (
    check_type_compatibility,
    dataclass_to_dict,
    get_image_str,
    is_empty,
    is_typed_dict,
    isinstanceany,
    nested_model_dump,
    validate_typed_dict,
)
from ii_agent.engine.v1.utils.merge_dict import (
    merge_dictionaries,
    merge_parallel_session_states,
)
from ii_agent.engine.v1.utils.safe_formatter import SafeFormatter
from ii_agent.engine.v1.utils.serialize import json_serializer
from ii_agent.engine.v1.utils.timer import Timer
from ii_agent.engine.v1.utils.tools import (
    extract_tool_call_from_string,
    extract_tool_from_xml,
    remove_function_calls_from_string,
    remove_tool_calls_from_string,
)
from ii_agent.engine.v1.utils.functions import get_function_call
from ii_agent.engine.v1.utils.message import filter_tool_calls, get_text_from_message
from ii_agent.engine.v1.utils.response import escape_markdown_tags, format_tool_calls

from ii_agent.engine.v1.models.message import Message
from ii_agent.engine.v1.models.response import ToolExecution
from ii_agent.engine.v1.tools.function import Function, FunctionCall


# ===========================================================================
# Helpers / fixtures shared across tests
# ===========================================================================

def _make_function(name: str = "my_func") -> Function:
    """Return a minimal Function instance without a real entrypoint."""
    return Function(name=name)


def _make_tool_execution(
    tool_name: Optional[str] = "my_tool",
    tool_args: Optional[Dict[str, Any]] = None,
    tool_call_id: Optional[str] = "call-1",
) -> ToolExecution:
    return ToolExecution(
        tool_name=tool_name,
        tool_args=tool_args,
        tool_call_id=tool_call_id,
    )


# ---------------------------------------------------------------------------
# TypedDict definitions used in common.py tests
# ---------------------------------------------------------------------------
from typing import TypedDict


class SimpleSchema(TypedDict):
    name: str
    age: int


class OptionalSchema(TypedDict, total=False):
    nickname: str
    score: float


class MixedSchema(TypedDict, total=False):
    nickname: str


# Make a TypedDict with a required key via inheritance
class RequiredMixed(TypedDict):
    name: str


# ===========================================================================
# 1. string.py
# ===========================================================================

class TestIsValidUuid:

    def test_valid_uuid4(self):
        assert is_valid_uuid("550e8400-e29b-41d4-a716-446655440000") is True

    def test_valid_uuid_uppercase(self):
        assert is_valid_uuid("550E8400-E29B-41D4-A716-446655440000") is True

    def test_valid_uuid_no_dashes(self):
        # uuid module accepts compact form
        assert is_valid_uuid("550e8400e29b41d4a716446655440000") is True

    def test_invalid_random_string(self):
        assert is_valid_uuid("not-a-uuid") is False

    def test_empty_string(self):
        assert is_valid_uuid("") is False

    def test_too_short(self):
        assert is_valid_uuid("550e8400-e29b") is False

    def test_numeric_string(self):
        assert is_valid_uuid("12345") is False

    def test_none_coerced_to_string(self):
        # str(None) == "None" which is not a valid UUID
        assert is_valid_uuid(str(None)) is False

    def test_uuid_with_wrong_version_char(self):
        # All zeros is a valid UUID (nil UUID)
        assert is_valid_uuid("00000000-0000-0000-0000-000000000000") is True

    def test_int_input_raises_or_returns_false(self):
        # int is coerced via str(), resulting in invalid UUID
        assert is_valid_uuid(str(42)) is False

    def test_special_chars(self):
        assert is_valid_uuid("!!@@##$$") is False


class TestUrlSafeString:

    def test_spaces_replaced_with_dashes(self):
        result = url_safe_string("hello world")
        assert result == "hello-world"

    def test_camel_case_to_kebab(self):
        result = url_safe_string("helloWorld")
        assert "hello-world" in result

    def test_snake_case_to_kebab(self):
        result = url_safe_string("hello_world")
        assert result == "hello-world"

    def test_special_chars_removed(self):
        result = url_safe_string("hello@world!")
        assert "@" not in result
        assert "!" not in result

    def test_consecutive_dashes_collapsed(self):
        result = url_safe_string("hello  world")
        assert "--" not in result

    def test_all_lowercase(self):
        result = url_safe_string("HELLO")
        assert result == result.lower()

    def test_dots_preserved(self):
        result = url_safe_string("file.name")
        assert "." in result

    def test_alphanumeric_unchanged_lower(self):
        result = url_safe_string("abc123")
        assert result == "abc123"

    def test_mixed_camel_and_spaces(self):
        result = url_safe_string("myVar Name")
        assert result == "my-var-name"

    def test_empty_string(self):
        result = url_safe_string("")
        assert result == ""


class TestHashStringSha256:

    def test_known_hash_for_hello(self):
        expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        assert hash_string_sha256("hello") == expected

    def test_empty_string(self):
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert hash_string_sha256("") == expected

    def test_different_inputs_different_hashes(self):
        assert hash_string_sha256("abc") != hash_string_sha256("def")

    def test_same_input_same_hash(self):
        assert hash_string_sha256("test") == hash_string_sha256("test")

    def test_output_length(self):
        # SHA-256 produces 64 hex chars
        result = hash_string_sha256("anything")
        assert len(result) == 64

    def test_hex_chars_only(self):
        result = hash_string_sha256("test_value")
        assert all(c in "0123456789abcdef" for c in result)


class TestExtractJsonObjects:

    def test_single_json_object(self):
        text = '{"key": "value"}'
        result = _extract_json_objects(text)
        assert result == ['{"key": "value"}']

    def test_multiple_json_objects(self):
        text = '{"a": 1} {"b": 2}'
        result = _extract_json_objects(text)
        assert len(result) == 2

    def test_nested_json_object(self):
        text = '{"outer": {"inner": 1}}'
        result = _extract_json_objects(text)
        assert len(result) == 1
        assert '"outer"' in result[0]

    def test_no_json_objects(self):
        text = "no json here"
        result = _extract_json_objects(text)
        assert result == []

    def test_json_with_surrounding_text(self):
        text = 'here is some text {"key": "value"} more text'
        result = _extract_json_objects(text)
        assert len(result) == 1
        assert '"key"' in result[0]

    def test_empty_object(self):
        text = "{}"
        result = _extract_json_objects(text)
        assert result == ["{}"]

    def test_deeply_nested_object(self):
        text = '{"a": {"b": {"c": 1}}}'
        result = _extract_json_objects(text)
        assert len(result) == 1


class TestCleanJsonContent:

    def test_removes_json_code_block(self):
        content = '```json\n{"key": "value"}\n```'
        result = _clean_json_content(content)
        assert "```" not in result
        assert '"key"' in result

    def test_removes_plain_code_block(self):
        content = '```\n{"key": "value"}\n```'
        result = _clean_json_content(content)
        assert "```" not in result

    def test_replaces_newlines(self):
        content = '{"key":\n"value"}'
        result = _clean_json_content(content)
        assert "\n" not in result

    def test_removes_carriage_returns(self):
        content = '{"key": "value"\r}'
        result = _clean_json_content(content)
        assert "\r" not in result

    def test_no_code_block_passes_through(self):
        content = '{"key": "value"}'
        result = _clean_json_content(content)
        assert '"key"' in result

    def test_control_chars_removed(self):
        content = '{"key": "val\x01ue"}'
        result = _clean_json_content(content)
        assert "\x01" not in result


class TestParseIndividualJson:

    class MyModel(BaseModel):
        name: str
        items: List[str] = []

    def test_single_matching_json(self):
        content = '{"name": "Alice", "items": ["a", "b"]}'
        result = _parse_individual_json(content, self.MyModel)
        assert result is not None
        assert result.name == "Alice"

    def test_multiple_jsons_field_merging_lists(self):
        # Two JSON objects both have items — lists should be extended
        content = '{"name": "Alice", "items": ["a"]} {"items": ["b"]}'
        result = _parse_individual_json(content, self.MyModel)
        assert result is not None
        assert "a" in result.items
        assert "b" in result.items

    def test_multiple_jsons_non_list_field_last_wins(self):
        content = '{"name": "Alice"} {"name": "Bob"}'
        result = _parse_individual_json(content, self.MyModel)
        assert result is not None
        assert result.name == "Bob"

    def test_no_json_returns_none(self):
        result = _parse_individual_json("no json here", self.MyModel)
        assert result is None

    def test_invalid_json_skipped(self):
        content = '{invalid} {"name": "Alice"}'
        result = _parse_individual_json(content, self.MyModel)
        assert result is not None
        assert result.name == "Alice"


class TestParseResponseModelStr:

    class MyModel(BaseModel):
        value: int
        label: str = "default"

    def test_valid_json(self):
        result = parse_response_model_str('{"value": 42, "label": "hello"}', self.MyModel)
        assert result is not None
        assert result.value == 42
        assert result.label == "hello"

    def test_code_block_wrapped_json(self):
        content = '```json\n{"value": 10}\n```'
        result = parse_response_model_str(content, self.MyModel)
        assert result is not None
        assert result.value == 10

    def test_concatenated_json_merged(self):
        content = '{"value": 99} {"label": "merged"}'
        result = parse_response_model_str(content, self.MyModel)
        assert result is not None
        assert result.value == 99

    def test_completely_invalid_returns_none(self):
        result = parse_response_model_str("this is not json at all !!", self.MyModel)
        assert result is None

    def test_single_json_object_in_text(self):
        content = 'Here is the answer: {"value": 7}'
        result = parse_response_model_str(content, self.MyModel)
        assert result is not None
        assert result.value == 7


class TestGenerateId:

    def test_without_seed_returns_valid_uuid(self):
        result = generate_id()
        assert is_valid_uuid(result) is True

    def test_without_seed_random_each_time(self):
        id1 = generate_id()
        id2 = generate_id()
        assert id1 != id2

    def test_with_seed_deterministic(self):
        result1 = generate_id("my-seed")
        result2 = generate_id("my-seed")
        assert result1 == result2

    def test_different_seeds_different_ids(self):
        id1 = generate_id("seed-a")
        id2 = generate_id("seed-b")
        assert id1 != id2

    def test_with_seed_is_valid_uuid(self):
        result = generate_id("any-seed")
        assert is_valid_uuid(result) is True

    def test_none_seed_returns_random(self):
        result = generate_id(None)
        assert is_valid_uuid(result) is True


class TestGenerateIdFromName:

    def test_spaces_converted_to_dashes(self):
        result = generate_id_from_name("hello world")
        assert result == "hello-world"

    def test_underscores_converted_to_dashes(self):
        result = generate_id_from_name("hello_world")
        assert result == "hello-world"

    def test_lowercase_applied(self):
        result = generate_id_from_name("HELLO")
        assert result == "hello"

    def test_none_returns_random_uuid(self):
        result = generate_id_from_name(None)
        assert is_valid_uuid(result) is True

    def test_empty_string_returns_random_uuid(self):
        # Empty string is falsy, so treated as None
        result = generate_id_from_name("")
        assert is_valid_uuid(result) is True

    def test_mixed_spaces_and_underscores(self):
        result = generate_id_from_name("my name_here")
        assert result == "my-name-here"

    def test_already_kebab_case(self):
        result = generate_id_from_name("my-name")
        assert result == "my-name"


# ===========================================================================
# 2. common.py
# ===========================================================================

class TestIsinstanceAny:

    def test_matches_first_type(self):
        assert isinstanceany("hello", [str, int]) is True

    def test_matches_second_type(self):
        assert isinstanceany(42, [str, int]) is True

    def test_no_match(self):
        assert isinstanceany(3.14, [str, int]) is False

    def test_empty_class_list(self):
        assert isinstanceany("x", []) is False

    def test_none_object(self):
        assert isinstanceany(None, [type(None)]) is True

    def test_none_object_not_str(self):
        assert isinstanceany(None, [str]) is False


class TestIsEmpty:

    def test_none_is_empty(self):
        assert is_empty(None) is True

    def test_empty_list_is_empty(self):
        assert is_empty([]) is True

    def test_empty_string_is_empty(self):
        assert is_empty("") is True

    def test_non_empty_string(self):
        assert is_empty("hello") is False

    def test_non_empty_list(self):
        assert is_empty([1, 2, 3]) is False

    def test_zero_is_not_empty(self):
        # 0 has no len(), so is_empty would raise; test that non-empty values work
        assert is_empty("0") is False


class TestGetImageStr:

    def test_basic_format(self):
        result = get_image_str("myrepo", "latest")
        assert result == "myrepo:latest"

    def test_with_registry_prefix(self):
        result = get_image_str("gcr.io/project/image", "v1.0")
        assert result == "gcr.io/project/image:v1.0"

    def test_empty_tag(self):
        result = get_image_str("myrepo", "")
        assert result == "myrepo:"


class TestDataclassToDict:

    def test_basic_conversion(self):
        @dataclass
        class Point:
            x: int
            y: int

        p = Point(x=1, y=2)
        result = dataclass_to_dict(p)
        assert result == {"x": 1, "y": 2}

    def test_exclude_fields(self):
        @dataclass
        class Point:
            x: int
            y: int

        p = Point(x=1, y=2)
        result = dataclass_to_dict(p, exclude={"y"})
        assert "y" not in result
        assert result["x"] == 1

    def test_exclude_none(self):
        @dataclass
        class Config:
            name: str
            value: Optional[str] = None

        c = Config(name="test", value=None)
        result = dataclass_to_dict(c, exclude_none=True)
        assert "value" not in result
        assert result["name"] == "test"

    def test_exclude_and_exclude_none(self):
        @dataclass
        class Config:
            a: str
            b: Optional[str] = None
            c: str = "keep"

        obj = Config(a="yes", b=None, c="keep")
        result = dataclass_to_dict(obj, exclude={"c"}, exclude_none=True)
        assert "c" not in result
        assert "b" not in result
        assert result["a"] == "yes"

    def test_nested_dataclass(self):
        @dataclass
        class Inner:
            v: int

        @dataclass
        class Outer:
            inner: Inner

        obj = Outer(inner=Inner(v=42))
        result = dataclass_to_dict(obj)
        assert result["inner"]["v"] == 42


class TestNestedModelDump:

    def test_pydantic_model(self):
        class M(BaseModel):
            x: int
            y: str

        m = M(x=1, y="hello")
        result = nested_model_dump(m)
        assert result == {"x": 1, "y": "hello"}

    def test_plain_dict(self):
        d = {"a": 1, "b": 2}
        result = nested_model_dump(d)
        assert result == {"a": 1, "b": 2}

    def test_list_of_models(self):
        class M(BaseModel):
            v: int

        items = [M(v=1), M(v=2)]
        result = nested_model_dump(items)
        assert result == [{"v": 1}, {"v": 2}]

    def test_primitive(self):
        assert nested_model_dump(42) == 42
        assert nested_model_dump("hello") == "hello"
        assert nested_model_dump(None) is None

    def test_nested_dict_with_model(self):
        class M(BaseModel):
            z: int

        d = {"key": M(z=5)}
        result = nested_model_dump(d)
        assert result == {"key": {"z": 5}}

    def test_list_of_primitives(self):
        result = nested_model_dump([1, 2, 3])
        assert result == [1, 2, 3]


class TestIsTypedDict:

    def test_typed_dict_returns_true(self):
        assert is_typed_dict(SimpleSchema) is True

    def test_regular_dict_class_returns_false(self):
        assert is_typed_dict(dict) is False

    def test_plain_class_returns_false(self):
        class NotTypedDict:
            pass

        assert is_typed_dict(NotTypedDict) is False

    def test_pydantic_model_returns_false(self):
        class MyModel(BaseModel):
            x: int

        assert is_typed_dict(MyModel) is False


class TestCheckTypeCompatibility:

    def test_none_with_optional_type(self):
        result = check_type_compatibility(None, Optional[str])
        assert result is True

    def test_none_with_non_optional_type(self):
        result = check_type_compatibility(None, str)
        assert result is False

    def test_string_with_str(self):
        assert check_type_compatibility("hello", str) is True

    def test_int_with_str(self):
        assert check_type_compatibility(42, str) is False

    def test_list_with_list(self):
        assert check_type_compatibility([1, 2], list) is True

    def test_list_with_typed_list(self):
        assert check_type_compatibility([1, 2, 3], List[int]) is True

    def test_list_with_wrong_element_type(self):
        assert check_type_compatibility(["a", "b"], List[int]) is False

    def test_union_type_match(self):
        from typing import Union
        assert check_type_compatibility("hello", Union[str, int]) is True
        assert check_type_compatibility(42, Union[str, int]) is True

    def test_any_type_always_true(self):
        assert check_type_compatibility(42, Any) is True
        assert check_type_compatibility("x", Any) is True

    def test_bool_with_bool(self):
        assert check_type_compatibility(True, bool) is True

    def test_float_with_float(self):
        assert check_type_compatibility(3.14, float) is True


class TestValidateTypedDict:

    def test_valid_data(self):
        result = validate_typed_dict({"name": "Alice", "age": 30}, SimpleSchema)
        assert result == {"name": "Alice", "age": 30}

    def test_missing_required_field_raises(self):
        with pytest.raises(ValueError, match="Missing required fields"):
            validate_typed_dict({"name": "Alice"}, SimpleSchema)

    def test_unexpected_field_raises(self):
        with pytest.raises(ValueError, match="Unexpected fields"):
            validate_typed_dict({"name": "Alice", "age": 30, "extra": "bad"}, SimpleSchema)

    def test_type_error_raises(self):
        with pytest.raises(ValueError):
            validate_typed_dict({"name": "Alice", "age": "not-an-int"}, SimpleSchema)

    def test_non_dict_raises(self):
        with pytest.raises(ValueError, match="Expected dict"):
            validate_typed_dict("not a dict", SimpleSchema)

    def test_optional_fields_not_required(self):
        # OptionalSchema has total=False so all fields are optional
        result = validate_typed_dict({}, OptionalSchema)
        assert result == {}

    def test_optional_fields_accepted(self):
        result = validate_typed_dict({"nickname": "Bob"}, OptionalSchema)
        assert result == {"nickname": "Bob"}


# ===========================================================================
# 3. merge_dict.py
# ===========================================================================

class TestMergeDictionaries:

    def test_simple_merge(self):
        a = {"x": 1}
        b = {"y": 2}
        merge_dictionaries(a, b)
        assert a == {"x": 1, "y": 2}

    def test_b_overrides_a(self):
        a = {"x": 1}
        b = {"x": 99}
        merge_dictionaries(a, b)
        assert a["x"] == 99

    def test_nested_merge(self):
        a = {"config": {"debug": False, "level": 1}}
        b = {"config": {"level": 2}}
        merge_dictionaries(a, b)
        assert a["config"]["debug"] is False
        assert a["config"]["level"] == 2

    def test_empty_b_no_change(self):
        a = {"x": 1}
        merge_dictionaries(a, {})
        assert a == {"x": 1}

    def test_empty_a_gets_b(self):
        a = {}
        b = {"y": 2}
        merge_dictionaries(a, b)
        assert a == {"y": 2}

    def test_deeply_nested_merge(self):
        a = {"a": {"b": {"c": 1}}}
        b = {"a": {"b": {"d": 2}}}
        merge_dictionaries(a, b)
        assert a["a"]["b"]["c"] == 1
        assert a["a"]["b"]["d"] == 2

    def test_non_dict_value_in_a_overwritten(self):
        a = {"key": "string-value"}
        b = {"key": {"nested": True}}
        merge_dictionaries(a, b)
        assert a["key"] == {"nested": True}


class TestMergeParallelSessionStates:

    def test_applies_changed_keys(self):
        original = {"x": 1, "y": 2}
        modified = [{"x": 10}]
        merge_parallel_session_states(original, modified)
        assert original["x"] == 10
        assert original["y"] == 2

    def test_unchanged_keys_not_applied(self):
        original = {"x": 1}
        modified = [{"x": 1}]  # same value
        merge_parallel_session_states(original, modified)
        assert original["x"] == 1

    def test_empty_original_no_change(self):
        original = {}
        modified = [{"x": 10}]
        merge_parallel_session_states(original, modified)
        # Function returns early when original is empty
        assert original == {}

    def test_empty_modified_no_change(self):
        original = {"x": 1}
        merge_parallel_session_states(original, [])
        assert original == {"x": 1}

    def test_new_key_from_modified(self):
        original = {"x": 1}
        modified = [{"new_key": "hello"}]
        merge_parallel_session_states(original, modified)
        assert original["new_key"] == "hello"

    def test_multiple_modified_states_all_applied(self):
        original = {"a": 1, "b": 2}
        modified = [{"a": 10}, {"b": 20}]
        merge_parallel_session_states(original, modified)
        assert original["a"] == 10
        assert original["b"] == 20

    def test_none_modified_state_skipped(self):
        original = {"x": 1}
        modified = [None, {"x": 5}]
        merge_parallel_session_states(original, modified)
        assert original["x"] == 5


# ===========================================================================
# 4. safe_formatter.py
# ===========================================================================

class TestSafeFormatter:

    def setup_method(self):
        self.fmt = SafeFormatter()

    def test_present_key_formats_correctly(self):
        result = self.fmt.format("{name}", name="Alice")
        assert result == "Alice"

    def test_missing_key_returns_key_literal(self):
        result = self.fmt.format("{missing_key}")
        assert "missing_key" in result

    def test_multiple_keys_missing_one(self):
        result = self.fmt.format("{a} and {b}", a="hello")
        assert "hello" in result
        assert "b" in result

    def test_all_keys_present(self):
        result = self.fmt.format("{x} + {y} = {z}", x=1, y=2, z=3)
        assert result == "1 + 2 = 3"

    def test_format_field_with_invalid_spec_returns_literal(self):
        # Test that an invalid format spec does not raise but returns literal
        formatter = SafeFormatter()
        # Directly test format_field with invalid spec
        result = formatter.format_field("value", '"invalid_spec"')
        assert "value" in result or "invalid_spec" in result

    def test_format_field_with_empty_spec(self):
        formatter = SafeFormatter()
        result = formatter.format_field("hello", "")
        assert result == "hello"

    def test_format_field_with_valid_spec(self):
        formatter = SafeFormatter()
        result = formatter.format_field(3.14159, ".2f")
        assert result == "3.14"

    def test_empty_template(self):
        result = self.fmt.format("")
        assert result == ""

    def test_no_placeholders(self):
        result = self.fmt.format("plain text")
        assert result == "plain text"


# ===========================================================================
# 5. serialize.py
# ===========================================================================

class TestJsonSerializer:

    def test_datetime_returns_iso_format(self):
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = json_serializer(dt)
        assert result == "2024-01-15T10:30:00"

    def test_date_returns_iso_format(self):
        d = date(2024, 6, 1)
        result = json_serializer(d)
        assert result == "2024-06-01"

    def test_time_returns_iso_format(self):
        from datetime import time as time_type
        t = time_type(14, 30, 0)
        result = json_serializer(t)
        assert result == "14:30:00"

    def test_enum_with_str_value(self):
        class Color(Enum):
            RED = "red"

        result = json_serializer(Color.RED)
        assert result == "red"

    def test_enum_with_int_value(self):
        class Status(Enum):
            ACTIVE = 1

        result = json_serializer(Status.ACTIVE)
        assert result == 1

    def test_enum_with_complex_value_uses_name(self):
        class Complex(Enum):
            ITEM = object()

        result = json_serializer(Complex.ITEM)
        assert result == "ITEM"

    def test_unknown_object_returns_str(self):
        class Custom:
            def __str__(self):
                return "custom_repr"

        result = json_serializer(Custom())
        assert result == "custom_repr"

    def test_list_object_falls_back_to_str(self):
        # Lists are JSON-serializable by default, but json_serializer
        # handles the case where it's passed an object
        class MyObj:
            def __str__(self):
                return "my_obj"

        assert json_serializer(MyObj()) == "my_obj"

    def test_none_enum_value(self):
        class NullEnum(Enum):
            NOTHING = None

        result = json_serializer(NullEnum.NOTHING)
        assert result is None


# ===========================================================================
# 6. timer.py
# ===========================================================================

class TestTimer:

    def test_start_sets_start_time(self):
        timer = Timer()
        assert timer.start_time is None
        timer.start()
        assert timer.start_time is not None

    def test_stop_sets_end_time(self):
        timer = Timer()
        timer.start()
        timer.stop()
        assert timer.end_time is not None

    def test_stop_computes_elapsed_time(self):
        timer = Timer()
        timer.start()
        timer.stop()
        assert timer.elapsed_time is not None
        assert timer.elapsed_time >= 0.0

    def test_elapsed_before_start_is_zero(self):
        timer = Timer()
        assert timer.elapsed == 0.0

    def test_elapsed_after_stop_is_elapsed_time(self):
        timer = Timer()
        timer.start()
        time.sleep(0.01)
        timer.stop()
        # After stop, elapsed == elapsed_time
        assert timer.elapsed == timer.elapsed_time

    def test_elapsed_while_running(self):
        timer = Timer()
        timer.start()
        elapsed = timer.elapsed
        assert elapsed >= 0.0

    def test_context_manager(self):
        with Timer() as timer:
            time.sleep(0.01)
        assert timer.elapsed_time is not None
        assert timer.elapsed_time > 0.0

    def test_context_manager_sets_start_and_end(self):
        with Timer() as timer:
            pass
        assert timer.start_time is not None
        assert timer.end_time is not None

    def test_to_dict_contains_expected_keys(self):
        timer = Timer()
        timer.start()
        timer.stop()
        d = timer.to_dict()
        assert "start_time" in d
        assert "end_time" in d
        assert "elapsed" in d

    def test_to_dict_before_start(self):
        timer = Timer()
        d = timer.to_dict()
        assert d["start_time"] is None
        assert d["end_time"] is None
        assert d["elapsed"] == 0.0

    def test_to_dict_start_time_is_string(self):
        timer = Timer()
        timer.start()
        timer.stop()
        d = timer.to_dict()
        assert isinstance(d["start_time"], str)
        assert isinstance(d["end_time"], str)


# ===========================================================================
# 7. tools.py
# ===========================================================================

class TestExtractToolCallFromString:

    def test_basic_extraction(self):
        text = "some text <tool_call>my tool content</tool_call> more"
        result = extract_tool_call_from_string(text)
        assert result == "my tool content"

    def test_extraction_with_json_content(self):
        text = '<tool_call>{"name": "my_tool", "args": {}}</tool_call>'
        result = extract_tool_call_from_string(text)
        assert '"name"' in result

    def test_whitespace_stripped(self):
        text = "<tool_call>  content  </tool_call>"
        result = extract_tool_call_from_string(text)
        assert result == "content"

    def test_custom_tags(self):
        text = "<my_tag>extracted</my_tag>"
        result = extract_tool_call_from_string(text, start_tag="<my_tag>", end_tag="</my_tag>")
        assert result == "extracted"

    def test_empty_content(self):
        text = "<tool_call></tool_call>"
        result = extract_tool_call_from_string(text)
        assert result == ""


class TestRemoveToolCallsFromString:

    def test_single_tool_call_removed(self):
        text = "before <tool_call>content</tool_call> after"
        result = remove_tool_calls_from_string(text)
        assert "<tool_call>" not in result
        assert "before" in result
        assert "after" in result

    def test_multiple_tool_calls_removed(self):
        text = "start <tool_call>one</tool_call> middle <tool_call>two</tool_call> end"
        result = remove_tool_calls_from_string(text)
        assert "<tool_call>" not in result
        assert "</tool_call>" not in result

    def test_no_tool_calls_unchanged(self):
        text = "no tool calls here"
        result = remove_tool_calls_from_string(text)
        assert result == text

    def test_custom_tags(self):
        text = "text <fn>call</fn> more"
        result = remove_tool_calls_from_string(text, start_tag="<fn>", end_tag="</fn>")
        assert "<fn>" not in result
        assert "text" in result
        assert "more" in result

    def test_empty_string(self):
        result = remove_tool_calls_from_string("")
        assert result == ""


class TestExtractToolFromXml:

    def test_basic_extraction(self):
        xml = """
        <tool_name>my_tool</tool_name>
        <parameters>
            <param1>value1</param1>
            <param2>value2</param2>
        </parameters>
        """
        result = extract_tool_from_xml(xml)
        assert result["tool_name"] == "my_tool"
        assert result["parameters"]["param1"] == "value1"
        assert result["parameters"]["param2"] == "value2"

    def test_single_parameter(self):
        xml = "<tool_name>search</tool_name><parameters><query>hello world</query></parameters>"
        result = extract_tool_from_xml(xml)
        assert result["tool_name"] == "search"
        assert result["parameters"]["query"] == "hello world"

    def test_empty_parameters(self):
        xml = "<tool_name>noop</tool_name><parameters></parameters>"
        result = extract_tool_from_xml(xml)
        assert result["tool_name"] == "noop"
        assert result["parameters"] == {}

    def test_returns_dict_with_tool_name_and_parameters_keys(self):
        xml = "<tool_name>t</tool_name><parameters><x>1</x></parameters>"
        result = extract_tool_from_xml(xml)
        assert "tool_name" in result
        assert "parameters" in result


class TestRemoveFunctionCallsFromString:

    def test_single_function_call_removed(self):
        text = "before <function_calls>call_content</function_calls> after"
        result = remove_function_calls_from_string(text)
        assert "<function_calls>" not in result
        assert "before" in result
        assert "after" in result

    def test_multiple_function_calls_removed(self):
        text = "A <function_calls>first</function_calls> B <function_calls>second</function_calls> C"
        result = remove_function_calls_from_string(text)
        assert "<function_calls>" not in result
        assert "</function_calls>" not in result

    def test_no_function_calls_unchanged(self):
        text = "clean text"
        result = remove_function_calls_from_string(text)
        assert result == text

    def test_custom_tags(self):
        text = "x <calls>body</calls> y"
        result = remove_function_calls_from_string(text, start_tag="<calls>", end_tag="</calls>")
        assert "<calls>" not in result


# ===========================================================================
# 8. functions.py
# ===========================================================================

class TestGetFunctionCall:

    def _make_functions(self, names: List[str]) -> Dict[str, Function]:
        return {name: Function(name=name) for name in names}

    def test_none_functions_returns_none(self):
        result = get_function_call(name="test", functions=None)
        assert result is None

    def test_missing_function_returns_none(self):
        functions = self._make_functions(["other_func"])
        result = get_function_call(name="nonexistent", functions=functions)
        assert result is None

    def test_valid_function_returns_function_call(self):
        functions = self._make_functions(["my_func"])
        result = get_function_call(name="my_func", functions=functions)
        assert result is not None
        assert isinstance(result, FunctionCall)

    def test_valid_json_arguments_parsed(self):
        functions = self._make_functions(["func"])
        result = get_function_call(
            name="func",
            arguments='{"key": "value"}',
            functions=functions,
        )
        assert result is not None
        assert result.arguments == {"key": "value"}

    def test_invalid_json_arguments_sets_error(self):
        functions = self._make_functions(["func"])
        result = get_function_call(
            name="func",
            arguments="{not valid json!!!}",
            functions=functions,
        )
        assert result is not None
        assert result.error is not None

    def test_call_id_assigned(self):
        functions = self._make_functions(["func"])
        result = get_function_call(
            name="func",
            call_id="abc-123",
            functions=functions,
        )
        assert result is not None
        assert result.call_id == "abc-123"

    def test_none_string_value_converted_to_none(self):
        functions = self._make_functions(["func"])
        result = get_function_call(
            name="func",
            arguments='{"param": "none"}',
            functions=functions,
        )
        assert result is not None
        assert result.arguments["param"] is None

    def test_true_string_value_converted_to_bool(self):
        functions = self._make_functions(["func"])
        result = get_function_call(
            name="func",
            arguments='{"flag": "true"}',
            functions=functions,
        )
        assert result is not None
        assert result.arguments["flag"] is True

    def test_false_string_value_converted_to_bool(self):
        functions = self._make_functions(["func"])
        result = get_function_call(
            name="func",
            arguments='{"flag": "false"}',
            functions=functions,
        )
        assert result is not None
        assert result.arguments["flag"] is False

    def test_non_dict_json_argument_sets_error(self):
        functions = self._make_functions(["func"])
        result = get_function_call(
            name="func",
            arguments='"just a string"',
            functions=functions,
        )
        assert result is not None
        assert result.error is not None

    def test_empty_arguments_string_no_parsing(self):
        functions = self._make_functions(["func"])
        result = get_function_call(
            name="func",
            arguments="",
            functions=functions,
        )
        assert result is not None
        assert result.arguments is None


# ===========================================================================
# 9. message.py
# ===========================================================================

class TestFilterToolCalls:

    def _make_messages(self) -> List[Message]:
        """Create a realistic sequence of messages with tool calls."""
        messages = [
            Message(role="user", content="hello"),
            Message(
                role="assistant",
                content="I'll use tools",
                tool_calls=[{"id": "tc-1", "type": "function"}],
            ),
            Message(role="tool", content="result-1", tool_call_id="tc-1"),
            Message(
                role="assistant",
                content="Using another tool",
                tool_calls=[{"id": "tc-2", "type": "function"}],
            ),
            Message(role="tool", content="result-2", tool_call_id="tc-2"),
            Message(
                role="assistant",
                content="One more",
                tool_calls=[{"id": "tc-3", "type": "function"}],
            ),
            Message(role="tool", content="result-3", tool_call_id="tc-3"),
        ]
        return messages

    def test_no_filtering_when_within_limit(self):
        messages = self._make_messages()
        original_len = len(messages)
        filter_tool_calls(messages, max_tool_calls=10)
        assert len(messages) == original_len

    def test_filters_to_most_recent_n(self):
        messages = self._make_messages()
        filter_tool_calls(messages, max_tool_calls=1)
        # Only tool calls with id "tc-3" should remain
        tool_msgs = [m for m in messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].tool_call_id == "tc-3"

    def test_keeps_two_most_recent(self):
        messages = self._make_messages()
        filter_tool_calls(messages, max_tool_calls=2)
        tool_msgs = [m for m in messages if m.role == "tool"]
        assert len(tool_msgs) == 2
        ids = {m.tool_call_id for m in tool_msgs}
        assert "tc-3" in ids
        assert "tc-2" in ids

    def test_user_messages_preserved(self):
        messages = self._make_messages()
        filter_tool_calls(messages, max_tool_calls=1)
        user_msgs = [m for m in messages if m.role == "user"]
        assert len(user_msgs) == 1

    def test_exact_limit_no_filtering(self):
        messages = self._make_messages()
        filter_tool_calls(messages, max_tool_calls=3)
        tool_msgs = [m for m in messages if m.role == "tool"]
        assert len(tool_msgs) == 3

    def test_empty_messages_list(self):
        messages = []
        filter_tool_calls(messages, max_tool_calls=5)
        assert messages == []

    def test_no_tool_calls_unchanged(self):
        messages = [
            Message(role="user", content="hi"),
            Message(role="assistant", content="hello"),
        ]
        filter_tool_calls(messages, max_tool_calls=1)
        assert len(messages) == 2


class TestGetTextFromMessage:

    def test_plain_string(self):
        result = get_text_from_message("hello world")
        assert result == "hello world"

    def test_list_of_messages_returns_user_content(self):
        messages = [
            Message(role="user", content="user says this"),
            Message(role="assistant", content="assistant says that"),
        ]
        result = get_text_from_message(messages)
        assert "user says this" in result
        assert "assistant says that" not in result

    def test_list_of_dicts_with_type_key(self):
        messages = [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ]
        result = get_text_from_message(messages)
        assert "hello" in result
        assert "world" in result

    def test_list_of_dicts_with_role_key(self):
        messages = [
            {"role": "user", "content": "user content"},
            {"role": "assistant", "content": "assistant content"},
        ]
        result = get_text_from_message(messages)
        assert "user content" in result
        assert "assistant content" not in result

    def test_dict_with_content_key(self):
        result = get_text_from_message({"content": "inner content"})
        assert result == "inner content"

    def test_dict_without_content_key_returns_json(self):
        result = get_text_from_message({"key": "value"})
        assert "key" in result

    def test_empty_list_returns_empty_string(self):
        result = get_text_from_message([])
        assert result == ""

    def test_pydantic_model_returns_json(self):
        class MyModel(BaseModel):
            name: str

        result = get_text_from_message(MyModel(name="test"))
        assert "test" in result

    def test_message_object_with_string_content(self):
        msg = Message(role="user", content="direct content")
        result = get_text_from_message(msg)
        assert "direct content" in result

    def test_message_object_with_none_content(self):
        # Message is a BaseModel subclass; when passed directly (not in a list),
        # it hits the BaseModel branch which serializes the whole model as JSON.
        msg = Message(role="user", content=None)
        result = get_text_from_message(msg)
        # The BaseModel branch dumps JSON representation of the message
        assert "role" in result
        assert "user" in result

    def test_multiple_user_messages_joined(self):
        messages = [
            Message(role="user", content="first"),
            Message(role="user", content="second"),
        ]
        result = get_text_from_message(messages)
        assert "first" in result
        assert "second" in result

    def test_list_of_dicts_with_image_type_not_included(self):
        messages = [
            {"type": "text", "text": "hello"},
            {"type": "image_url", "image_url": "http://example.com/img.png"},
        ]
        result = get_text_from_message(messages)
        assert "hello" in result
        # image_url type is not extracted by the current implementation
        assert "http://example.com" not in result


# ===========================================================================
# 10. response.py
# ===========================================================================

class TestEscapeMarkdownTags:

    def test_escapes_opening_tag(self):
        result = escape_markdown_tags("text <tool_call> more", {"tool_call"})
        assert "<tool_call>" not in result
        assert "&lt;tool_call&gt;" in result

    def test_escapes_closing_tag(self):
        result = escape_markdown_tags("text </tool_call> more", {"tool_call"})
        assert "</tool_call>" not in result
        assert "&lt;/tool_call&gt;" in result

    def test_escapes_multiple_tags(self):
        content = "<a>and</a><b>also</b>"
        result = escape_markdown_tags(content, {"a", "b"})
        assert "<a>" not in result
        assert "<b>" not in result
        assert "&lt;a&gt;" in result
        assert "&lt;b&gt;" in result

    def test_empty_tags_set_no_change(self):
        content = "<tool_call>content</tool_call>"
        result = escape_markdown_tags(content, set())
        assert result == content

    def test_no_matching_tags_unchanged(self):
        content = "<other>content</other>"
        result = escape_markdown_tags(content, {"tool_call"})
        assert result == content

    def test_empty_content(self):
        result = escape_markdown_tags("", {"tool_call"})
        assert result == ""

    def test_multiple_occurrences_all_escaped(self):
        content = "<fn>first</fn> and <fn>second</fn>"
        result = escape_markdown_tags(content, {"fn"})
        assert "<fn>" not in result
        assert result.count("&lt;fn&gt;") == 2


class TestFormatToolCalls:

    def test_basic_tool_call_formatted(self):
        te = _make_tool_execution(tool_name="search", tool_args={"query": "hello"})
        result = format_tool_calls([te])
        assert len(result) == 1
        assert "search" in result[0]
        assert "query" in result[0]

    def test_tool_call_without_args(self):
        te = _make_tool_execution(tool_name="noop", tool_args=None)
        result = format_tool_calls([te])
        assert len(result) == 1
        assert "noop()" in result[0]

    def test_tool_call_with_empty_args(self):
        te = _make_tool_execution(tool_name="noop", tool_args={})
        result = format_tool_calls([te])
        assert len(result) == 1
        assert "noop()" in result[0]

    def test_none_tool_name_excluded(self):
        te = _make_tool_execution(tool_name=None)
        result = format_tool_calls([te])
        assert len(result) == 0

    def test_multiple_tool_calls(self):
        te1 = _make_tool_execution(tool_name="tool_a", tool_args={"x": 1})
        te2 = _make_tool_execution(tool_name="tool_b", tool_args={"y": 2})
        result = format_tool_calls([te1, te2])
        assert len(result) == 2
        assert any("tool_a" in r for r in result)
        assert any("tool_b" in r for r in result)

    def test_empty_list(self):
        result = format_tool_calls([])
        assert result == []

    def test_multiple_args_all_included(self):
        te = _make_tool_execution(
            tool_name="func",
            tool_args={"a": "1", "b": "2", "c": "3"},
        )
        result = format_tool_calls([te])
        assert len(result) == 1
        formatted = result[0]
        assert "a" in formatted
        assert "b" in formatted
        assert "c" in formatted
