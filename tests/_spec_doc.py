"""docs/02-config-spec.md에서 registry JSON, 표, TOML 예시를 꺼내는 도우미."""

import copy
import re
import tomllib
from pathlib import Path
from typing import Any

SPEC = Path(__file__).resolve().parent.parent / "docs" / "02-config-spec.md"


def section(heading: str) -> str:
    text = SPEC.read_text(encoding="utf-8")
    start = text.index(f"\n## {heading}\n") + 1
    end = text.find("\n## ", start + 3)
    return text[start : end if end != -1 else len(text)]


def code_blocks(body: str, lang: str) -> list[str]:
    return re.findall(rf"```{lang}\n(.*?)\n```", body, re.DOTALL)


def registry_table() -> dict[tuple[str, str], str]:
    """'provider registry와 최소 버전' 절의 표에서 (회사, 모델 ID) -> 최소 버전을 읽는다."""
    rows: dict[tuple[str, str], str] = {}
    for line in section("provider registry와 최소 버전").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] in ("Claude", "Codex"):
            rows[(cells[0].lower(), cells[1])] = "unknown" if cells[2] == "미확인" else cells[2]
    return rows


def full_example() -> dict[str, Any]:
    return tomllib.loads(code_blocks(section("예시 전체 설정"), "toml")[0])


def presets() -> dict[str, dict[str, Any]]:
    """프리셋 3종의 providers, agents, roles 묶음. mixed는 전체 예시의 배정이다."""
    claude_only, codex_only, mixed_variant = (
        tomllib.loads(block) for block in code_blocks(section("프리셋 3종"), "toml")
    )
    example = full_example()
    mixed = {key: example[key] for key in ("providers", "agents", "roles")}
    return {
        "claude-only": claude_only,
        "codex-only": codex_only,
        "mixed": mixed,
        "mixed-variant": mixed_variant,
    }


def with_assignment(assignment: dict[str, Any]) -> dict[str, Any]:
    """전체 예시에서 providers, agents, roles만 프리셋 묶음으로 바꾼다."""
    data = copy.deepcopy(full_example())
    for key in ("providers", "agents", "roles"):
        data[key] = copy.deepcopy(assignment[key])
    return data


def extra_example(index: int) -> dict[str, Any]:
    """'추가 명령 예시' 절의 TOML 블록. 0은 prepare, 1은 checks다."""
    return tomllib.loads(code_blocks(section("추가 명령 예시"), "toml")[index])


def effort_lists() -> dict[str, tuple[str, ...]]:
    """'effort 허용 값' 소절의 "- 이름: 값, 값." 목록. 키는 소문자 이름이다."""
    text = SPEC.read_text(encoding="utf-8")
    start = text.index("\n### effort 허용 값\n")
    end = text.find("\n## ", start + 3)
    body = text[start : end if end != -1 else len(text)]
    found = re.findall(r"^- ([\w.-]+): ([a-z, ]+)\.", body, re.MULTILINE)
    return {name.lower(): tuple(v.strip() for v in values.split(",")) for name, values in found}
