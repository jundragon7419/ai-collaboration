"""이슈 #7 prepare 동작 확인 실험.

임시 디렉터리에 작은 Python 프로젝트와 Node 프로젝트를 만들고, 새 worktree에서
uv sync와 npm ci를 실행해 source와 lock, 의존성 산출물의 전후 상태를 기록한다.
패키지 레지스트리(PyPI, npm registry) 네트워크가 필요하다. 사용자 저장소와 전역
Git 설정은 바꾸지 않는다.

실행: python scripts/probes/prepare_behavior.py [--out 디렉터리]
결과: 기본 local-data/probes/prepare-behavior/<시각>/results.json
표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
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

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__"}
LOCK_FILES = ("uv.lock", "package-lock.json")
TAIL = 4000


class Recorder:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.checks: dict[str, dict[str, Any]] = {}

    def anonymize(self, text: str) -> str:
        pairs = []
        for base in (self.tmp, Path.home()):
            label = "<TMP>" if base == self.tmp else "<HOME>"
            for variant in {str(base), str(base).replace("\\", "/")}:
                pairs.append((variant, label))
            try:
                real = str(base.resolve())
                pairs.insert(0, (real.replace("\\", "/"), label))
                pairs.insert(0, (real, label))
            except OSError:
                pass
        for old, new in pairs:
            text = text.replace(old, new)
        # npm debug log 경로에는 사용자 홈이 들어간다.
        return re.sub(r"\S*[\\/]_logs[\\/]\S+", "<NPM_LOG>", text)

    def run(self, argv: list[str], cwd: Path, env: dict[str, str], timeout: float = 600) -> dict[str, Any]:
        start = time.monotonic()
        try:
            proc = subprocess.run(
                argv, cwd=cwd, env=env, capture_output=True, timeout=timeout,
                text=True, encoding="utf-8", errors="replace",
            )
            res: dict[str, Any] = {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "timed_out": False}
        except subprocess.TimeoutExpired as exc:
            res = {"exit_code": None, "stdout": str(exc.stdout or ""), "stderr": str(exc.stderr or ""), "timed_out": True}
        except FileNotFoundError as exc:
            res = {"exit_code": None, "stdout": "", "stderr": str(exc), "timed_out": False, "not_found": True}
        res["argv"] = [self.anonymize(Path(argv[0]).name if i == 0 else a) for i, a in enumerate(argv)]
        res["cwd"] = self.anonymize(str(cwd))
        res["seconds"] = round(time.monotonic() - start, 3)
        res["stdout"] = self.anonymize(res["stdout"])[-TAIL:]
        res["stderr"] = self.anonymize(res["stderr"])[-TAIL:]
        return res

    def add(self, check_id: str, title: str, observed: dict[str, Any]) -> None:
        self.checks[check_id] = {"title": title, "observed": observed}


def tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"{name}을 찾지 못함")
    return found


def git_env(tmp: Path) -> dict[str, str]:
    env = dict(os.environ)
    cfg = tmp / "isolated-global.gitconfig"
    if not cfg.exists():
        cfg.write_text(
            "[user]\n\tname = Probe User\n\temail = probe@example.invalid\n"
            "[init]\n\tdefaultBranch = main\n[core]\n\tautocrlf = false\n",
            encoding="utf-8",
        )
    env["GIT_CONFIG_GLOBAL"] = str(cfg)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def snapshot(root: Path) -> dict[str, str]:
    """의존성 산출물과 .git을 뺀 파일의 sha256."""
    result: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            result[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def diff(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "modified": sorted(k for k in set(before) & set(after) if before[k] != after[k]),
    }


def dep_dir_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    count = 0
    top = sorted(p.name for p in path.iterdir())[:20]
    for _, _, files in os.walk(path):
        count += len(files)
    return {"exists": True, "file_count": count, "top_entries": top}


def venv_has(worktree: Path, module: str) -> bool:
    for site in worktree.glob(".venv/lib/python*/site-packages"):
        if (site / module).exists() or any(site.glob(f"{module}*")):
            return True
    site = worktree / ".venv" / "Lib" / "site-packages"
    return site.exists() and ((site / module).exists() or any(site.glob(f"{module}*")))


class Repo:
    def __init__(self, rec: Recorder, path: Path, env: dict[str, str]) -> None:
        self.rec, self.path, self.env = rec, path, env
        self.count = 0

    def git(self, *args: str, cwd: Path | None = None) -> dict[str, Any]:
        return self.rec.run(["git", *args], cwd or self.path, self.env)

    def init(self) -> None:
        self.path.mkdir(parents=True)
        self.git("init", "-q", "-b", "main", str(self.path))
        write(self.path / ".gitignore", ".venv/\nnode_modules/\n__pycache__/\n")
        write(self.path / "src.txt", "source\n")

    def commit(self, msg: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)
        return self.git("rev-parse", "HEAD")["stdout"].strip()

    def worktree(self, rev: str) -> Path:
        self.count += 1
        wt = self.path.parent / f"wt{self.count}"
        self.git("worktree", "add", "-q", "--detach", str(wt), rev)
        return wt


def measure(rec: Recorder, wt: Path, argv: list[str], env: dict[str, str], dep_dir: str, before_hook: Any = None) -> dict[str, Any]:
    if before_hook:
        before_hook(wt)
    before = snapshot(wt)
    dep_before = dep_dir_summary(wt / dep_dir)
    res = rec.run(argv, wt, env)
    after = snapshot(wt)
    status = rec.run(["git", "status", "--porcelain", "--ignored"], wt, env)
    return {
        "command": res["argv"],
        "exit_code": res["exit_code"],
        "seconds": res["seconds"],
        "stdout_tail": res["stdout"],
        "stderr_tail": res["stderr"],
        "source_diff": diff(before, after),
        "lock_changed": {f: before.get(f) != after.get(f) for f in LOCK_FILES if f in before or f in after},
        "dependency_dir_before": dep_before,
        "dependency_dir_after": dep_dir_summary(wt / dep_dir),
        "git_status_ignored": status["stdout"].strip().splitlines(),
    }


PYPROJECT = """[project]
name = "probe-app"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [{deps}]

[tool.uv]
package = false
"""


def probe_uv(rec: Recorder, tmp: Path) -> None:
    uv = tool("uv")
    genv = git_env(tmp)
    env = dict(genv)
    env.setdefault("UV_NO_PROGRESS", "1")
    repo = Repo(rec, tmp / "uv" / "repo", genv)
    repo.init()
    write(repo.path / "pyproject.toml", PYPROJECT.format(deps='"six==1.16.0"'))
    no_lock = repo.commit("no lock")
    lock_res = rec.run([uv, "lock"], repo.path, env)
    with_lock = repo.commit("with lock")

    obs: dict[str, Any] = {"uv_lock_create_exit": lock_res["exit_code"]}

    wt = repo.worktree(with_lock)
    obs["U1_sync_with_lock"] = measure(rec, wt, [uv, "sync"], env, ".venv")
    obs["U1_sync_with_lock"]["six_installed"] = venv_has(wt, "six")
    obs["U1b_sync_again"] = measure(rec, wt, [uv, "sync"], env, ".venv")

    wt = repo.worktree(no_lock)
    obs["U2_sync_without_lock"] = measure(rec, wt, [uv, "sync"], env, ".venv")
    wt = repo.worktree(no_lock)
    obs["U2b_sync_locked_without_lock"] = measure(rec, wt, [uv, "sync", "--locked"], env, ".venv")

    # manifest와 lock 불일치: lock은 그대로 두고 의존성을 추가한 commit
    write(repo.path / "pyproject.toml", PYPROJECT.format(deps='"six==1.16.0", "idna==3.7"'))
    mismatch = repo.commit("manifest changed without relock")
    wt = repo.worktree(mismatch)
    obs["U3_sync_mismatch"] = measure(rec, wt, [uv, "sync"], env, ".venv")
    wt = repo.worktree(mismatch)
    obs["U3b_sync_locked_mismatch"] = measure(rec, wt, [uv, "sync", "--locked"], env, ".venv")
    wt = repo.worktree(mismatch)
    obs["U3c_sync_frozen_mismatch"] = measure(rec, wt, [uv, "sync", "--frozen"], env, ".venv")

    # 설치 중 실패: 정상 패키지와 build가 실패하는 로컬 패키지를 함께 둔다.
    broken = tmp / "uv" / "broken-pkg"
    write(broken / "pyproject.toml", '[build-system]\nrequires = ["setuptools>=61"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "broken-pkg"\nversion = "0.0.1"\n')
    write(broken / "setup.py", 'raise SystemExit("probe: intentional build failure")\n')
    write(repo.path / "pyproject.toml", PYPROJECT.format(deps=f'"six==1.16.0", "broken-pkg @ {broken.as_uri()}"'))
    lock_broken = rec.run([uv, "lock"], repo.path, env)
    failing = repo.commit("broken dependency")
    obs["U4_lock_with_broken_exit"] = lock_broken["exit_code"]
    obs["U4_lock_with_broken_stderr"] = lock_broken["stderr"]
    wt = repo.worktree(failing)
    obs["U4_sync_build_failure"] = measure(rec, wt, [uv, "sync"], env, ".venv")
    obs["U4_sync_build_failure"]["six_installed_after_failure"] = venv_has(wt, "six")

    # 존재하지 않는 패키지
    write(repo.path / "pyproject.toml", PYPROJECT.format(deps='"aicollab-probe-nonexistent-package-zz==9.9.9"'))
    missing = repo.commit("missing dependency")
    wt = repo.worktree(missing)
    obs["U5_sync_missing_package"] = measure(rec, wt, [uv, "sync"], env, ".venv")

    rec.add("UV", "uv sync", obs)


def npm_script(code: str) -> str:
    return "node -e " + json.dumps(code)


def probe_npm(rec: Recorder, tmp: Path) -> None:
    npm = tool("npm")
    genv = git_env(tmp)
    env = dict(genv)
    env["npm_config_fund"] = "false"
    env["npm_config_audit"] = "false"
    env["npm_config_update_notifier"] = "false"
    repo = Repo(rec, tmp / "npm" / "repo", genv)
    repo.init()

    def package(deps: dict[str, str], scripts: dict[str, str] | None = None) -> None:
        data: dict[str, Any] = {"name": "probe-app", "version": "0.1.0", "private": True, "dependencies": deps}
        if scripts:
            data["scripts"] = scripts
        write(repo.path / "package.json", json.dumps(data, indent=2) + "\n")

    package({"is-number": "7.0.0"})
    no_lock = repo.commit("no lock")
    lock_res = rec.run([npm, "install", "--package-lock-only"], repo.path, env)
    with_lock = repo.commit("with lock")
    obs: dict[str, Any] = {"package_lock_only_exit": lock_res["exit_code"]}

    wt = repo.worktree(with_lock)
    obs["N1_ci_with_lock"] = measure(rec, wt, [npm, "ci"], env, "node_modules")

    def marker(w: Path) -> None:
        write(w / "node_modules" / "probe-marker.txt", "existing\n")

    wt = repo.worktree(with_lock)
    obs["N1b_ci_removes_existing_node_modules"] = measure(rec, wt, [npm, "ci"], env, "node_modules", before_hook=marker)
    obs["N1b_ci_removes_existing_node_modules"]["marker_left"] = (wt / "node_modules" / "probe-marker.txt").exists()

    wt = repo.worktree(no_lock)
    obs["N2_ci_without_lock"] = measure(rec, wt, [npm, "ci"], env, "node_modules")

    package({"is-number": "7.0.0", "is-odd": "3.0.1"})
    mismatch = repo.commit("manifest changed without relock")
    wt = repo.worktree(mismatch)
    obs["N3_ci_mismatch"] = measure(rec, wt, [npm, "ci"], env, "node_modules")

    # 루트 lifecycle script가 source를 바꾸는 경우
    package(
        {"is-number": "7.0.0"},
        {
            "preinstall": npm_script("require('fs').appendFileSync('src.txt','preinstall\\n')"),
            "postinstall": npm_script("require('fs').appendFileSync('src.txt','postinstall\\n');require('fs').writeFileSync('generated.txt','x\\n')"),
            "prepare": npm_script("require('fs').appendFileSync('src.txt','prepare\\n')"),
        },
    )
    rec.run([npm, "install", "--package-lock-only", "--ignore-scripts"], repo.path, env)
    scripts_rev = repo.commit("lifecycle scripts")
    wt = repo.worktree(scripts_rev)
    obs["N4_ci_lifecycle_scripts"] = measure(rec, wt, [npm, "ci"], env, "node_modules")
    obs["N4_ci_lifecycle_scripts"]["src_txt_after"] = (wt / "src.txt").read_text(encoding="utf-8")

    # 설치 뒤 실패: postinstall이 실패
    package({"is-number": "7.0.0"}, {"postinstall": npm_script("process.exit(7)")})
    rec.run([npm, "install", "--package-lock-only", "--ignore-scripts"], repo.path, env)
    fail_rev = repo.commit("failing postinstall")
    wt = repo.worktree(fail_rev)
    obs["N5_ci_postinstall_failure"] = measure(rec, wt, [npm, "ci"], env, "node_modules")
    obs["N5_ci_postinstall_failure"]["is_number_present"] = (wt / "node_modules" / "is-number").exists()

    # 존재하지 않는 패키지 버전이 lock에 있는 경우: lock을 직접 고친다.
    package({"is-number": "7.0.0"})
    rec.run([npm, "install", "--package-lock-only"], repo.path, env)
    lock_path = repo.path / "package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    entry = lock.get("packages", {}).get("node_modules/is-number")
    if entry:
        entry["resolved"] = "https://registry.npmjs.org/is-number/-/is-number-99.99.99.tgz"
        entry.pop("integrity", None)
    write(lock_path, json.dumps(lock, indent=2) + "\n")
    bad_rev = repo.commit("bad resolved url")
    wt = repo.worktree(bad_rev)
    obs["N6_ci_download_failure"] = measure(rec, wt, [npm, "ci"], env, "node_modules")

    rec.add("NPM", "npm ci", obs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--only", choices=["uv", "npm"], default=None)
    parser.add_argument("--keep-tmp", action="store_true")
    args = parser.parse_args()

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out or Path("local-data") / "probes" / "prepare-behavior" / stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="aicollab-prepare-probe-"))
    rec = Recorder(tmp)

    def version(argv: list[str]) -> str:
        found = shutil.which(argv[0])
        if not found:
            return "없음"
        r = rec.run([found, *argv[1:]], tmp, dict(os.environ))
        return (r["stdout"] or r["stderr"]).strip().splitlines()[0] if (r["stdout"] or r["stderr"]).strip() else ""

    env_info = {
        "probe": "prepare-behavior",
        "issue": 7,
        "started_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "git": version(["git", "--version"]),
        "uv": version(["uv", "--version"]),
        "node": version(["node", "--version"]),
        "npm": version(["npm", "--version"]),
    }
    errors = {}
    probes = {"uv": probe_uv, "npm": probe_npm}
    for name, fn in probes.items():
        if args.only and args.only != name:
            continue
        try:
            fn(rec, tmp)
        except Exception as exc:  # 실험 하나가 실패해도 나머지를 기록한다.
            errors[name] = repr(exc)
    data = {"environment": env_info, "checks": rec.checks, "script_errors": errors}
    (out_dir / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.keep_tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"결과: {out_dir / 'results.json'}")
    if errors:
        print(f"스크립트 오류: {errors}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
