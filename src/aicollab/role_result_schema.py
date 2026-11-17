"""공통 role-result JSON Schema와 이 Schema에 필요한 최소 검증기.

Schema 원문은 docs/03-roles-and-handoff.md의 "공통 role-result JSON Schema" 절이다.
두 CLI에 같은 Schema를 넘기므로(Claude `--json-schema`, Codex `--output-schema`) 문서와
같은 내용을 유지한다. tests/test_role_result_schema.py가 문서와의 일치를 검사한다.

검증기는 이 Schema가 쓰는 키워드(type, enum, required, additionalProperties, properties,
items)만 지원한다. 그 밖의 키워드가 Schema에 있으면 검사를 건너뛰지 않고 예외를 낸다.
"""

import json
from typing import Any

ROLE_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "kind",
        "status",
        "summary",
        "questions",
        "plan",
        "implementation",
        "testing",
        "review",
        "observations",
    ],
    "properties": {
        "schema_version": {"type": "integer", "enum": [2]},
        "kind": {
            "type": "string",
            "enum": ["plan", "implementation", "test-authoring", "review", "observation"],
        },
        "status": {"type": "string", "enum": ["completed", "needs-input", "blocked"]},
        "summary": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
        "plan": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "goal",
                "criteria",
                "steps",
                "scope_paths",
                "check_ids",
                "test_contract",
                "new_dependencies_required",
                "dependency_reason",
            ],
            "properties": {
                "goal": {"type": "string"},
                "criteria": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "description"],
                        "properties": {"id": {"type": "string"}, "description": {"type": "string"}},
                    },
                },
                "steps": {"type": "array", "items": {"type": "string"}},
                "scope_paths": {"type": "array", "items": {"type": "string"}},
                "check_ids": {"type": "array", "items": {"type": "string"}},
                "test_contract": {"type": "string"},
                "new_dependencies_required": {"type": "boolean"},
                "dependency_reason": {"type": "string"},
            },
        },
        "implementation": {
            "type": "object",
            "additionalProperties": False,
            "required": ["description", "changed_paths", "addressed_criteria"],
            "properties": {
                "description": {"type": "string"},
                "changed_paths": {"type": "array", "items": {"type": "string"}},
                "addressed_criteria": {"type": "array", "items": {"type": "string"}},
            },
        },
        "review": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "criteria",
                "findings",
                "failure_attribution",
                "repair_targets",
                "execution_assessment",
            ],
            "properties": {
                "criteria": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["criterion_id", "assessment", "evidence"],
                        "properties": {
                            "criterion_id": {"type": "string"},
                            "assessment": {
                                "type": "string",
                                "enum": ["satisfied", "failed", "not-checked", "not-verified"],
                            },
                            "evidence": {"type": "string"},
                        },
                    },
                },
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "id",
                            "severity",
                            "title",
                            "path",
                            "line",
                            "criterion_id",
                            "condition",
                            "observed",
                            "expected",
                            "evidence",
                            "impact",
                            "scope",
                            "workaround",
                        ],
                        "properties": {
                            "id": {"type": "string"},
                            "severity": {
                                "type": "string",
                                "enum": ["P0", "P1", "P2", "P3", "P4", "P5"],
                            },
                            "title": {"type": "string"},
                            "path": {"type": "string"},
                            "line": {"type": "integer"},
                            "criterion_id": {"type": "string"},
                            "condition": {"type": "string"},
                            "observed": {"type": "string"},
                            "expected": {"type": "string"},
                            "evidence": {"type": "string"},
                            "impact": {"type": "string"},
                            "scope": {"type": "string"},
                            "workaround": {"type": "string"},
                        },
                    },
                },
                "failure_attribution": {
                    "type": "string",
                    "enum": ["not-applicable", "code", "tests", "both", "environment", "unclear"],
                },
                "repair_targets": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["coder", "tester"]},
                },
                "execution_assessment": {
                    "type": "string",
                    "enum": ["not-applicable", "passed", "failed", "not-run", "environment-error"],
                },
            },
        },
        "observations": {"type": "array", "items": {"type": "string"}},
        "testing": {
            "type": "object",
            "additionalProperties": False,
            "required": ["description", "changed_paths", "covered_criteria"],
            "properties": {
                "description": {"type": "string"},
                "changed_paths": {"type": "array", "items": {"type": "string"}},
                "covered_criteria": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

_SUPPORTED_KEYWORDS = frozenset(
    {"type", "enum", "required", "additionalProperties", "properties", "items"}
)


def role_result_schema_json() -> str:
    """CLI 인자나 파일로 넘길 Schema JSON 문자열을 돌려준다."""
    return json.dumps(ROLE_RESULT_SCHEMA, ensure_ascii=False)


def _type_matches(value: object, expected: str) -> bool:
    # bool은 int의 하위 클래스이므로 integer와 number에서 따로 뺀다.
    match expected:
        case "object":
            return isinstance(value, dict)
        case "array":
            return isinstance(value, list)
        case "string":
            return isinstance(value, str)
        case "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        case "number":
            return isinstance(value, int | float) and not isinstance(value, bool)
        case "boolean":
            return isinstance(value, bool)
        case "null":
            return value is None
        case _:
            raise ValueError(f"unsupported type in schema: {expected!r}")


def validate_against_schema(instance: object, schema: dict[str, Any], path: str = "$") -> list[str]:
    """instance가 schema를 어기는 곳을 `path: 이유` 문자열 목록으로 돌려준다. 빈 목록이면 통과."""
    unsupported = set(schema) - _SUPPORTED_KEYWORDS
    if unsupported:
        raise ValueError(f"unsupported schema keywords at {path}: {sorted(unsupported)}")

    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type is not None:
        if not isinstance(expected_type, str):
            raise ValueError(f"unsupported type value at {path}: {expected_type!r}")
        if not _type_matches(instance, expected_type):
            return [f"{path}: expected {expected_type}, got {type(instance).__name__}"]

    if "enum" in schema and not any(
        type(instance) is type(option) and instance == option for option in schema["enum"]
    ):
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']!r}")

    if isinstance(instance, dict):
        properties: dict[str, Any] = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: unexpected property {key!r}")
        for key, subschema in properties.items():
            if key in instance:
                errors.extend(validate_against_schema(instance[key], subschema, f"{path}.{key}"))

    if isinstance(instance, list) and "items" in schema:
        for index, item in enumerate(instance):
            errors.extend(validate_against_schema(item, schema["items"], f"{path}[{index}]"))

    return errors


def validate_role_result(instance: object) -> list[str]:
    """role-result 객체를 공통 Schema로 검사한다."""
    return validate_against_schema(instance, ROLE_RESULT_SCHEMA)
