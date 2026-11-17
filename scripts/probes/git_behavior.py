"""이슈 #6 Git 동작 확인 실험.

임시 디렉터리에 저장소를 새로 만들어 worktree, hooks, tree 비교, 서명 설정,
변경 없음 판정, push lease, gh pr create 도움말을 확인한다. 사용자 저장소와
전역 Git 설정은 바꾸지 않는다. 실험용 Git 명령은 GIT_CONFIG_GLOBAL을 임시
파일로 바꾸고 GIT_CONFIG_NOSYSTEM=1로 실행한다.

실행: python scripts/probes/git_behavior.py [--out 디렉터리]
결과: 기본 local-data/probes/git-behavior/<시각>/results.json
표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

IS_WINDOWS = os.name == "nt"


class Recorder:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.checks: dict[str, dict[str, Any]] = {}

    def anonymize(self, text: str) -> str:
        replacements = [
            (str(self.tmp), "<TMP>"),
            (str(self.tmp).replace("\\", "/"), "<TMP>"),
            (str(Path.home()), "<HOME>"),
            (str(Path.home()).replace("\\", "/"), "<HOME>"),
        ]
        try:
            real = str(self.tmp.resolve())
            replacements.insert(0, (real, "<TMP>"))
            replacements.insert(1, (real.replace("\\", "/"), "<TMP>"))
        except OSError:
            pass
        for old, new in replacements:
            if old:
                text = text.replace(old, new)
        return text

    def run(
        self,
        argv: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float = 60,
        stdin: str | None = None,
    ) -> dict[str, Any]:
        start = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                env=env,
                input=stdin,
                capture_output=True,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            result = {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            result = {
                "exit_code": None,
                "stdout": exc.stdout if isinstance(exc.stdout, str) else "",
                "stderr": exc.stderr if isinstance(exc.stderr, str) else "",
                "timed_out": True,
            }
        except FileNotFoundError as exc:
            result = {"exit_code": None, "stdout": "", "stderr": str(exc), "timed_out": False, "not_found": True}
        result["argv"] = [self.anonymize(a) for a in argv]
        result["cwd"] = self.anonymize(str(cwd))
        result["seconds"] = round(time.monotonic() - start, 3)
        result["stdout"] = self.anonymize(result["stdout"] or "")
        result["stderr"] = self.anonymize(result["stderr"] or "")
        return result

    def add(self, check_id: str, title: str, steps: list[dict[str, Any]], observed: dict[str, Any]) -> None:
        self.checks[check_id] = {"title": title, "observed": observed, "steps": steps}


def isolated_env(tmp: Path) -> dict[str, str]:
    env = dict(os.environ)
    global_cfg = tmp / "isolated-global.gitconfig"
    if not global_cfg.exists():
        global_cfg.write_text(
            "[user]\n\tname = Probe User\n\temail = probe@example.invalid\n"
            "[init]\n\tdefaultBranch = main\n[core]\n\tautocrlf = false\n",
            encoding="utf-8",
        )
    env["GIT_CONFIG_GLOBAL"] = str(global_cfg)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(key, None)
    return env


def write(path: Path, text: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)


def write_hook(repo_git_dir: Path, name: str, body: str) -> None:
    hook = repo_git_dir / "hooks" / name
    write(hook, "#!/bin/sh\n" + body)
    hook.chmod(0o755)


def init_repo(rec: Recorder, path: Path, env: dict[str, str]) -> list[dict[str, Any]]:
    path.mkdir(parents=True)
    steps = [rec.run(["git", "init", "-q", "-b", "main", str(path)], path, env)]
    write(path / ".gitattributes", "* text=auto eol=lf\n")
    write(path / ".gitignore", "node_modules/\n.venv/\n")
    write(path / "src.txt", "line1\nline2\n")
    steps.append(rec.run(["git", "add", "-A"], path, env))
    steps.append(rec.run(["git", "commit", "-q", "-m", "base"], path, env))
    return steps


def out(step: dict[str, Any]) -> str:
    return (step.get("stdout") or "").strip()


def probe_worktree(rec: Recorder, tmp: Path) -> None:
    env = isolated_env(tmp)
    repo = tmp / "g1" / "repo"
    steps = init_repo(rec, repo, env)
    wt = tmp / "g1" / "wt"
    add = rec.run(["git", "worktree", "add", "-b", "aicollab/run-1", str(wt), "HEAD"], repo, env)
    steps.append(add)
    listing = rec.run(["git", "worktree", "list", "--porcelain"], repo, env)
    steps.append(listing)
    dup = rec.run(["git", "worktree", "add", "-b", "aicollab/run-1", str(tmp / "g1" / "wt2"), "HEAD"], repo, env)
    steps.append(dup)
    write(wt / "untracked.txt", "x\n")
    remove_dirty = rec.run(["git", "worktree", "remove", str(wt)], repo, env)
    steps.append(remove_dirty)
    remove_force = rec.run(["git", "worktree", "remove", "--force", str(wt)], repo, env)
    steps.append(remove_force)
    prune = rec.run(["git", "worktree", "prune", "-v"], repo, env)
    steps.append(prune)
    branch_after = rec.run(["git", "branch", "--list", "aicollab/run-1"], repo, env)
    steps.append(branch_after)
    # 폴더를 직접 지운 뒤 prune 하는 경우
    wt3 = tmp / "g1" / "wt3"
    steps.append(rec.run(["git", "worktree", "add", "-b", "aicollab/run-3", str(wt3), "HEAD"], repo, env))
    shutil.rmtree(wt3)
    list_stale = rec.run(["git", "worktree", "list", "--porcelain"], repo, env)
    steps.append(list_stale)
    prune_stale = rec.run(["git", "worktree", "prune", "-v"], repo, env)
    steps.append(prune_stale)
    rec.add(
        "G1",
        "worktree 생성과 정리",
        steps,
        {
            "add_exit": add["exit_code"],
            "list_porcelain": out(listing),
            "duplicate_branch_exit": dup["exit_code"],
            "duplicate_branch_stderr": dup["stderr"].strip(),
            "remove_with_untracked_exit": remove_dirty["exit_code"],
            "remove_with_untracked_stderr": remove_dirty["stderr"].strip(),
            "remove_force_exit": remove_force["exit_code"],
            "branch_kept_after_remove": bool(out(branch_after)),
            "list_after_manual_delete": out(list_stale),
            "prune_after_manual_delete": (prune_stale["stdout"] + prune_stale["stderr"]).strip(),
        },
    )


HOOK_LOG_BODY = 'echo "{name} pwd=$(pwd) git_dir=$GIT_DIR args=$*" >> "{log}"\n'


def probe_hooks(rec: Recorder, tmp: Path) -> None:
    env = isolated_env(tmp)
    repo = tmp / "g2" / "repo"
    steps = init_repo(rec, repo, env)
    log = (tmp / "g2" / "hook.log").as_posix()
    for name in ("post-checkout", "pre-commit", "commit-msg", "post-commit"):
        write_hook(repo / ".git", name, HOOK_LOG_BODY.format(name=name, log=log))
    wt = tmp / "g2" / "wt"
    steps.append(rec.run(["git", "worktree", "add", "-b", "aicollab/run-2", str(wt), "HEAD"], repo, env))
    write(wt / "src.txt", "line1\nline2\nline3\n")
    steps.append(rec.run(["git", "add", "-A"], wt, env))
    commit = rec.run(["git", "commit", "-q", "-m", "change"], wt, env)
    steps.append(commit)
    hook_log = Path(log).read_text(encoding="utf-8") if Path(log).exists() else ""
    no_verify_log_before = hook_log
    write(wt / "src.txt", "line1\n")
    steps.append(rec.run(["git", "add", "-A"], wt, env))
    steps.append(rec.run(["git", "commit", "-q", "--no-verify", "-m", "no-verify"], wt, env))
    hook_log_after = Path(log).read_text(encoding="utf-8") if Path(log).exists() else ""
    hooks_path = rec.run(["git", "rev-parse", "--git-path", "hooks"], wt, env)
    steps.append(hooks_path)
    rec.add(
        "G2",
        "worktree 안 커밋에서 hooks 실행",
        steps,
        {
            "commit_exit": commit["exit_code"],
            "hook_log_add_and_commit": rec.anonymize(no_verify_log_before).strip().splitlines(),
            "hook_log_added_by_no_verify": rec.anonymize(hook_log_after[len(no_verify_log_before):]).strip().splitlines(),
            "hooks_dir_from_worktree": out(hooks_path),
        },
    )


def tree_of(rec: Recorder, cwd: Path, env: dict[str, str], rev: str) -> str:
    return out(rec.run(["git", "rev-parse", f"{rev}^{{tree}}"], cwd, env))


def probe_hook_mutation(rec: Recorder, tmp: Path) -> None:
    env = isolated_env(tmp)
    results: dict[str, Any] = {}
    steps: list[dict[str, Any]] = []

    # 1. pre-commit이 stage 내용을 바꾸는 경우
    repo = tmp / "g3a" / "repo"
    steps += init_repo(rec, repo, env)
    write_hook(repo / ".git", "pre-commit", 'echo "added-by-pre-commit" >> src.txt\ngit add src.txt\n')
    write(repo / "src.txt", "line1\nline2\nchange\n")
    steps.append(rec.run(["git", "add", "-A"], repo, env))
    expected = rec.run(["git", "write-tree"], repo, env)
    steps.append(expected)
    commit = rec.run(["git", "commit", "-q", "-m", "c"], repo, env)
    steps.append(commit)
    actual = tree_of(rec, repo, env, "HEAD")
    status = rec.run(["git", "status", "--porcelain"], repo, env)
    steps.append(status)
    results["pre_commit_restage"] = {
        "commit_exit": commit["exit_code"],
        "expected_tree": out(expected),
        "actual_tree": actual,
        "tree_mismatch": out(expected) != actual,
        "status_after": out(status),
    }

    # 2. pre-commit이 작업 파일만 바꾸고 stage 하지 않는 경우
    repo = tmp / "g3b" / "repo"
    steps += init_repo(rec, repo, env)
    write_hook(repo / ".git", "pre-commit", 'echo "unstaged-by-pre-commit" >> src.txt\n')
    write(repo / "src.txt", "line1\nline2\nchange\n")
    steps.append(rec.run(["git", "add", "-A"], repo, env))
    expected = rec.run(["git", "write-tree"], repo, env)
    steps.append(expected)
    commit = rec.run(["git", "commit", "-q", "-m", "c"], repo, env)
    steps.append(commit)
    actual = tree_of(rec, repo, env, "HEAD")
    status = rec.run(["git", "status", "--porcelain"], repo, env)
    steps.append(status)
    results["pre_commit_worktree_only"] = {
        "commit_exit": commit["exit_code"],
        "tree_mismatch": out(expected) != actual,
        "status_after": out(status),
    }

    # 3. post-commit이 소스를 바꾸는 경우
    repo = tmp / "g3c" / "repo"
    steps += init_repo(rec, repo, env)
    write_hook(repo / ".git", "post-commit", 'echo "post-commit" >> src.txt\n')
    write(repo / "src.txt", "line1\nline2\nchange\n")
    steps.append(rec.run(["git", "add", "-A"], repo, env))
    expected = rec.run(["git", "write-tree"], repo, env)
    steps.append(expected)
    commit = rec.run(["git", "commit", "-q", "-m", "c"], repo, env)
    steps.append(commit)
    actual = tree_of(rec, repo, env, "HEAD")
    status = rec.run(["git", "status", "--porcelain"], repo, env)
    steps.append(status)
    results["post_commit_mutation"] = {
        "commit_exit": commit["exit_code"],
        "tree_mismatch": out(expected) != actual,
        "status_after": out(status),
    }

    # 4. pre-commit이 실패하는 경우
    repo = tmp / "g3d" / "repo"
    steps += init_repo(rec, repo, env)
    write_hook(repo / ".git", "pre-commit", 'echo "blocked by hook" >&2\nexit 3\n')
    write(repo / "src.txt", "line1\nline2\nchange\n")
    steps.append(rec.run(["git", "add", "-A"], repo, env))
    head_before = out(rec.run(["git", "rev-parse", "HEAD"], repo, env))
    commit = rec.run(["git", "commit", "-q", "-m", "c"], repo, env)
    steps.append(commit)
    head_after = out(rec.run(["git", "rev-parse", "HEAD"], repo, env))
    results["pre_commit_fail"] = {
        "commit_exit": commit["exit_code"],
        "stderr": commit["stderr"].strip(),
        "head_moved": head_before != head_after,
    }

    # 5. commit-msg가 메시지를 바꾸는 경우
    repo = tmp / "g3e" / "repo"
    steps += init_repo(rec, repo, env)
    write_hook(repo / ".git", "commit-msg", 'echo "Signed-off-by: hook" >> "$1"\n')
    write(repo / "src.txt", "line1\nchange\n")
    steps.append(rec.run(["git", "add", "-A"], repo, env))
    steps.append(rec.run(["git", "commit", "-q", "-m", "original"], repo, env))
    msg = rec.run(["git", "log", "-1", "--format=%B"], repo, env)
    steps.append(msg)
    results["commit_msg_mutation"] = {"final_message": out(msg)}

    rec.add("G3", "hook이 파일을 바꿀 때 tree 불일치 탐지", steps, results)


SIGNING_KEYS = (
    "commit.gpgsign",
    "tag.gpgsign",
    "gpg.format",
    "gpg.program",
    "gpg.openpgp.program",
    "gpg.ssh.program",
    "gpg.x509.program",
    "user.signingkey",
)


def probe_signing(rec: Recorder, tmp: Path) -> None:
    steps: list[dict[str, Any]] = []
    results: dict[str, Any] = {}

    # 사용자 실제 설정은 읽기만 하고 값은 남기지 않는다. 존재 여부와 출처 범위만 기록한다.
    user_env = dict(os.environ)
    user_cfg = rec.run(["git", "config", "--show-scope", "--get-regexp", r"^(commit|tag)\.gpgsign$|^gpg\.|^user\.signingkey$"], tmp, user_env)
    present = []
    for line in out(user_cfg).splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2:
            present.append({"scope": parts[0], "key": parts[1], "value_recorded": parts[1] in ("commit.gpgsign", "tag.gpgsign", "gpg.format")
                            and len(parts) > 2 and parts[2] or "<생략>"})
    results["user_signing_config_keys"] = present
    results["user_signing_config_exit"] = user_cfg["exit_code"]

    env = isolated_env(tmp)
    repo = tmp / "g4" / "repo"
    steps += init_repo(rec, repo, env)

    # 탐지 명령
    rec.run(["git", "config", "commit.gpgsign", "true"], repo, env)
    detect = rec.run(["git", "config", "--show-origin", "--show-scope", "--get-regexp", r"^(commit|tag)\.gpgsign$|^gpg\.|^user\.signingkey$"], repo, env)
    steps.append(detect)
    bool_val = rec.run(["git", "config", "--type=bool", "--get", "commit.gpgsign"], repo, env)
    steps.append(bool_val)
    results["detect_output"] = out(detect)
    results["detect_bool"] = out(bool_val)

    # 실패하는 서명 프로그램
    fail_prog = tmp / "g4" / ("fail-sign.cmd" if IS_WINDOWS else "fail-sign.sh")
    if IS_WINDOWS:
        write(fail_prog, "@echo off\r\necho signing refused 1>&2\r\nexit /b 1\r\n", newline="")
    else:
        write(fail_prog, "#!/bin/sh\necho 'signing refused' >&2\nexit 1\n")
        fail_prog.chmod(0o755)
    rec.run(["git", "config", "gpg.program", str(fail_prog)], repo, env)
    write(repo / "src.txt", "line1\nsign-fail\n")
    steps.append(rec.run(["git", "add", "-A"], repo, env))
    head_before = out(rec.run(["git", "rev-parse", "HEAD"], repo, env))
    commit = rec.run(["git", "commit", "-q", "-m", "signed"], repo, env)
    steps.append(commit)
    head_after = out(rec.run(["git", "rev-parse", "HEAD"], repo, env))
    results["failing_program"] = {
        "commit_exit": commit["exit_code"],
        "stderr": commit["stderr"].strip(),
        "head_moved": head_before != head_after,
    }

    # 입력을 기다리는 서명 프로그램 (사람 개입 흉내). 시간 상한으로 끊는다.
    wait_prog = tmp / "g4" / ("wait-sign.cmd" if IS_WINDOWS else "wait-sign.sh")
    if IS_WINDOWS:
        write(wait_prog, "@echo off\r\nset /p PIN=PIN: \r\nexit /b 1\r\n", newline="")
    else:
        write(wait_prog, "#!/bin/sh\nprintf 'PIN: ' >&2\nread PIN\nsleep 30\nexit 1\n")
        wait_prog.chmod(0o755)
    rec.run(["git", "config", "gpg.program", str(wait_prog)], repo, env)
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            ["git", "commit", "-q", "-m", "signed-wait"],
            cwd=repo,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            so, se = proc.communicate(timeout=5)
            wait_result = {"exit_code": proc.returncode, "timed_out": False, "stderr": rec.anonymize(se.strip())}
        except subprocess.TimeoutExpired:
            proc.kill()
            so, se = proc.communicate()
            wait_result = {"exit_code": proc.returncode, "timed_out": True, "stderr": rec.anonymize((se or "").strip())}
    except OSError as exc:
        wait_result = {"error": str(exc)}
    wait_result["seconds"] = round(time.monotonic() - start, 3)
    head_after_wait = out(rec.run(["git", "rev-parse", "HEAD"], repo, env))
    wait_result["head_moved"] = head_after != head_after_wait
    lock_left = (repo / ".git" / "index.lock").exists()
    wait_result["index_lock_left"] = lock_left
    results["waiting_program_stdin_pipe"] = wait_result

    # ssh 형식인데 서명 키가 없는 경우
    rec.run(["git", "config", "--unset", "gpg.program"], repo, env)
    if lock_left:
        (repo / ".git" / "index.lock").unlink()
    rec.run(["git", "config", "gpg.format", "ssh"], repo, env)
    commit = rec.run(["git", "commit", "-q", "-m", "ssh-no-key"], repo, env)
    steps.append(commit)
    results["ssh_format_without_key"] = {"commit_exit": commit["exit_code"], "stderr": commit["stderr"].strip()}

    rec.add("G4", "사람 개입 서명 설정 탐지", steps, results)


def probe_no_change(rec: Recorder, tmp: Path) -> None:
    env = isolated_env(tmp)
    repo = tmp / "g5" / "repo"
    steps = init_repo(rec, repo, env)
    base_tree = tree_of(rec, repo, env, "HEAD")
    results: dict[str, Any] = {"base_tree": base_tree}

    def snapshot(label: str) -> None:
        steps.append(rec.run(["git", "add", "-A"], repo, env))
        wt = rec.run(["git", "write-tree"], repo, env)
        quiet = rec.run(["git", "diff", "--cached", "--quiet", "HEAD"], repo, env)
        status = rec.run(["git", "status", "--porcelain"], repo, env)
        steps.extend([wt, quiet, status])
        results[label] = {
            "write_tree": out(wt),
            "same_as_base": out(wt) == base_tree,
            "diff_cached_quiet_exit": quiet["exit_code"],
            "status": out(status),
        }

    snapshot("untouched")
    commit = rec.run(["git", "commit", "-q", "-m", "nothing"], repo, env)
    steps.append(commit)
    results["commit_without_change"] = {
        "exit_code": commit["exit_code"],
        "stdout": commit["stdout"].strip(),
        "stderr": commit["stderr"].strip(),
    }

    write(repo / "src.txt", "line1\nline2\nextra\n")
    write(repo / "src.txt", "line1\nline2\n")
    snapshot("changed_then_reverted")

    (repo / "node_modules").mkdir()
    write(repo / "node_modules" / "dep.js", "module.exports = 1\n")
    (repo / ".venv").mkdir()
    write(repo / ".venv" / "pyvenv.cfg", "home = x\n")
    snapshot("ignored_dependency_dirs")

    raw_before = (repo / "src.txt").read_bytes()
    write(repo / "src.txt", "line1\nline2\n", newline="\r\n")
    raw_after = (repo / "src.txt").read_bytes()
    status_pre = rec.run(["git", "status", "--porcelain"], repo, env)
    steps.append(status_pre)
    results["crlf_status_before_add"] = out(status_pre)
    snapshot("crlf_rewrite_with_eol_lf")
    results["crlf_rewrite_with_eol_lf"]["raw_bytes_changed"] = raw_before != raw_after

    rec.add("G5", "변경 없음 판정", steps, results)


def probe_push_and_gh(rec: Recorder, tmp: Path) -> None:
    env = isolated_env(tmp)
    steps: list[dict[str, Any]] = []
    results: dict[str, Any] = {}
    remote = tmp / "g6" / "remote.git"
    remote.parent.mkdir(parents=True)
    steps.append(rec.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], remote.parent, env))
    repo = tmp / "g6" / "repo"
    steps += init_repo(rec, repo, env)
    steps.append(rec.run(["git", "remote", "add", "origin", str(remote)], repo, env))
    steps.append(rec.run(["git", "switch", "-q", "-c", "aicollab/run-6"], repo, env))
    write(repo / "src.txt", "line1\npush1\n")
    steps.append(rec.run(["git", "commit", "-qam", "p1"], repo, env))

    lease = "--force-with-lease=refs/heads/aicollab/run-6:"
    first = rec.run(["git", "push", "--porcelain", lease, "origin", "HEAD:refs/heads/aicollab/run-6"], repo, env)
    steps.append(first)
    write(repo / "src.txt", "line1\npush2\n")
    steps.append(rec.run(["git", "commit", "-qam", "p2"], repo, env))
    second = rec.run(["git", "push", "--porcelain", lease, "origin", "HEAD:refs/heads/aicollab/run-6"], repo, env)
    steps.append(second)
    remote_head = rec.run(["git", "rev-parse", "refs/heads/aicollab/run-6"], remote, env)
    steps.append(remote_head)
    results["create_only_lease"] = {
        "first_exit": first["exit_code"],
        "first_stdout": first["stdout"].strip(),
        "second_exit": second["exit_code"],
        "second_stdout": second["stdout"].strip(),
        "second_stderr": second["stderr"].strip(),
    }
    dry = rec.run(["git", "push", "--dry-run", "--porcelain", "origin", "HEAD:refs/heads/aicollab/other"], repo, env)
    steps.append(dry)
    exists_after_dry = rec.run(["git", "rev-parse", "--verify", "--quiet", "refs/heads/aicollab/other"], remote, env)
    results["push_dry_run"] = {"exit": dry["exit_code"], "ref_created": exists_after_dry["exit_code"] == 0}

    gh = shutil.which("gh")
    results["gh_path_found"] = gh is not None
    if gh:
        ver = rec.run([gh, "--version"], tmp, dict(os.environ))
        help_ = rec.run([gh, "pr", "create", "--help"], tmp, dict(os.environ))
        steps += [ver, help_]
        lines = [line for line in help_["stdout"].splitlines() if any(k in line.lower() for k in ("push", "dry-run", "head", "fork"))]
        results["gh_version"] = out(ver).splitlines()[0] if out(ver) else ""
        results["gh_pr_create_help_lines"] = [line.strip() for line in lines]
    rec.add("G6", "push lease와 gh pr create의 push 동작", steps, results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--keep-tmp", action="store_true")
    args = parser.parse_args()

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out or Path("local-data") / "probes" / "git-behavior" / stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="aicollab-git-probe-"))
    rec = Recorder(tmp)

    env_info = {
        "probe": "git-behavior",
        "issue": 6,
        "started_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "git_version": out(rec.run(["git", "--version"], tmp, dict(os.environ))),
        "locale_env": {k: os.environ.get(k) for k in ("LANG", "LC_ALL", "LANGUAGE") if os.environ.get(k)},
    }
    failures = {}
    for fn in (probe_worktree, probe_hooks, probe_hook_mutation, probe_signing, probe_no_change, probe_push_and_gh):
        try:
            fn(rec, tmp)
        except Exception as exc:  # 실험 하나가 실패해도 나머지를 기록한다.
            failures[fn.__name__] = repr(exc)
    data = {"environment": env_info, "checks": rec.checks, "script_errors": failures}
    (out_dir / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.keep_tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"결과: {out_dir / 'results.json'}")
    if failures:
        print(f"스크립트 오류: {failures}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
