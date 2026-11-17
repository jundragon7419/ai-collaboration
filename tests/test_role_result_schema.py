import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from aicollab.role_result_schema import (
    ROLE_RESULT_SCHEMA,
    role_result_schema_json,
    validate_against_schema,
    validate_role_result,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "docs" / "probes" / "fixtures"


def _valid_result() -> dict[str, Any]:
    path = FIXTURES / "claude-headless" / "structured-output-role-result.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    return copy.deepcopy(fixture["stdout_json"]["structured_output"])


def test_schema_matches_docs() -> None:
    text = (ROOT / "docs" / "03-roles-and-handoff.md").read_text(encoding="utf-8")
    section = text[text.index("## 공통 role-result JSON Schema") :]
    block = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert block is not None
    assert json.loads(block.group(1)) == ROLE_RESULT_SCHEMA


def test_schema_json_round_trips() -> None:
    assert json.loads(role_result_schema_json()) == ROLE_RESULT_SCHEMA


def test_valid_result_passes() -> None:
    assert validate_role_result(_valid_result()) == []


def test_missing_required_property_is_rejected() -> None:
    result = _valid_result()
    del result["testing"]
    assert any("testing" in error for error in validate_role_result(result))


def test_extra_property_is_rejected() -> None:
    result = _valid_result()
    result["extra"] = "x"
    assert any("extra" in error for error in validate_role_result(result))


def test_nested_extra_property_is_rejected() -> None:
    result = _valid_result()
    result["plan"]["extra"] = "x"
    assert any("$.plan" in error for error in validate_role_result(result))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), 1),
        (("schema_version",), True),
        (("schema_version",), "2"),
        (("kind",), "unknown-kind"),
        (("status",), "done"),
        (("summary",), None),
        (("questions",), "not-a-list"),
        (("questions",), [1]),
        (("plan", "new_dependencies_required"), "false"),
        (("review", "failure_attribution"), "maybe"),
        (("review", "repair_targets"), ["planner"]),
    ],
)
def test_wrong_type_or_enum_is_rejected(path: tuple[str, ...], value: object) -> None:
    result = _valid_result()
    target = result
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert validate_role_result(result) != []


def test_line_must_be_integer_not_bool() -> None:
    result = _valid_result()
    result["review"]["findings"] = [
        {
            "id": "F1",
            "severity": "P1",
            "title": "t",
            "path": "a.py",
            "line": True,
            "criterion_id": "AC1",
            "condition": "c",
            "observed": "o",
            "expected": "e",
            "evidence": "ev",
            "impact": "i",
            "scope": "s",
            "workaround": "w",
        }
    ]
    assert any("$.review.findings[0].line" in error for error in validate_role_result(result))


@pytest.mark.parametrize("instance", [None, [], "text", 1])
def test_non_object_is_rejected(instance: object) -> None:
    assert validate_role_result(instance) != []


def test_unsupported_schema_keyword_raises() -> None:
    with pytest.raises(ValueError, match="pattern"):
        validate_against_schema("x", {"type": "string", "pattern": "^x$"})
