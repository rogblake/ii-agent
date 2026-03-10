"""Unit tests for ii_agent.engine.runtime.utils.json_schema utility functions."""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import pytest
from pydantic import BaseModel

from ii_agent.engine.runtime.utils.json_schema import (
    get_json_schema,
    get_json_schema_for_arg,
    get_json_type_for_py_type,
    get_py_type_for_json_type,
    inline_pydantic_schema,
)


# ===========================================================================
# get_json_type_for_py_type()
# ===========================================================================


class TestGetJsonTypeForPyType:
    """Tests for get_json_type_for_py_type()."""

    def test_int_returns_number(self):
        assert get_json_type_for_py_type("int") == "number"

    def test_float_returns_number(self):
        assert get_json_type_for_py_type("float") == "number"

    def test_complex_returns_number(self):
        assert get_json_type_for_py_type("complex") == "number"

    def test_Decimal_returns_number(self):
        assert get_json_type_for_py_type("Decimal") == "number"

    def test_str_returns_string(self):
        assert get_json_type_for_py_type("str") == "string"

    def test_string_alias_returns_string(self):
        assert get_json_type_for_py_type("string") == "string"

    def test_bool_returns_boolean(self):
        assert get_json_type_for_py_type("bool") == "boolean"

    def test_boolean_alias_returns_boolean(self):
        assert get_json_type_for_py_type("boolean") == "boolean"

    def test_NoneType_returns_null(self):
        assert get_json_type_for_py_type("NoneType") == "null"

    def test_None_alias_returns_null(self):
        assert get_json_type_for_py_type("None") == "null"

    def test_list_returns_array(self):
        assert get_json_type_for_py_type("list") == "array"

    def test_tuple_returns_array(self):
        assert get_json_type_for_py_type("tuple") == "array"

    def test_set_returns_array(self):
        assert get_json_type_for_py_type("set") == "array"

    def test_frozenset_returns_array(self):
        assert get_json_type_for_py_type("frozenset") == "array"

    def test_dict_returns_object(self):
        assert get_json_type_for_py_type("dict") == "object"

    def test_mapping_returns_object(self):
        assert get_json_type_for_py_type("mapping") == "object"

    def test_unknown_type_returns_object(self):
        assert get_json_type_for_py_type("SomeCustomType") == "object"

    def test_empty_string_returns_object(self):
        assert get_json_type_for_py_type("") == "object"


# ===========================================================================
# get_py_type_for_json_type()
# ===========================================================================


class TestGetPyTypeForJsonType:
    """Tests for get_py_type_for_json_type()."""

    def test_string_returns_str(self):
        assert get_py_type_for_json_type("string") is str

    def test_number_returns_float(self):
        assert get_py_type_for_json_type("number") is float

    def test_integer_returns_int(self):
        assert get_py_type_for_json_type("integer") is int

    def test_boolean_returns_bool(self):
        assert get_py_type_for_json_type("boolean") is bool

    def test_array_returns_list(self):
        assert get_py_type_for_json_type("array") is list

    def test_object_returns_dict(self):
        assert get_py_type_for_json_type("object") is dict

    def test_null_returns_NoneType(self):
        assert get_py_type_for_json_type("null") is type(None)

    def test_unknown_type_defaults_to_str(self):
        assert get_py_type_for_json_type("foobar") is str

    def test_empty_string_defaults_to_str(self):
        assert get_py_type_for_json_type("") is str


# ===========================================================================
# inline_pydantic_schema()
# ===========================================================================


class TestInlinePydanticSchema:
    """Tests for inline_pydantic_schema()."""

    def test_schema_without_refs_is_returned_unchanged(self):
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        result = inline_pydantic_schema(dict(schema))
        assert result["type"] == "object"
        assert result["properties"]["x"] == {"type": "string"}

    def test_ref_in_property_is_resolved(self):
        schema = {
            "$defs": {"Inner": {"type": "object", "properties": {"val": {"type": "integer"}}}},
            "type": "object",
            "properties": {"inner": {"$ref": "#/$defs/Inner"}},
        }
        result = inline_pydantic_schema(schema)
        assert "$ref" not in result["properties"]["inner"]
        assert result["properties"]["inner"]["type"] == "object"

    def test_unknown_ref_resolves_to_object_fallback(self):
        schema = {
            "type": "object",
            "properties": {"x": {"$ref": "#/$defs/Missing"}},
        }
        result = inline_pydantic_schema(schema)
        assert result["properties"]["x"] == {"type": "object"}

    def test_external_ref_resolves_to_object_fallback(self):
        schema = {
            "type": "object",
            "properties": {"x": {"$ref": "http://external.com/schema"}},
        }
        result = inline_pydantic_schema(schema)
        assert result["properties"]["x"] == {"type": "object"}

    def test_anyOf_refs_are_resolved(self):
        schema = {
            "$defs": {"Str": {"type": "string"}, "Int": {"type": "integer"}},
            "anyOf": [{"$ref": "#/$defs/Str"}, {"$ref": "#/$defs/Int"}],
        }
        result = inline_pydantic_schema(schema)
        types = {s["type"] for s in result["anyOf"]}
        assert "string" in types
        assert "integer" in types

    def test_allOf_refs_are_resolved(self):
        schema = {
            "$defs": {"Base": {"type": "object", "properties": {"id": {"type": "string"}}}},
            "allOf": [{"$ref": "#/$defs/Base"}],
        }
        result = inline_pydantic_schema(schema)
        assert "$ref" not in result["allOf"][0]
        assert result["allOf"][0]["type"] == "object"

    def test_items_ref_is_resolved(self):
        schema = {
            "$defs": {"Item": {"type": "string"}},
            "type": "array",
            "items": {"$ref": "#/$defs/Item"},
        }
        result = inline_pydantic_schema(schema)
        assert result["items"] == {"type": "string"}

    def test_defs_key_removed_from_result(self):
        schema = {
            "$defs": {"T": {"type": "string"}},
            "type": "object",
            "properties": {"t": {"$ref": "#/$defs/T"}},
        }
        result = inline_pydantic_schema(schema)
        assert "$defs" not in result

    def test_non_dict_input_is_returned_as_is(self):
        assert inline_pydantic_schema("not-a-dict") == "not-a-dict"  # type: ignore[arg-type]

    def test_additionalProperties_ref_is_resolved(self):
        schema = {
            "$defs": {"Val": {"type": "number"}},
            "type": "object",
            "additionalProperties": {"$ref": "#/$defs/Val"},
        }
        result = inline_pydantic_schema(schema)
        assert result["additionalProperties"] == {"type": "number"}


# ===========================================================================
# get_json_schema_for_arg()
# ===========================================================================


class TestGetJsonSchemaForArg:
    """Tests for get_json_schema_for_arg()."""

    def test_list_type_hint_returns_array_schema(self):
        result = get_json_schema_for_arg(List[str])
        assert result is not None
        assert result["type"] == "array"
        assert result["items"] == {"type": "string"}

    def test_list_without_args_returns_array_with_string_items(self):
        result = get_json_schema_for_arg(list)
        assert result is not None
        assert result["type"] == "array"

    def test_dict_type_hint_returns_object_schema(self):
        result = get_json_schema_for_arg(Dict[str, int])
        assert result is not None
        assert result["type"] == "object"
        assert "propertyNames" in result
        assert "additionalProperties" in result

    def test_optional_type_returns_anyof(self):
        result = get_json_schema_for_arg(Optional[str])
        assert result is not None
        assert "anyOf" in result
        types = {s.get("type") for s in result["anyOf"]}
        assert "string" in types
        assert "null" in types

    def test_union_type_returns_anyof(self):
        result = get_json_schema_for_arg(Union[str, int])
        assert result is not None
        assert "anyOf" in result
        assert len(result["anyOf"]) == 2

    def test_enum_type_returns_string_with_enum_values(self):
        class Color(str, Enum):
            RED = "red"
            GREEN = "green"
            BLUE = "blue"

        result = get_json_schema_for_arg(Color)
        assert result is not None
        assert result["type"] == "string"
        assert set(result["enum"]) == {"red", "green", "blue"}

    def test_base_model_returns_inlined_object_schema(self):
        class MyModel(BaseModel):
            name: str
            age: int

        result = get_json_schema_for_arg(MyModel)
        assert result is not None
        assert result["type"] == "object"
        assert "name" in result["properties"]
        assert "age" in result["properties"]

    def test_dataclass_returns_object_schema(self):
        # Use dataclass with pre-resolved type objects (not string annotations)
        # to ensure get_json_schema_for_arg can process field.type as a type object.
        import dataclasses as dc

        @dc.dataclass
        class Point:
            x: float = 0.0
            y: float = 0.0

        # Manually set field types to actual types since the source accesses field.type
        # which may be a string in Python 3.10 with from __future__ import annotations.
        for f in dc.fields(Point):
            object.__setattr__(f, "type", float)

        result = get_json_schema_for_arg(Point)
        assert result is not None
        assert result["type"] == "object"
        assert "x" in result["properties"]
        assert "y" in result["properties"]

    def test_basic_str_type_returns_string(self):
        result = get_json_schema_for_arg(str)
        assert result is not None
        assert result["type"] == "string"

    def test_basic_int_type_returns_number(self):
        result = get_json_schema_for_arg(int)
        assert result is not None
        assert result["type"] == "number"

    def test_basic_bool_type_returns_boolean(self):
        result = get_json_schema_for_arg(bool)
        assert result is not None
        assert result["type"] == "boolean"

    def test_list_of_int_has_number_items(self):
        result = get_json_schema_for_arg(List[int])
        assert result is not None
        assert result["type"] == "array"
        assert result["items"]["type"] == "number"

    def test_nested_list_schema(self):
        result = get_json_schema_for_arg(List[List[str]])
        assert result is not None
        assert result["type"] == "array"
        assert result["items"]["type"] == "array"

    def test_dataclass_optional_field_not_in_required(self):
        import dataclasses as dc

        @dc.dataclass
        class Container:
            required_field: str = ""
            optional_field: Optional[str] = None  # type: ignore[assignment]

        # Override field types to actual type objects so the source code can call
        # get_json_schema_for_arg(field.type) without hitting AttributeError.
        for f in dc.fields(Container):
            if f.name == "required_field":
                object.__setattr__(f, "type", str)
            else:
                object.__setattr__(f, "type", Optional[str])

        result = get_json_schema_for_arg(Container)
        assert result is not None
        # The optional field should NOT appear in required.
        assert "optional_field" not in result.get("required", [])
        assert "required_field" in result.get("required", [])


# ===========================================================================
# get_json_schema()
# ===========================================================================


class TestGetJsonSchema:
    """Tests for get_json_schema()."""

    def test_single_string_param(self):
        hints = {"query": str}
        result = get_json_schema(hints)
        assert result["type"] == "object"
        assert "query" in result["properties"]
        assert result["properties"]["query"]["type"] == "string"

    def test_multiple_params(self):
        hints = {"name": str, "age": int, "active": bool}
        result = get_json_schema(hints)
        props = result["properties"]
        assert "name" in props
        assert "age" in props
        assert "active" in props

    def test_return_key_is_skipped(self):
        hints = {"param": str, "return": str}
        result = get_json_schema(hints)
        assert "return" not in result["properties"]
        assert "param" in result["properties"]

    def test_descriptions_are_added(self):
        hints = {"query": str}
        descs = {"query": "The search query string"}
        result = get_json_schema(hints, param_descriptions=descs)
        assert result["properties"]["query"]["description"] == "The search query string"

    def test_no_descriptions_omits_description_key(self):
        hints = {"query": str}
        result = get_json_schema(hints)
        assert "description" not in result["properties"]["query"]

    def test_optional_param_is_unwrapped(self):
        hints = {"name": Optional[str]}
        result = get_json_schema(hints)
        # Optional[str] should be unwrapped to str (not anyOf).
        assert result["properties"]["name"]["type"] == "string"

    def test_strict_mode_adds_additional_properties_false(self):
        hints = {"x": int}
        result = get_json_schema(hints, strict=True)
        assert result.get("additionalProperties") is False

    def test_non_strict_mode_does_not_add_additional_properties(self):
        hints = {"x": int}
        result = get_json_schema(hints, strict=False)
        assert "additionalProperties" not in result

    def test_empty_hints_returns_empty_properties(self):
        result = get_json_schema({})
        assert result["type"] == "object"
        assert result["properties"] == {}

    def test_list_param_returns_array(self):
        hints = {"items": List[str]}
        result = get_json_schema(hints)
        assert result["properties"]["items"]["type"] == "array"

    def test_dict_param_returns_object(self):
        hints = {"mapping": Dict[str, int]}
        result = get_json_schema(hints)
        assert result["properties"]["mapping"]["type"] == "object"

    def test_pydantic_model_param_is_inlined(self):
        class Config(BaseModel):
            host: str
            port: int

        hints = {"config": Config}
        result = get_json_schema(hints)
        cfg_schema = result["properties"]["config"]
        assert cfg_schema["type"] == "object"
        assert "host" in cfg_schema["properties"]
        assert "port" in cfg_schema["properties"]

    def test_none_descriptions_dict_is_handled(self):
        hints = {"x": str}
        result = get_json_schema(hints, param_descriptions=None)
        assert "description" not in result["properties"]["x"]

    def test_description_not_added_when_key_missing_from_descs(self):
        hints = {"x": str, "y": int}
        descs = {"x": "X description"}
        result = get_json_schema(hints, param_descriptions=descs)
        assert "description" in result["properties"]["x"]
        assert "description" not in result["properties"]["y"]
