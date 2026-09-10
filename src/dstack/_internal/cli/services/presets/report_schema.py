"""The final report schema the agent CLIs enforce on the agent's last message."""

from typing import Any

from dstack._internal.cli.models.preset_agent import PresetAgentFailure, PresetAgentSuccess

# Keywords the strict structured-output mode of the OpenAI API rejects.
_STRICT_UNSUPPORTED_KEYWORDS = frozenset(
    {
        "title",
        "default",
        "examples",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "uniqueItems",
        "multipleOf",
        "minProperties",
        "maxProperties",
        "patternProperties",
        "readOnly",
        "deprecated",
        "$comment",
        "contentMediaType",
    }
)


def get_report_json_schema() -> dict[str, Any]:
    """The one shape the API can enforce: a single object, no union, only
    `success` required. `AnyPresetAgentResult` enforces the rest at parse."""
    success = PresetAgentSuccess.model_json_schema()
    failure = PresetAgentFailure.model_json_schema()
    return {
        "type": "object",
        "properties": {
            **success["properties"],
            **failure["properties"],
            # Each outcome fixes its own value; only the merged shape offers both.
            "success": {"type": "boolean"},
        },
        "required": ["success"],
        "additionalProperties": False,
        "$defs": {**success.get("$defs", {}), **failure.get("$defs", {})},
    }


def get_strict_report_json_schema() -> dict[str, Any]:
    """`get_report_json_schema` in the strict form the OpenAI API enforces: every
    property required, optional ones nullable, no unsupported keywords. A field
    the agent has no value for comes back as `null`, which the report parser drops."""
    return _strict(get_report_json_schema())


def _strict(node: Any) -> Any:
    if isinstance(node, list):
        return [_strict(item) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        # A `$ref` may carry no sibling keywords.
        return {"$ref": node["$ref"]}
    if node.get("type") == "object" and "properties" in node:
        required = set(node.get("required", []))
        properties = {}
        for name, schema in node["properties"].items():
            # An optional field with a concrete default stays non-null and becomes
            # required, so the model writes the default; one without becomes nullable.
            has_default = schema.get("default") is not None
            schema = _strict(schema)
            if name not in required and not has_default:
                schema = _nullable(schema)
            properties[name] = schema
        rest = {
            key: _strict(value)
            for key, value in node.items()
            if key not in _STRICT_UNSUPPORTED_KEYWORDS and key not in ("properties", "required")
        }
        return {
            **rest,
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }
    return {
        key: _strict(value)
        for key, value in node.items()
        if key not in _STRICT_UNSUPPORTED_KEYWORDS
    }


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    if "anyOf" in schema:
        if not any(option.get("type") == "null" for option in schema["anyOf"]):
            schema["anyOf"].append({"type": "null"})
        return schema
    if "$ref" in schema:
        return {"anyOf": [schema, {"type": "null"}]}
    if isinstance(schema.get("type"), str):
        schema["type"] = [schema["type"], "null"]
    elif isinstance(schema.get("type"), list) and "null" not in schema["type"]:
        schema["type"].append("null")
    return schema
