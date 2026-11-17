import json
from pathlib import Path
from typing import Any

import pytest

from aicollab.role_result_parser import (
    FailureKind,
    ParseOutcome,
    parse_claude_output,
    parse_codex_output,
)
from aicollab.role_result_schema import validate_role_result

FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "probes" / "fixtures"


def _load(provider: str, name: str) -> dict[str, Any]:
    path = FIXTURES / provider / f"{name}.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _claude(name: str) -> ParseOutcome:
    fixture = _load("claude-headless", name)
    return parse_claude_output(fixture["exit_code"], json.dumps(fixture["stdout_json"]))


def _codex_stdout(fixture: dict[str, Any]) -> str:
    return "\n".join(json.dumps(event) for event in fixture["events"])


def _last_agent_message(fixture: dict[str, Any]) -> str | None:
    # fixture는 `-o` 파일 내용을 따로 두지 않는다. `-o`에는 마지막 agent_message의 text가
    # 그대로 들어가므로(docs/probes/codex-exec.md) 그 값을 파일 내용으로 쓴다.
    texts = [
        event["item"]["text"]
        for event in fixture["events"]
        if event["type"] == "item.completed" and event["item"]["type"] == "agent_message"
    ]
    return texts[-1] if texts else None


def _codex(name: str, *, with_file: bool = True) -> ParseOutcome:
    fixture = _load("codex-exec", name)
    output_file = _last_agent_message(fixture) if with_file else None
    return parse_codex_output(fixture["exit_code"], _codex_stdout(fixture), output_file)


def _failure_kind(outcome: ParseOutcome) -> FailureKind:
    assert outcome.failure is not None
    return outcome.failure.kind


# ---------------------------------------------------------------- Claude


def test_claude_success_reads_structured_output() -> None:
    outcome = _claude("structured-output-role-result")
    fixture = _load("claude-headless", "structured-output-role-result")
    assert outcome.ok
    assert outcome.result == fixture["stdout_json"]["structured_output"]
    assert validate_role_result(outcome.result) == []


def test_claude_does_not_fall_back_to_result_string() -> None:
    # result 문자열에는 같은 JSON이 들어 있지만 structured_output이 없으면 실패다.
    fixture = _load("claude-headless", "structured-output-role-result")
    envelope = dict(fixture["stdout_json"])
    del envelope["structured_output"]
    outcome = parse_claude_output(0, json.dumps(envelope))
    assert _failure_kind(outcome) is FailureKind.MISSING_RESULT


@pytest.mark.parametrize(
    "name",
    [
        "success-haiku",
        "success-fable-below-min-version",
        "effort-unknown-value",
        "permission-denied-bash",
        "permission-denied-write",
    ],
)
def test_claude_success_without_schema_has_no_role_result(name: str) -> None:
    # 성공한 호출이지만 --json-schema 없이 실행한 fixture라 structured_output이 없다.
    outcome = _claude(name)
    assert not outcome.ok
    assert _failure_kind(outcome) is FailureKind.MISSING_RESULT


@pytest.mark.parametrize(
    ("name", "api_error_status"),
    [("error-not-logged-in", None), ("error-invalid-model", 404)],
)
def test_claude_error_with_subtype_success_is_failure(
    name: str, api_error_status: int | None
) -> None:
    # M0: 오류에서도 subtype은 success였다. is_error와 terminal_reason으로 판정한다.
    fixture = _load("claude-headless", name)
    assert fixture["stdout_json"]["subtype"] == "success"
    outcome = _claude(name)
    assert not outcome.ok
    assert outcome.result is None
    assert outcome.failure is not None
    assert outcome.failure.kind is FailureKind.PROVIDER_ERROR
    assert outcome.failure.api_error_status == api_error_status


def test_claude_auth_error_is_not_split_by_message() -> None:
    # 인증 없음과 없는 모델은 같은 종류의 실패다. result 문장으로 나누지 않는다.
    assert _failure_kind(_claude("error-not-logged-in")) is _failure_kind(
        _claude("error-invalid-model")
    )


def test_claude_error_result_text_is_not_used() -> None:
    fixture = _load("claude-headless", "error-not-logged-in")
    envelope = dict(fixture["stdout_json"])
    envelope["result"] = "something else entirely"
    outcome = parse_claude_output(fixture["exit_code"], json.dumps(envelope))
    assert _failure_kind(outcome) is FailureKind.PROVIDER_ERROR


def test_claude_is_error_wins_even_with_structured_output() -> None:
    fixture = _load("claude-headless", "structured-output-role-result")
    envelope = dict(fixture["stdout_json"])
    envelope["is_error"] = True
    envelope["terminal_reason"] = "api_error"
    assert _failure_kind(parse_claude_output(1, json.dumps(envelope))) is FailureKind.PROVIDER_ERROR


def test_claude_nonzero_exit_without_is_error_is_unclassifiable() -> None:
    fixture = _load("claude-headless", "structured-output-role-result")
    outcome = parse_claude_output(1, json.dumps(fixture["stdout_json"]))
    assert _failure_kind(outcome) is FailureKind.UNCLASSIFIABLE


def test_claude_unknown_terminal_reason_is_unclassifiable() -> None:
    fixture = _load("claude-headless", "structured-output-role-result")
    envelope = dict(fixture["stdout_json"])
    envelope["terminal_reason"] = "something_new"
    assert _failure_kind(parse_claude_output(0, json.dumps(envelope))) is FailureKind.UNCLASSIFIABLE


@pytest.mark.parametrize("missing", ["is_error", "terminal_reason"])
def test_claude_missing_status_field_is_unclassifiable(missing: str) -> None:
    fixture = _load("claude-headless", "structured-output-role-result")
    envelope = dict(fixture["stdout_json"])
    del envelope[missing]
    assert _failure_kind(parse_claude_output(0, json.dumps(envelope))) is FailureKind.UNCLASSIFIABLE


@pytest.mark.parametrize(
    "stdout",
    ["", "not json", "[]", '{"type": "assistant"}', '{"is_error": false}'],
)
def test_claude_unclassifiable_stdout(stdout: str) -> None:
    assert _failure_kind(parse_claude_output(0, stdout)) is FailureKind.UNCLASSIFIABLE


def test_claude_text_around_json_is_not_accepted() -> None:
    fixture = _load("claude-headless", "structured-output-role-result")
    stdout = "note\n" + json.dumps(fixture["stdout_json"])
    assert _failure_kind(parse_claude_output(0, stdout)) is FailureKind.UNCLASSIFIABLE


def test_claude_schema_violation_is_failure() -> None:
    fixture = _load("claude-headless", "structured-output-role-result")
    envelope = dict(fixture["stdout_json"])
    output = dict(envelope["structured_output"])
    output["kind"] = "unknown-kind"
    del output["observations"]
    envelope["structured_output"] = output
    outcome = parse_claude_output(0, json.dumps(envelope))
    assert _failure_kind(outcome) is FailureKind.SCHEMA_VIOLATION
    assert outcome.result is None


def test_claude_structured_output_must_be_object() -> None:
    fixture = _load("claude-headless", "structured-output-role-result")
    envelope = dict(fixture["stdout_json"])
    envelope["structured_output"] = "OK"
    assert (
        _failure_kind(parse_claude_output(0, json.dumps(envelope))) is FailureKind.SCHEMA_VIOLATION
    )


# ---------------------------------------------------------------- Codex


def test_codex_success_reads_output_file() -> None:
    outcome = _codex("schema-role-result")
    fixture = _load("codex-exec", "schema-role-result")
    assert outcome.ok
    assert outcome.result == json.loads(_last_agent_message(fixture) or "")
    assert validate_role_result(outcome.result) == []


def test_codex_success_without_output_file_is_failure() -> None:
    outcome = _codex("schema-role-result", with_file=False)
    assert _failure_kind(outcome) is FailureKind.MISSING_RESULT


@pytest.mark.parametrize(
    "name",
    [
        "success-gpt-6-astra",
        "events-command-execution",
        "sandbox-read-only",
        "sandbox-workspace-write",
    ],
)
def test_codex_success_with_free_text_is_not_a_role_result(name: str) -> None:
    # turn.completed로 끝났지만 --output-schema 없이 실행해 -o 내용이 JSON이 아니다.
    assert _failure_kind(_codex(name)) is FailureKind.UNCLASSIFIABLE


@pytest.mark.parametrize(
    "name",
    [
        "error-not-logged-in",
        "error-invalid-model",
        "effort-invalid-value",
        "effort-unsupported-minimal",
        "schema-rejected-not-all-required",
    ],
)
def test_codex_turn_failed_is_failure_without_output_file(name: str) -> None:
    # 실패한 turn은 -o 파일을 만들지 않는다.
    fixture = _load("codex-exec", name)
    assert fixture["events"][-1]["type"] == "turn.failed"
    assert _last_agent_message(fixture) is None
    outcome = _codex(name, with_file=False)
    assert not outcome.ok
    assert outcome.result is None
    assert _failure_kind(outcome) is FailureKind.PROVIDER_ERROR


def test_codex_auth_error_is_not_split_by_message() -> None:
    assert _failure_kind(_codex("error-not-logged-in", with_file=False)) is _failure_kind(
        _codex("error-invalid-model", with_file=False)
    )


def test_codex_turn_failed_ignores_stale_output_file() -> None:
    fixture = _load("codex-exec", "schema-role-result")
    stale = _last_agent_message(fixture)
    failed = _load("codex-exec", "error-invalid-model")
    outcome = parse_codex_output(failed["exit_code"], _codex_stdout(failed), stale)
    assert _failure_kind(outcome) is FailureKind.PROVIDER_ERROR


def test_codex_turn_failed_with_exit_zero_is_still_failure() -> None:
    failed = _load("codex-exec", "error-invalid-model")
    outcome = parse_codex_output(0, _codex_stdout(failed), None)
    assert _failure_kind(outcome) is FailureKind.PROVIDER_ERROR


def test_codex_completed_with_nonzero_exit_is_unclassifiable() -> None:
    fixture = _load("codex-exec", "schema-role-result")
    outcome = parse_codex_output(1, _codex_stdout(fixture), _last_agent_message(fixture))
    assert _failure_kind(outcome) is FailureKind.UNCLASSIFIABLE


def test_codex_without_terminal_event_is_unclassifiable() -> None:
    fixture = _load("codex-exec", "schema-role-result")
    events = fixture["events"][:-1]
    stdout = "\n".join(json.dumps(event) for event in events)
    outcome = parse_codex_output(0, stdout, _last_agent_message(fixture))
    assert _failure_kind(outcome) is FailureKind.UNCLASSIFIABLE


def test_codex_event_after_terminal_event_is_unclassifiable() -> None:
    fixture = _load("codex-exec", "schema-role-result")
    stdout = _codex_stdout(fixture) + "\n" + json.dumps({"type": "error", "message": "late"})
    outcome = parse_codex_output(0, stdout, _last_agent_message(fixture))
    assert _failure_kind(outcome) is FailureKind.UNCLASSIFIABLE


@pytest.mark.parametrize("stdout", ["", "\n\n", "not json", "[]", '{"no_type": 1}'])
def test_codex_unclassifiable_stdout(stdout: str) -> None:
    assert _failure_kind(parse_codex_output(0, stdout, "{}")) is FailureKind.UNCLASSIFIABLE


def test_codex_output_file_with_text_around_json_is_not_accepted() -> None:
    fixture = _load("codex-exec", "schema-role-result")
    text = "Here is the result:\n" + (_last_agent_message(fixture) or "")
    outcome = parse_codex_output(0, _codex_stdout(fixture), text)
    assert _failure_kind(outcome) is FailureKind.UNCLASSIFIABLE


def test_codex_schema_violation_is_failure() -> None:
    fixture = _load("codex-exec", "schema-role-result")
    output = json.loads(_last_agent_message(fixture) or "")
    output["status"] = "done"
    output["extra"] = 1
    outcome = parse_codex_output(0, _codex_stdout(fixture), json.dumps(output))
    assert _failure_kind(outcome) is FailureKind.SCHEMA_VIOLATION
    assert outcome.result is None


def test_codex_output_file_must_be_object() -> None:
    fixture = _load("codex-exec", "schema-role-result")
    outcome = parse_codex_output(0, _codex_stdout(fixture), "[]")
    assert _failure_kind(outcome) is FailureKind.SCHEMA_VIOLATION
