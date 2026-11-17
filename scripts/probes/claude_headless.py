"""이슈 #3 Claude Code 비대화형 호출 확인 실험.

실제 claude를 호출하므로 본인 계정의 사용량이 소비된다. 짧은 prompt만 쓴다.
인증 파일과 토큰은 읽지 않는다. 인증 오류 확인은 CLAUDE_CONFIG_DIR을 빈 임시
폴더로 바꾸고 인증 관련 환경 변수를 뺀 채 실행한다.

실행: python scripts/probes/claude_headless.py [--out 디렉터리] [--only 항목,...]
항목: version, models, tools, schema, errors, effort
결과: 기본 local-data/probes/claude-headless/<시각>/results.json
저장소 루트에서 실행한다. docs/03-roles-and-handoff.md의 role-result Schema를 읽는다.
표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

MODELS = ["claude-opus-5-5", "claude-fable-5-2", "claude-sonnet-5-5", "claude-haiku-5-5"]
MIN_VERSION = {
    "claude-opus-5-5": "2.1.280",
    "claude-fable-5-2": "2.1.321",
    "claude-sonnet-5-5": "2.1.284",
    "claude-haiku-5-5": "2.1.293",
}
CHEAP_ORDER = ["claude-haiku-5-5", "claude-sonnet-5-5"]
EFFORTS = ["low", "medium", "high", "xhigh", "max", "bogus-effort"]
AUTH_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL")
TIMEOUT = 240

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def version_tuple(text: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(x) for x in m.groups()) if m else ()


class Recorder:
    def __init__(self, tmp: Path, claude: str) -> None:
        self.tmp = tmp
        self.claude = claude
        self.checks: dict[str, Any] = {}

    def anonymize(self, text: str) -> str:
        pairs: list[tuple[str, str]] = []
        for base, label in ((self.tmp, "<TMP>"), (Path.home(), "<HOME>")):
            for p in {str(base), str(base).replace("\\", "/"), str(base).replace("\\", "\\\\")}:
                pairs.append((p, label))
        pairs.sort(key=lambda x: -len(x[0]))
        for old, new in pairs:
            text = text.replace(old, new)
        return UUID_RE.sub("<UUID>", text)

    def run(self, args: list[str], cwd: Path, prompt: str | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
        argv = [self.claude, *args]
        start = time.monotonic()
        try:
            proc = subprocess.run(
                argv, cwd=cwd, env=env, input=prompt, capture_output=True, timeout=TIMEOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            res: dict[str, Any] = {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "timed_out": False}
        except subprocess.TimeoutExpired as exc:
            res = {"exit_code": None, "stdout": str(exc.stdout or ""), "stderr": str(exc.stderr or ""), "timed_out": True}
        res["argv"] = ["claude", *[self.anonymize(a) if len(a) < 300 else "<긴 인자 생략>" for a in args]]
        res["seconds"] = round(time.monotonic() - start, 3)
        res["stdout"] = self.anonymize(res["stdout"])
        res["stderr"] = self.anonymize(res["stderr"])
        try:
            res["json"] = json.loads(res["stdout"])
        except ValueError:
            res["json"] = None
        return res


def summarize(res: dict[str, Any]) -> dict[str, Any]:
    j = res.get("json") if isinstance(res.get("json"), dict) else {}
    usage = j.get("modelUsage") if isinstance(j, dict) else None
    return {
        "exit_code": res["exit_code"],
        "timed_out": res["timed_out"],
        "seconds": res["seconds"],
        "json_keys": sorted(j.keys()) if j else [],
        "type": j.get("type") if j else None,
        "subtype": j.get("subtype") if j else None,
        "is_error": j.get("is_error") if j else None,
        "result_head": (j.get("result") or "")[:300] if j and isinstance(j.get("result"), str) else None,
        "model_usage_models": sorted(usage.keys()) if isinstance(usage, dict) else None,
        "permission_denials": j.get("permission_denials") if j else None,
        "stdout_head": None if j else res["stdout"][:1500],
        "stderr_head": res["stderr"][:1500],
    }


def load_role_result_schema(repo_root: Path) -> dict[str, Any] | None:
    doc = repo_root / "docs" / "03-roles-and-handoff.md"
    if not doc.exists():
        return None
    text = doc.read_text(encoding="utf-8")
    start = text.find("## 공통 role-result JSON Schema")
    m = re.search(r"```json\n(.*?)\n```", text[start:], re.S)
    return json.loads(m.group(1)) if m else None


def check_subset(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
    """문서가 쓰는 부분집합(type, enum, required, additionalProperties, properties, items)만 검사한다."""
    errors: list[str] = []
    types = schema.get("type")
    types = types if isinstance(types, list) else [types] if types else []
    py = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None), "number": (int, float)}
    if types and not any(isinstance(value, py[t]) and not (t == "integer" and isinstance(value, bool)) for t in types):
        return [f"{path}: type {types}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: enum")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required")
        if schema.get("additionalProperties") is False:
            errors += [f"{path}.{k}: additional" for k in value if k not in props]
        for k, v in value.items():
            if k in props:
                errors += check_subset(props[k], v, f"{path}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            errors += check_subset(schema["items"], v, f"{path}[{i}]")
    return errors


EXTENDED_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["code", "email", "note"],
    "properties": {
        "code": {"type": "string", "pattern": "^[A-Z]{3}$", "minLength": 3, "maxLength": 3},
        "email": {"type": "string", "format": "email"},
        "note": {"type": ["string", "null"]},
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--only", default="version,models,tools,schema,errors,effort")
    args = parser.parse_args()
    only = set(args.only.split(","))

    claude = shutil.which("claude")
    if not claude:
        print("claude 실행 파일을 찾지 못했습니다.", file=sys.stderr)
        return 2
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out or Path("local-data") / "probes" / "claude-headless" / stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="aicollab-claude-probe-"))
    rec = Recorder(tmp, claude)
    raw: dict[str, Any] = {}
    work = tmp / "work"
    work.mkdir()
    (work / "readme.txt").write_text("probe workspace\n", encoding="utf-8")

    base = ["-p", "--output-format", "json", "--no-session-persistence"]
    ver = rec.run(["--version"], tmp)
    cli_version = ver["stdout"].strip()
    env_info = {
        "probe": "claude-headless",
        "issue": 3,
        "started_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "claude_path_kind": Path(claude).suffix or "(확장자 없음)",
        "claude_version": cli_version,
    }

    if "version" in only:
        help_ = rec.run(["--help"], tmp)
        raw["help"] = help_
        lines = [ln.strip() for ln in help_["stdout"].splitlines() if re.search(r"--(effort|tools|allowedTools|json-schema|output-format|no-session-persistence|model|max-turns|permission-mode)\b", ln)]
        rec.checks["C0"] = {"title": "버전과 도움말", "observed": {"version": cli_version, "help_lines": lines}}

    working_cheap: str | None = None
    if "models" in only:
        obs = {}
        for model in MODELS:
            meets = version_tuple(cli_version) >= version_tuple(MIN_VERSION[model]) if version_tuple(cli_version) else None
            r = rec.run([*base, "--model", model], work, "Reply with exactly: OK")
            raw[f"model_{model}"] = r
            s = summarize(r)
            s["min_cli_version"] = MIN_VERSION[model]
            s["installed_meets_min"] = meets
            obs[model] = s
        for model in CHEAP_ORDER:
            s = obs[model]
            if s["exit_code"] == 0 and not s["is_error"]:
                working_cheap = model
                break
        bad = rec.run([*base, "--model", "claude-probe-nonexistent-0"], work, "Reply with exactly: OK")
        raw["model_invalid"] = bad
        obs["invalid_model_id"] = summarize(bad)
        rec.checks["C1"] = {"title": "전체 모델 ID 4개 지정", "observed": obs}
    cheap = working_cheap or "claude-haiku-5-5"

    if "tools" in only:
        obs = {}
        prompt = (
            "Create a file named {name} in the current directory containing the word hello. "
            "Use any tool you have (Write, Edit, Bash). If no tool can do it, reply exactly: CANNOT"
        )
        cases = {
            "read_only_tools": ["--tools", "Read,Glob,Grep"],
            "write_listed_not_allowed": ["--tools", "Read,Glob,Grep,Write"],
            "bash_listed_not_allowed": ["--tools", "Read,Bash"],
            "control_write_allowed": ["--tools", "Read,Write", "--allowedTools", "Write"],
        }
        for name, extra in cases.items():
            target = f"probe-{name}.txt"
            r = rec.run([*base, "--model", cheap, *extra], work, prompt.format(name=target))
            raw[f"tools_{name}"] = r
            s = summarize(r)
            s["file_created"] = (work / target).exists()
            obs[name] = s
        rec.checks["C2"] = {"title": "--tools로 쓰기 도구와 Bash 제외", "observed": obs, "model": cheap}

    if "schema" in only:
        obs = {}
        schema = load_role_result_schema(Path.cwd())
        if schema is None:
            obs["error"] = "docs/03-roles-and-handoff.md에서 Schema를 찾지 못함. 저장소 루트에서 실행해야 함"
        else:
            r = rec.run(
                [*base, "--model", cheap, "--json-schema", json.dumps(schema, ensure_ascii=False)],
                work,
                "You are a planner. Produce a minimal role result: kind plan, status completed, "
                "summary 'probe'. Fill every other field with empty strings, empty arrays, or not-applicable values.",
            )
            raw["schema_role_result"] = r
            s = summarize(r)
            j = r.get("json") or {}
            so = j.get("structured_output") if isinstance(j, dict) else None
            s["structured_output_present"] = so is not None
            s["structured_output_subset_errors"] = check_subset(schema, so) if so is not None else None
            obs["role_result_schema"] = s
        r = rec.run(
            [*base, "--model", cheap, "--json-schema", json.dumps(EXTENDED_SCHEMA)],
            work,
            "Return code ABC, email probe@example.com, note null.",
        )
        raw["schema_extended"] = r
        s = summarize(r)
        j = r.get("json") or {}
        s["structured_output"] = j.get("structured_output") if isinstance(j, dict) else None
        obs["extended_keywords_schema"] = s
        rec.checks["C3"] = {"title": "--json-schema 출력과 Schema 공통 부분집합 수락", "observed": obs, "model": cheap}

    if "errors" in only:
        obs = {}
        env = {k: v for k, v in os.environ.items() if k not in AUTH_ENV}
        empty = tmp / "empty-config"
        empty.mkdir()
        env["CLAUDE_CONFIG_DIR"] = str(empty)
        r = rec.run([*base, "--model", cheap], work, "Reply with exactly: OK", env=env)
        raw["auth_missing"] = r
        obs["auth_missing_empty_config_dir"] = summarize(r)
        obs["rate_limit"] = "한도 오류는 일부러 만들지 않음. 실행 중 발생하면 raw에 남는다."
        rec.checks["C4"] = {"title": "한도와 인증 오류 출력 형태", "observed": obs}

    if "effort" in only:
        obs = {}
        effort_model = cheap
        for effort in EFFORTS:
            r = rec.run([*base, "--model", effort_model, "--effort", effort], work, "Reply with exactly: OK")
            raw[f"effort_{effort}"] = r
            obs[effort] = summarize(r)
        rec.checks["C5"] = {"title": "--effort 값", "observed": obs, "model": effort_model}

    data = {"environment": env_info, "checks": rec.checks}
    (out_dir / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"결과: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
