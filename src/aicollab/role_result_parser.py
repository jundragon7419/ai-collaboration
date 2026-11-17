"""Claude Code와 Codex CLI의 출력에서 role-result를 꺼내는 파서.

판정은 두 CLI가 구조화 필드로 알려 주는 값만 쓴다. 모델 응답이나 오류 메시지의 문장은
읽지 않는다(AGENTS.md). 분류할 수 없는 출력, 결과 누락, Schema 위반은 모두 실패다.

- Claude: exit code, `is_error`, `terminal_reason`으로 판정하고 `structured_output`에서 읽는다.
  `result` 문자열로 대신 읽지 않는다. 오류에서도 `subtype`은 `success`이므로 보지 않는다.
- Codex: `--json` 이벤트의 마지막 `turn.completed`/`turn.failed`로 판정하고 `-o` 파일에서 읽는다.
  실패한 turn은 `-o` 파일을 만들지 않는다.

인증 오류는 두 CLI 모두 구조화된 구분 필드가 없다(docs/02-config-spec.md). 그래서 별도 종류로
나누지 않고 `provider-error`에 포함한다. 문장으로 구분할지는 이슈에서 결정한다.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from aicollab.role_result_schema import validate_role_result

# Claude `terminal_reason`에서 성공으로 관측된 값. 그 밖의 값은 의미를 알 수 없어 실패로 둔다.
_CLAUDE_SUCCESS_TERMINAL_REASON = "completed"


class FailureKind(StrEnum):
    # CLI가 구조화 필드로 실패를 알렸다(Claude `is_error`, Codex `turn.failed`).
    PROVIDER_ERROR = "provider-error"
    # 출력 모양이 기대와 다르거나 신호가 서로 어긋나 성공과 실패를 정할 수 없다.
    UNCLASSIFIABLE = "unclassifiable"
    # 성공으로 보이지만 결과 위치에 결과가 없다.
    MISSING_RESULT = "missing-result"
    # 결과가 role-result Schema를 어긴다.
    SCHEMA_VIOLATION = "schema-violation"


@dataclass(frozen=True)
class ParseFailure:
    kind: FailureKind
    # 사람이 보는 진단 문장. 판정에 쓰지 않는다.
    detail: str
    # Claude `api_error_status`. 값이 없거나 Codex면 None.
    api_error_status: int | None = None


@dataclass(frozen=True)
class ParseOutcome:
    # 성공이면 Schema를 통과한 role-result, 실패면 None.
    result: dict[str, Any] | None
    failure: ParseFailure | None

    @property
    def ok(self) -> bool:
        return self.failure is None


def _fail(kind: FailureKind, detail: str, api_error_status: int | None = None) -> ParseOutcome:
    return ParseOutcome(None, ParseFailure(kind, detail, api_error_status))


def _check_schema(candidate: object) -> ParseOutcome:
    errors = validate_role_result(candidate)
    if errors:
        shown = "; ".join(errors[:5])
        extra = f" (외 {len(errors) - 5}건)" if len(errors) > 5 else ""
        return _fail(FailureKind.SCHEMA_VIOLATION, shown + extra)
    assert isinstance(candidate, dict)
    return ParseOutcome(candidate, None)


def parse_claude_output(exit_code: int, stdout: str) -> ParseOutcome:
    """`claude -p --output-format json --json-schema ...`의 exit code와 stdout을 해석한다."""
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return _fail(FailureKind.UNCLASSIFIABLE, f"stdout이 JSON이 아니다: {exc.msg}")
    if not isinstance(envelope, dict) or envelope.get("type") != "result":
        return _fail(FailureKind.UNCLASSIFIABLE, "stdout이 type=result JSON 객체가 아니다")

    is_error = envelope.get("is_error")
    terminal_reason = envelope.get("terminal_reason")
    if not isinstance(is_error, bool) or not isinstance(terminal_reason, str):
        return _fail(
            FailureKind.UNCLASSIFIABLE, "is_error 또는 terminal_reason이 없거나 형식이 다르다"
        )

    status = envelope.get("api_error_status")
    api_error_status = status if isinstance(status, int) and not isinstance(status, bool) else None

    if is_error:
        return _fail(
            FailureKind.PROVIDER_ERROR,
            f"is_error=true, terminal_reason={terminal_reason}, exit_code={exit_code}",
            api_error_status,
        )
    if exit_code != 0:
        return _fail(
            FailureKind.UNCLASSIFIABLE,
            f"exit_code={exit_code}인데 is_error=false다",
            api_error_status,
        )
    if terminal_reason != _CLAUDE_SUCCESS_TERMINAL_REASON:
        return _fail(
            FailureKind.UNCLASSIFIABLE,
            f"알 수 없는 terminal_reason={terminal_reason}",
            api_error_status,
        )

    if "structured_output" not in envelope or envelope["structured_output"] is None:
        return _fail(FailureKind.MISSING_RESULT, "structured_output이 없다")
    return _check_schema(envelope["structured_output"])


def _parse_codex_events(stdout: str) -> list[Mapping[str, Any]] | None:
    events: list[Mapping[str, Any]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            return None
        events.append(event)
    return events


def parse_codex_output(exit_code: int, stdout: str, output_file: str | None) -> ParseOutcome:
    """`codex exec --json -o <파일> --output-schema ...`의 exit code, stdout, `-o` 파일을 해석한다.

    output_file은 `-o` 파일의 내용이다. 파일이 없으면 None을 넘긴다.
    """
    events = _parse_codex_events(stdout)
    if events is None:
        return _fail(FailureKind.UNCLASSIFIABLE, "stdout에 JSON 이벤트가 아닌 줄이 있다")
    if not events:
        return _fail(FailureKind.UNCLASSIFIABLE, "이벤트가 없다")

    terminal = events[-1]
    terminal_type = terminal["type"]
    if terminal_type == "turn.failed":
        return _fail(FailureKind.PROVIDER_ERROR, f"turn.failed, exit_code={exit_code}")
    if terminal_type != "turn.completed":
        return _fail(
            FailureKind.UNCLASSIFIABLE,
            f"마지막 이벤트가 turn.completed나 turn.failed가 아니다: {terminal_type}",
        )
    if exit_code != 0:
        return _fail(
            FailureKind.UNCLASSIFIABLE, f"exit_code={exit_code}인데 turn.completed로 끝났다"
        )

    if output_file is None:
        return _fail(FailureKind.MISSING_RESULT, "-o 파일이 없다")
    try:
        candidate = json.loads(output_file)
    except json.JSONDecodeError as exc:
        return _fail(FailureKind.UNCLASSIFIABLE, f"-o 파일이 JSON이 아니다: {exc.msg}")
    return _check_schema(candidate)
