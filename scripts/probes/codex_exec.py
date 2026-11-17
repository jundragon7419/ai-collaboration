"""이슈 #4 Codex exec 호출 확인 실험.

실제 codex를 호출하므로 본인 계정의 사용량이 소비된다. 짧은 prompt만 쓴다.
인증 파일과 토큰은 읽지 않는다. 인증 오류 확인은 CODEX_HOME을 빈 임시 폴더로
바꾸고 인증 관련 환경 변수를 뺀 채 실행한다. --ephemeral 확인은 세션 폴더의
파일 개수만 센다. 파일 내용은 읽지 않는다.

실행: python scripts/probes/codex_exec.py [--out 디렉터리] [--only 항목,...]
항목: version, models, sandbox, schema, events, effort, ephemeral, errors
결과: 기본 local-data/probes/codex-exec/<시각>/results.json
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

EFFORTS = ["minimal", "low", "medium", "high", "xhigh", "bogus-effort"]
AUTH_ENV = ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL")
TIMEOUT = 300
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def base_env() -> dict[str, str]:
    """CLI에 넘길 환경. 상속 GIT_*(GIT_DIR, GIT_WORK_TREE, GIT_CONFIG_COUNT 등)를 뺀다.

    CLI가 실험 폴더에서 git을 실행할 때 호출한 쪽 저장소나 외부 Git 설정을 건드리지 않게 한다.
    """
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}


def _as_text(value: object) -> str:
    """TimeoutExpired의 stdout과 stderr는 text=True여도 bytes일 수 있다. 문자열로 맞춘다."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class Recorder:
    def __init__(self, tmp: Path, codex: str) -> None:
        self.tmp = tmp
        self.codex = codex
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
        start = time.monotonic()
        try:
            proc = subprocess.run(
                [self.codex, *args], cwd=cwd, env=env if env is not None else base_env(), input=prompt, capture_output=True, timeout=TIMEOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            res: dict[str, Any] = {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "timed_out": False}
        except subprocess.TimeoutExpired as exc:
            res = {"exit_code": None, "stdout": _as_text(exc.stdout), "stderr": _as_text(exc.stderr), "timed_out": True}
        res["argv"] = ["codex", *[self.anonymize(a) for a in args]]
        res["seconds"] = round(time.monotonic() - start, 3)
        res["stdout"] = self.anonymize(res["stdout"])
        res["stderr"] = self.anonymize(res["stderr"])
        return res


def events(stdout: str) -> list[dict[str, Any]]:
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def summarize(res: dict[str, Any], last_file: Path | None = None) -> dict[str, Any]:
    evs = events(res["stdout"])
    s: dict[str, Any] = {
        "exit_code": res["exit_code"],
        "timed_out": res["timed_out"],
        "seconds": res["seconds"],
        "event_types": [e.get("type") for e in evs],
        "error_events": [e for e in evs if "error" in str(e.get("type", "")) or e.get("type") == "turn.failed"][:5],
        "stdout_head": res["stdout"][:1200] if not evs else None,
        "stderr_tail": res["stderr"][-1500:],
    }
    if last_file is not None:
        s["last_message_file_exists"] = last_file.exists()
        s["last_message"] = last_file.read_text(encoding="utf-8", errors="replace")[:1500] if last_file.exists() else None
    return s


def load_registry_models(repo_root: Path, provider: str) -> list[dict[str, Any]]:
    """docs/02-config-spec.md의 provider registry JSON에서 모델 목록을 읽는다.

    모델 ID와 최소 버전은 registry 한 곳에만 둔다(AGENTS.md). registry 코드(#10)가 생기기 전이라
    문서의 registry 원문을 읽는다. 저장소 루트에서 실행해야 한다.
    """
    doc = repo_root / "docs" / "02-config-spec.md"
    text = doc.read_text(encoding="utf-8")
    start = text.find("## provider registry와 최소 버전")
    m = re.search(r"```json\n(.*?)\n```", text[start:], re.S) if start >= 0 else None
    if not m:
        raise SystemExit("docs/02-config-spec.md에서 provider registry를 찾지 못함. 저장소 루트에서 실행해야 함")
    for entry in json.loads(m.group(1))["providers"]:
        if entry["id"] == provider:
            return list(entry["models"])
    raise SystemExit(f"registry에 {provider} provider가 없음")


def load_role_result_schema(repo_root: Path) -> dict[str, Any] | None:
    doc = repo_root / "docs" / "03-roles-and-handoff.md"
    if not doc.exists():
        return None
    text = doc.read_text(encoding="utf-8")
    start = text.find("## 공통 role-result JSON Schema")
    m = re.search(r"```json\n(.*?)\n```", text[start:], re.S)
    return json.loads(m.group(1)) if m else None


def check_subset(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
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
        errors += [f"{path}.{k}: required" for k in schema.get("required", []) if k not in value]
        if schema.get("additionalProperties") is False:
            errors += [f"{path}.{k}: additional" for k in value if k not in props]
        for k, v in value.items():
            if k in props:
                errors += check_subset(props[k], v, f"{path}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            errors += check_subset(schema["items"], v, f"{path}[{i}]")
    return errors


NOT_ALL_REQUIRED = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer"],
    "properties": {"answer": {"type": "string"}, "extra": {"type": "string"}},
}
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


def count_session_files(codex_home: Path) -> int | None:
    sessions = codex_home / "sessions"
    if not sessions.exists():
        return None
    return sum(len(files) for _, _, files in os.walk(sessions))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--only", default="version,models,sandbox,schema,events,effort,ephemeral,errors")
    parser.add_argument("--codex", default=None, help="codex 실행 파일 경로. 생략하면 PATH에서 찾는다")
    parser.add_argument("--model", default=None, help="sandbox, schema, effort 시험에 쓸 모델. 기본은 models에서 처음 성공한 모델")
    args = parser.parse_args()
    only = set(args.only.split(","))

    # 상대 경로는 실행 위치 기준으로 바꾼다. CLI는 임시 작업 폴더를 cwd로 실행되기 때문이다.
    codex = args.codex or shutil.which("codex")
    if codex and Path(codex).exists():
        codex = str(Path(codex).resolve())
    elif codex:
        codex = shutil.which(codex)
    if not codex:
        print("codex 실행 파일을 찾지 못했습니다.", file=sys.stderr)
        return 2
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out or Path("local-data") / "probes" / "codex-exec" / stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="aicollab-codex-probe-"))
    rec = Recorder(tmp, codex)
    raw: dict[str, Any] = {}
    n = 0

    def workdir() -> Path:
        nonlocal n
        n += 1
        w = tmp / f"ws{n}" / "work"
        w.mkdir(parents=True)
        (w / "readme.txt").write_text("probe workspace\n", encoding="utf-8")
        return w

    def exec_args(work: Path, model: str | None, sandbox: str = "read-only", extra: list[str] | None = None,
                  json_events: bool = True, last: Path | None = None, ephemeral: bool = True) -> list[str]:
        a = ["-a", "never", "--sandbox", sandbox, "exec", "--skip-git-repo-check", "-C", str(work)]
        if ephemeral:
            a.append("--ephemeral")
        if model:
            a += ["-m", model]
        if json_events:
            a.append("--json")
        if last is not None:
            a += ["-o", str(last)]
        a += extra or []
        a.append("-")
        return a

    ver = rec.run(["--version"], tmp)
    env_info = {
        "probe": "codex-exec",
        "issue": 4,
        "started_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "codex_path_kind": Path(codex).suffix or "(확장자 없음)",
        "codex_version": ver["stdout"].strip() or ver["stderr"].strip(),
        "codex_version_stderr": ver["stderr"].strip()[:500],
    }

    if "version" in only:
        h1 = rec.run(["--help"], tmp)
        h2 = rec.run(["exec", "--help"], tmp)
        raw["help"], raw["exec_help"] = h1, h2
        pick = re.compile(r"(-a|--ask-for-approval|--sandbox|-s,|--output-schema|-o,|--output-last-message|--json|--ephemeral|-m,|--model|-c,|--config)\b")
        rec.checks["X0"] = {"title": "버전과 도움말", "observed": {
            "version": env_info["codex_version"],
            "help_lines": [ln.strip() for ln in h1["stdout"].splitlines() if pick.search(ln)],
            "exec_help_lines": [ln.strip() for ln in h2["stdout"].splitlines() if pick.search(ln)],
        }}

    models = [m["id"] for m in load_registry_models(Path.cwd(), "codex")]
    model = args.model
    if "models" in only:
        obs = {}
        for m in models:
            w = workdir()
            last = w.parent / "last.txt"
            r = rec.run(exec_args(w, m, last=last), w, "Reply with exactly: OK")
            raw[f"model_{m}"] = r
            obs[m] = summarize(r, last)
            if model is None and r["exit_code"] == 0:
                model = m
        w = workdir()
        r = rec.run(exec_args(w, "gpt-probe-nonexistent-0"), w, "Reply with exactly: OK")
        raw["model_invalid"] = r
        obs["invalid_model_id"] = summarize(r)
        rec.checks["X1"] = {"title": "모델 ID 4개 지정", "observed": obs}

    if "sandbox" in only:
        obs = {}
        prompt = (
            "Run a shell command that creates the file {inside} with the text hello, "
            "then run a shell command that creates the file {outside} with the text hello. "
            "Report for each whether it succeeded."
        )
        for sandbox in ("read-only", "workspace-write"):
            w = workdir()
            inside = w / "probe-inside.txt"
            # 임시 폴더는 쓰기 허용 경로에 들어갈 수 있어서 바깥 대상은 결과 폴더(임시 폴더 밖)에 둔다.
            outside = (out_dir / f"sandbox-outside-{sandbox}.txt").resolve()
            # 같은 --out으로 다시 실행하면 이전 결과 파일이 남아 있을 수 있다. 시험 전에 지우고 확인한다.
            inside.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)
            if inside.exists() or outside.exists():
                raise SystemExit(f"이전 sandbox 시험 파일을 지우지 못함: {outside.name}")
            r = rec.run(exec_args(w, model, sandbox=sandbox, last=w.parent / "last.txt"), w,
                        prompt.format(inside=inside, outside=outside))
            raw[f"sandbox_{sandbox}"] = r
            s = summarize(r, w.parent / "last.txt")
            s["inside_created"] = inside.exists()
            s["outside_created"] = outside.exists()
            s["outside_target"] = "<결과 폴더>/" + outside.name
            obs[sandbox] = s
        rec.checks["X2"] = {"title": "sandbox read-only와 workspace-write 실제 차단, -a never", "observed": obs, "model": model}

    if "schema" in only:
        obs = {}
        schema = load_role_result_schema(Path.cwd())
        cases: dict[str, tuple[dict[str, Any] | None, str]] = {
            "role_result_schema": (schema, "You are a planner. Produce a minimal role result: kind plan, status completed, summary 'probe'. "
                                           "Fill every other field with empty strings, empty arrays, or not-applicable values."),
            "not_all_required": (NOT_ALL_REQUIRED, "Answer: OK"),
            "extended_keywords": (EXTENDED_SCHEMA, "Return code ABC, email probe@example.com, note null."),
        }
        for name, (sch, prompt) in cases.items():
            if sch is None:
                obs[name] = {"error": "docs/03-roles-and-handoff.md에서 Schema를 찾지 못함. 저장소 루트에서 실행해야 함"}
                continue
            w = workdir()
            sf = w.parent / "schema.json"
            sf.write_text(json.dumps(sch, ensure_ascii=False), encoding="utf-8")
            last = w.parent / "last.txt"
            r = rec.run(exec_args(w, model, last=last, extra=["--output-schema", str(sf)]), w, prompt)
            raw[f"schema_{name}"] = r
            s = summarize(r, last)
            if s.get("last_message"):
                try:
                    parsed = json.loads(last.read_text(encoding="utf-8"))
                    s["last_message_is_json"] = True
                    s["subset_errors"] = check_subset(sch, parsed)
                except ValueError:
                    s["last_message_is_json"] = False
            obs[name] = s
        rec.checks["X3"] = {"title": "--output-schema 엄격 규칙과 -o", "observed": obs, "model": model}

    if "events" in only:
        w = workdir()
        r = rec.run(exec_args(w, model, last=w.parent / "last.txt"), w, "List the files in the current directory, then reply DONE.")
        raw["events"] = r
        evs = events(r["stdout"])
        rec.checks["X4"] = {"title": "--json 이벤트", "observed": {
            "summary": summarize(r, w.parent / "last.txt"),
            "event_key_sets": sorted({",".join(sorted(e.keys())) for e in evs}),
            "item_types": sorted({str((e.get("item") or {}).get("type")) for e in evs if isinstance(e.get("item"), dict)}),
            "non_json_stdout_lines": [ln for ln in r["stdout"].splitlines() if ln.strip() and not ln.strip().startswith("{")][:20],
        }, "model": model}

    if "effort" in only:
        obs = {}
        for effort in EFFORTS:
            w = workdir()
            r = rec.run(exec_args(w, model, extra=["-c", f'model_reasoning_effort="{effort}"']), w, "Reply with exactly: OK")
            raw[f"effort_{effort}"] = r
            obs[effort] = summarize(r)
        rec.checks["X5"] = {"title": "effort 값 이름", "observed": obs, "model": model}

    if "ephemeral" in only:
        home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        obs = {}
        for eph in (True, False):
            before = count_session_files(home)
            w = workdir()
            r = rec.run(exec_args(w, model, ephemeral=eph), w, "Reply with exactly: OK")
            after = count_session_files(home)
            raw[f"ephemeral_{eph}"] = r
            s = summarize(r)
            s["session_files_before"] = before
            s["session_files_after"] = after
            obs["ephemeral" if eph else "not_ephemeral"] = s
        rec.checks["X6"] = {"title": "--ephemeral", "observed": obs, "model": model,
                            "note": "같은 시간에 다른 codex 세션을 쓰면 개수가 섞인다"}

    if "errors" in only:
        env = {k: v for k, v in base_env().items() if k not in AUTH_ENV}
        empty = tmp / "empty-codex-home"
        empty.mkdir()
        env["CODEX_HOME"] = str(empty)
        w = workdir()
        r = rec.run(exec_args(w, model), w, "Reply with exactly: OK", env=env)
        raw["auth_missing"] = r
        rec.checks["X7"] = {"title": "인증 오류 출력 형태", "observed": {
            "auth_missing_empty_codex_home": summarize(r),
            "rate_limit": "한도 오류는 일부러 만들지 않음. 실행 중 발생하면 raw에 남는다.",
        }}

    data = {"environment": env_info, "checks": rec.checks}
    (out_dir / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"결과: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
