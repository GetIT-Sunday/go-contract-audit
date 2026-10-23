"""Dependency-free validator for the frozen R043 fixture JSON Schema subset."""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    pass


def _resolve(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise SchemaValidationError(f"unsupported schema reference {reference}")
    value: Any = root
    for part in reference[2:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "null": value is None,
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }.get(expected, False)


def validate_json(value: Any, schema: dict[str, Any], *, root: dict[str, Any] | None = None, path: str = "$") -> None:
    root = schema if root is None else root
    if "$ref" in schema:
        validate_json(value, _resolve(root, schema["$ref"]), root=root, path=path)
        return
    if "anyOf" in schema:
        failures = []
        for branch in schema["anyOf"]:
            try:
                validate_json(value, branch, root=root, path=path)
                break
            except SchemaValidationError as exc:
                failures.append(str(exc))
        else:
            raise SchemaValidationError(f"{path}: no anyOf branch matched: {failures}")
    expected = schema.get("type")
    if expected is not None:
        options = [expected] if isinstance(expected, str) else expected
        if not any(_type_matches(value, option) for option in options):
            raise SchemaValidationError(f"{path}: expected type {options}")
    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path}: value {value!r} outside enum")
    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise SchemaValidationError(f"{path}: missing {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise SchemaValidationError(f"{path}: additional properties {extra}")
        additional = schema.get("additionalProperties")
        for key, item in value.items():
            child = properties.get(key, additional if isinstance(additional, dict) else None)
            if child:
                validate_json(item, child, root=root, path=f"{path}.{key}")
        if len(value) < schema.get("minProperties", 0):
            raise SchemaValidationError(f"{path}: too few properties")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
            raise SchemaValidationError(f"{path}: array length out of bounds")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            raise SchemaValidationError(f"{path}: items are not unique")
        if "items" in schema:
            for index, item in enumerate(value):
                validate_json(item, schema["items"], root=root, path=f"{path}[{index}]")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise SchemaValidationError(f"{path}: string too short")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise SchemaValidationError(f"{path}: string does not match pattern")
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise SchemaValidationError(f"{path}: invalid date-time") from exc
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaValidationError(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaValidationError(f"{path}: above maximum")
    for branch in schema.get("allOf", []):
        condition = branch.get("if")
        applies = True
        if condition:
            try:
                validate_json(value, condition, root=root, path=path)
            except SchemaValidationError:
                applies = False
        if applies and "then" in branch:
            validate_json(value, branch["then"], root=root, path=path)


def load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def public_fixture_schema(frozen_schema: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(frozen_schema)
    result["properties"].pop("ground_truth", None)
    result["allOf"] = []
    artifacts = result["properties"]["artifacts"]["properties"]
    artifacts.pop("private_expected_manifest", None)
    return result


def validate_public_fixture(value: dict[str, Any], frozen_schema: dict[str, Any]) -> None:
    forbidden = {"ground_truth", "injected_axes", "minimal_reconciling_axis_sets", "expected_verdict", "required_claim_guards", "private_expected_manifest"}
    serialized = json.dumps(value, sort_keys=True)
    if any(f'"{key}"' in serialized for key in forbidden):
        raise SchemaValidationError("public fixture contains private expectation fields")
    validate_json(value, public_fixture_schema(frozen_schema))


def validate_scoring_view(value: dict[str, Any], frozen_schema: dict[str, Any]) -> None:
    validate_json(value, frozen_schema)
