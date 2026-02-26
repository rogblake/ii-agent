from google.genai import types

from ii_agent.engine.v1.models.google.gemini_schema import _json_to_genai_schema, create_function_declaration


def test_json_to_genai_schema_handles_oneof_and_null_fallback():
    schema = {
        "oneOf": [
            {
                "type": "object",
                "properties": {"name": {"type": "string"}, "age": {"type": "null"}},
                "required": ["name"],
            }
        ]
    }

    converted = _json_to_genai_schema(schema)

    assert converted.type == types.Type.OBJECT
    assert converted.properties["name"].type == types.Type.STRING
    assert converted.properties["age"].type == types.Type.STRING
    assert converted.required == ["name"]


def test_json_to_genai_schema_handles_enum_and_arrays():
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["new", "done"]},
            "scores": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["status"],
    }

    converted = _json_to_genai_schema(schema)

    assert converted.properties["status"].enum == ["new", "done"]
    assert converted.properties["scores"].items.type == types.Type.INTEGER


def test_create_function_declaration_returns_none_on_invalid_input():
    declaration = create_function_declaration(
        name="demo",
        description="desc",
        parameters={"type": "object", "properties": {"x": {"type": "string"}}},
    )

    assert declaration is not None
    assert declaration.name == "demo"
