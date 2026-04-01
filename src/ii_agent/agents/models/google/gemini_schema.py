"""Gemini schema conversion utilities for function declarations."""

from google.genai import types


def _json_to_genai_schema(json_schema: dict):
    """Convert JSON Schema to GenAI Schema format, handling composite types."""
    # Handle None or empty schema - return empty object schema
    if json_schema is None:
        return types.Schema(type=types.Type.OBJECT, properties={}, required=[])

    # Handle composite types (patterns from openapi.py)
    if "oneOf" in json_schema:
        # Gemini doesn't support unions directly, use first valid schema
        # This is a limitation but better than failing
        return _json_to_genai_schema(json_schema["oneOf"][0])

    if "anyOf" in json_schema:
        # Similar to oneOf
        return _json_to_genai_schema(json_schema["anyOf"][0])

    if "allOf" in json_schema:
        # Merge all schemas (pattern from openapi.py's _all_of_to_parameter)
        merged = {}
        for subschema in json_schema["allOf"]:
            merged.update(subschema)
        return _json_to_genai_schema(merged)

    # Handle enum independently (can appear with or without type)
    if "enum" in json_schema:
        return _handle_enum_schema(json_schema)

    schema_type = json_schema.get("type", "string")

    # Map type handlers
    type_handlers = {
        "array": _handle_array_schema,
        "object": _handle_object_schema,
        "string": _handle_string_schema,
        "number": lambda _: types.Schema(type=types.Type.NUMBER),
        "integer": lambda _: types.Schema(type=types.Type.INTEGER),
        "boolean": lambda _: types.Schema(type=types.Type.BOOLEAN),
        "null": lambda _: types.Schema(type=types.Type.STRING),  # Gemini doesn't have null type
    }

    handler = type_handlers.get(schema_type, lambda _: types.Schema(type=types.Type.STRING))
    return handler(json_schema)


def _handle_array_schema(json_schema: dict):
    """Handle array type schema conversion."""
    items = json_schema.get("items", {})
    return types.Schema(
        type=types.Type.ARRAY,
        items=_json_to_genai_schema(items) if items else types.Schema(type=types.Type.STRING),
    )


def _handle_object_schema(json_schema: dict):
    """Handle object type schema conversion."""
    properties = {
        name: schema_obj
        for name, schema in json_schema.get("properties", {}).items()
        if (schema_obj := _json_to_genai_schema(schema)) is not None
    }
    return types.Schema(
        type=types.Type.OBJECT,
        properties=properties,
        required=json_schema.get("required", []),
    )


def _handle_string_schema(json_schema: dict):
    """Handle string type schema conversion."""
    if enum_values := json_schema.get("enum"):
        return types.Schema(type=types.Type.STRING, enum=enum_values)
    return types.Schema(type=types.Type.STRING)


def _handle_enum_schema(json_schema: dict):
    """Handle enum schema conversion (pattern from openapi.py)."""
    # Enum can be of any type, default to string if no type specified
    base_type = json_schema.get("type", "string")
    type_map = {
        "string": types.Type.STRING,
        "integer": types.Type.INTEGER,
        "number": types.Type.NUMBER,
    }
    schema_type = type_map.get(base_type, types.Type.STRING)
    return types.Schema(type=schema_type, enum=json_schema["enum"])


def create_function_declaration(name, description, parameters):
    """Create a native Gemini FunctionDeclaration if possible."""
    try:
        genai_schema = _json_to_genai_schema(parameters)
        return types.FunctionDeclaration(
            name=name,
            description=description,
            parameters=genai_schema,
        )
    except Exception as e:
        print(f"Warning: Could not create FunctionDeclaration for {name}: {e}")
        return None
