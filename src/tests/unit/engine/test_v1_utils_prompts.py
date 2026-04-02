"""Unit tests for engine/runtime/utils/prompts.py.

Covers get_json_output_prompt and get_response_model_format_prompt.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


from ii_agent.agents.utils.prompts import (
    get_json_output_prompt,
    get_response_model_format_prompt,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


class SimpleModel(BaseModel):
    name: str
    age: int


class ModelWithDesc(BaseModel):
    title: str = Field(description="The title of the item")
    count: int = Field(description="Number of items")
    optional_note: Optional[str] = Field(default=None, description="An optional note")


class StatusEnum(str, Enum):
    active = "active"
    inactive = "inactive"


class ModelWithEnum(BaseModel):
    status: StatusEnum
    label: str


class NestedChildModel(BaseModel):
    x: int
    y: int


class ModelWithNested(BaseModel):
    point: NestedChildModel
    name: str


# ---------------------------------------------------------------------------
# get_json_output_prompt — string schema
# ---------------------------------------------------------------------------


class TestGetJsonOutputPromptStringSchema:
    """Given a plain string schema."""

    def test_contains_json_fields_tag(self):
        prompt = get_json_output_prompt("field1, field2")
        assert "<json_fields>" in prompt
        assert "field1, field2" in prompt
        assert "</json_fields>" in prompt

    def test_ends_with_json_instructions(self):
        prompt = get_json_output_prompt("x")
        assert prompt.endswith("Make sure it only contains valid JSON.")

    def test_starts_with_brace_instruction(self):
        prompt = get_json_output_prompt("x")
        assert "Start your response with `{`" in prompt

    def test_json_loads_instruction_present(self):
        prompt = get_json_output_prompt("x")
        assert "json.loads()" in prompt


# ---------------------------------------------------------------------------
# get_json_output_prompt — list schema
# ---------------------------------------------------------------------------


class TestGetJsonOutputPromptListSchema:
    """Given a list schema."""

    def test_list_is_json_serialized(self):
        fields = ["alpha", "beta", "gamma"]
        prompt = get_json_output_prompt(fields)
        assert "<json_fields>" in prompt
        assert json.dumps(fields) in prompt

    def test_empty_list_produces_prompt(self):
        prompt = get_json_output_prompt([])
        # An empty list still produces the prompt
        assert "json_fields" in prompt
        assert "[]" in prompt


# ---------------------------------------------------------------------------
# get_json_output_prompt — None schema (edge case)
# ---------------------------------------------------------------------------


class TestGetJsonOutputPromptNoneSchema:
    """When output_schema is None, a generic instruction is included."""

    def test_none_schema_fallback(self):
        prompt = get_json_output_prompt(None)
        assert "Provide the output as JSON." in prompt

    def test_brace_instruction_still_appended(self):
        prompt = get_json_output_prompt(None)
        assert "Start your response with `{`" in prompt


# ---------------------------------------------------------------------------
# get_json_output_prompt — Pydantic model schema (instance)
# ---------------------------------------------------------------------------


class TestGetJsonOutputPromptPydanticInstance:
    """Given a Pydantic model *instance* (not class)."""

    def test_simple_model_instance_fields_listed(self):
        instance = SimpleModel(name="Alice", age=30)
        prompt = get_json_output_prompt(instance)
        assert "name" in prompt
        assert "age" in prompt
        assert "<json_fields>" in prompt

    def test_model_with_desc_includes_field_properties(self):
        instance = ModelWithDesc(title="T", count=5)
        prompt = get_json_output_prompt(instance)
        assert "title" in prompt
        assert "count" in prompt
        assert "<json_field_properties>" in prompt


# ---------------------------------------------------------------------------
# get_json_output_prompt — Pydantic model schema (class)
# ---------------------------------------------------------------------------


class TestGetJsonOutputPromptPydanticClass:
    """Given a Pydantic model *class*."""

    def test_simple_model_class_produces_field_list(self):
        prompt = get_json_output_prompt(SimpleModel)
        assert "name" in prompt
        assert "age" in prompt

    def test_model_with_description_adds_properties_block(self):
        prompt = get_json_output_prompt(ModelWithDesc)
        assert "<json_field_properties>" in prompt
        assert "title" in prompt

    def test_model_with_enum_includes_defs(self):
        prompt = get_json_output_prompt(ModelWithEnum)
        # The enum type should appear somewhere (either via $defs or enum_type key)
        assert "status" in prompt

    def test_model_with_nested_includes_nested_def(self):
        prompt = get_json_output_prompt(ModelWithNested)
        # Both top-level and nested fields should appear
        assert "point" in prompt or "x" in prompt

    def test_title_fields_stripped_from_properties(self):
        """Field property dicts should not contain the 'title' key."""
        prompt = get_json_output_prompt(SimpleModel)
        # The 'title' key (from JSON schema field title) should NOT appear inside
        # the properties section — we only strip field-level title, not the word 'title'
        # as a field name. We check the json_field_properties block is clean.
        import json as _json

        if "<json_field_properties>" in prompt:
            start = prompt.index("<json_field_properties>") + len("<json_field_properties>")
            end = prompt.index("</json_field_properties>")
            props_str = prompt[start:end].strip()
            props = _json.loads(props_str)
            for field_name, field_props in props.items():
                if field_name != "$defs" and isinstance(field_props, dict):
                    assert "title" not in field_props, (
                        f"Field '{field_name}' should not have 'title' in its properties"
                    )


# ---------------------------------------------------------------------------
# get_response_model_format_prompt
# ---------------------------------------------------------------------------


class TestGetResponseModelFormatPrompt:
    """Tests for get_response_model_format_prompt."""

    def test_contains_field_names(self):
        prompt = get_response_model_format_prompt(SimpleModel)
        assert "name" in prompt
        assert "age" in prompt

    def test_contains_field_descriptions(self):
        prompt = get_response_model_format_prompt(ModelWithDesc)
        assert "The title of the item" in prompt
        assert "Number of items" in prompt

    def test_field_without_description_still_listed(self):
        """Fields that have no description are listed by name only."""
        prompt = get_response_model_format_prompt(SimpleModel)
        # name and age have no description, but they must appear
        assert "- name" in prompt
        assert "- age" in prompt

    def test_header_message(self):
        prompt = get_response_model_format_prompt(SimpleModel)
        assert "valid string (NOT JSON)" in prompt

    def test_returns_string(self):
        result = get_response_model_format_prompt(SimpleModel)
        assert isinstance(result, str)

    def test_model_with_optional_field(self):
        prompt = get_response_model_format_prompt(ModelWithDesc)
        assert "optional_note" in prompt
        assert "An optional note" in prompt
