"""고정 HEAD에서 run worktree를 만든다(D09 warn-head).

원본의 staged, unstaged, untracked 변경은 경고만 하고 run에 넣지 않는다. 자동 stash,
reset, clean을 하지 않는다. worktree는 작업 분리이며 보안 격리가 아니다(R08).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from aicollab.audit.snapshot import Snapshot, take_snapshot
from aicollab.workspace.git import (
    Git,
    GitEnvironment,
    GitError,
    build_git_environment,
    decode_path,
    display_path,
    split_nul,
)

BRANCH_PREFIX = "aicollab/"
TRUSTED_LOCAL_NOTICE = (
    "trusted-local: 본인 저장소의 AI 실수 탐지용. 악의적 저장소와 prompt injection 방어 "
    "보장 없음. 범위 위반은 실행 뒤 탐지"
)

_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class WorkspaceError(RuntimeError):
    """작업 공간을 만들 수 없거나 만든 뒤 확인에서 예상 밖 상태를 발견했다.

    preserved_path가 있으면 그 worktree를 지우지 않고 남겨 둔 것이다.
    """

    def __init__(self, message: str, preserved_path: Path | None = None) -> None:
        super().__init__(message)
        self.preserved_path = preserved_path


@dataclass(frozen=True)
class OriginEntry:
    path: str
    xy: str  # status의 두 글자. untracked는 "??"
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class OriginState:
    """원본 저장소의 HEAD와 미커밋 변경."""

    head_oid: str
    branch: str | None
    entries: tuple[OriginEntry, ...]

    @property
    def staged(self) -> tuple[str, ...]:
        return tuple(e.path for e in self.entries if e.xy != "??" and e.xy[0] != ".")

    @property
    def unstaged(self) -> tuple[str, ...]:
        return tuple(e.path for e in self.entries if e.xy != "??" and e.xy[1] != ".")

    @property
    def untracked(self) -> tuple[str, ...]:
        return tuple(e.path for e in self.entries if e.xy == "??")

    @property
    def dirty(self) -> bool:
        return bool(self.entries)

    def record(self) -> dict[str, object]:
        return {
            "head_oid": self.head_oid,
            "branch": self.branch,
            "staged": [display_path(p) for p in self.staged],
            "unstaged": [display_path(p) for p in self.unstaged],
            "untracked": [display_path(p) for p in self.untracked],
        }


def _parse_status(output: bytes) -> list[tuple[str, str]]:
    """`git status --porcelain=v2 -z`의 (XY, 경로) 목록."""
    records = split_nul(output)
    result: list[tuple[str, str]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        kind = record[:1]
        if kind == b"1":
            fields = record.split(b" ", 8)
            result.append((fields[1].decode("ascii"), decode_path(fields[8])))
        elif kind == b"2":
            fields = record.split(b" ", 9)
            result.append((fields[1].decode("ascii"), decode_path(fields[9])))
            index += 1  # 원래 경로가 다음 레코드로 온다.
        elif kind == b"u":
            fields = record.split(b" ", 10)
            result.append((fields[1].decode("ascii"), decode_path(fields[10])))
        elif kind == b"?":
            result.append(("??", decode_path(record[2:])))
    return result


def inspect_origin(git: Git) -> OriginState:
    """원본 저장소 상태를 읽는다. `--no-optional-locks`로 원본 index를 갱신하지 않는다."""
    head = git.line("rev-parse", "--verify", "HEAD^{commit}")
    symbolic = git.run("symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    branch = symbolic.stdout.decode("utf-8", "replace").strip() or None
    status = git.run(
        "--no-optional-locks",
        "status",
        "--porcelain=v2",
        "-z",
        "--no-renames",
        "--untracked-files=all",
    ).stdout
    entries: list[OriginEntry] = []
    for xy, path in _parse_status(status):
        try:
            info = os.lstat(git.cwd / path.rstrip("/"))
            size, mtime_ns = info.st_size, info.st_mtime_ns
        except OSError:
            size, mtime_ns = -1, -1
        entries.append(OriginEntry(path, xy, size, mtime_ns))
    entries.sort(key=lambda entry: entry.path.encode("utf-8", "surrogateescape"))
    return OriginState(head, branch, tuple(entries))


def run_dir(run_root: Path, run_id: str) -> Path:
    return run_root / run_id


def worktree_path(run_root: Path, run_id: str) -> Path:
    return run_dir(run_root, run_id) / "worktree"


def audit_dir(run_root: Path, run_id: str, sequence: int, role: str) -> Path:
    return run_dir(run_root, run_id) / "audit" / f"{sequence:03d}-{role}"


def _path_key(path: Path) -> Path:
    """실제 경로로 푼 뒤 비교용으로 정규화한다. Windows에서는 대소문자와 구분자를 맞춘다."""
    return Path(os.path.normcase(str(path.resolve())))


def _overlaps(a: Path, b: Path) -> bool:
    """두 경로가 같거나 한쪽이 다른 쪽 안에 있다."""
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def _git_common_dir(git: Git) -> Path:
    raw = git.run("rev-parse", "--git-common-dir").stdout.rstrip(b"\r\n")
    common = Path(decode_path(raw))
    return common if common.is_absolute() else git.cwd / common


def validate_run_root(run_root: Path, run_id: str, git: Git) -> Path:
    """run_root가 project.run_root의 조건을 지키는지 확인하고 run 폴더 경로를 돌려준다.

    조건(docs/02-config-spec.md): 원본 checkout과 공유 Git 관리 경로 밖 절대 경로.
    git.cwd는 원본 작업 트리의 최상위 폴더다. 비교는 실제 경로 기준이다.
    """
    if not run_root.is_absolute():
        raise WorkspaceError(f"run_root는 절대 경로여야 합니다: {run_root}")
    root_key = _path_key(run_root)
    top_key = _path_key(git.cwd)
    common_key = _path_key(_git_common_dir(git))
    if root_key == top_key or root_key.is_relative_to(top_key):
        raise WorkspaceError(f"run_root가 원본 작업 트리 안에 있습니다: {run_root}")
    if root_key == common_key or root_key.is_relative_to(common_key):
        raise WorkspaceError(f"run_root가 공유 Git 관리 경로 안에 있습니다: {run_root}")
    target = run_dir(run_root, run_id)
    target_key = _path_key(target)
    if _overlaps(target_key, top_key) or _overlaps(target_key, common_key):
        raise WorkspaceError(f"run 폴더가 원본 작업 트리나 공유 Git 관리 경로와 겹칩니다: {target}")
    return target


@dataclass(frozen=True)
class RunWorkspace:
    origin: Path
    run_root: Path
    path: Path
    run_id: str
    branch: str
    base_oid: str
    base_tree: str
    baseline: Snapshot
    origin_state: OriginState
    environment: GitEnvironment
    warnings: tuple[str, ...]

    @property
    def git(self) -> Git:
        return Git(self.path, self.environment)

    @property
    def run_dir(self) -> Path:
        return run_dir(self.run_root, self.run_id)

    def audit_dir(self, sequence: int, role: str) -> Path:
        return audit_dir(self.run_root, self.run_id, sequence, role)

    @property
    def origin_git(self) -> Git:
        return Git(self.origin, self.environment)

    def origin_changes(self) -> tuple[str, ...]:
        """run 시작 뒤 원본 저장소에서 달라진 점. 비어 있으면 그대로다."""
        now = inspect_origin(self.origin_git)
        before = self.origin_state
        changes: list[str] = []
        if now.head_oid != before.head_oid:
            changes.append(f"HEAD: {before.head_oid} -> {now.head_oid}")
        if now.branch != before.branch:
            changes.append(f"branch: {before.branch} -> {now.branch}")
        old = {entry.path: entry for entry in before.entries}
        new = {entry.path: entry for entry in now.entries}
        for path in sorted(old.keys() | new.keys()):
            if old.get(path) != new.get(path):
                changes.append(f"path: {display_path(path)}")
        return tuple(changes)

    def record(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "origin": str(self.origin),
            "run_root": str(self.run_root),
            "worktree": str(self.path),
            "branch": self.branch,
            "base_oid": self.base_oid,
            "base_tree": self.base_tree,
            "baseline_manifest_sha256": self.baseline.manifest_sha256,
            "origin_state": self.origin_state.record(),
            "git_environment": self.environment.record(),
            "warnings": list(self.warnings),
        }


def _warn_head(state: OriginState) -> str | None:
    if not state.dirty:
        return None
    return (
        "원본 저장소에 미커밋 변경이 있습니다 "
        f"(staged {len(state.staged)}개, unstaged {len(state.unstaged)}개, "
        f"untracked {len(state.untracked)}개). 이 변경은 run에 들어가지 않습니다. "
        f"고정한 HEAD {state.head_oid}에서 시작합니다."
    )


def _resolve_origin(origin: Path, environment: GitEnvironment) -> tuple[Path, str]:
    probe = Git(origin, environment)
    top = probe.run("rev-parse", "--show-toplevel", check=False)
    if top.returncode != 0 or not top.stdout.strip():
        raise WorkspaceError(f"작업 트리가 있는 Git 저장소가 아닙니다: {origin}")
    top_path = Path(decode_path(top.stdout.rstrip(b"\r\n")))
    git = probe.at(top_path)
    superproject = git.run("rev-parse", "--show-superproject-working-tree", check=False)
    if superproject.stdout.strip():
        raise WorkspaceError(f"submodule은 지원하지 않습니다: {top_path}")
    head = git.run("rev-parse", "--verify", "--quiet", "HEAD^{commit}", check=False)
    if head.returncode != 0:
        raise WorkspaceError(f"유효한 HEAD가 없는 저장소입니다: {top_path}")
    return top_path, head.stdout.decode("ascii").strip()


def create_run_workspace(
    origin: Path,
    run_id: str,
    *,
    run_root: Path,
    environ: Mapping[str, str] | None = None,
) -> RunWorkspace:
    """시작 시 해석한 HEAD commit OID에서 `aicollab/<run_id>` worktree를 만든다.

    worktree는 `<run_root>/<run_id>/worktree`에 만든다. run_root는 설정의 project.run_root이며
    원본 작업 트리와 공유 Git 관리 경로 밖의 절대 경로여야 한다. 조건을 어기면 worktree를
    만들기 전에 거부한다. 만든 뒤 worktree의 source가 고정 HEAD와 같은지, 원본 저장소가
    그대로인지 확인한다. 다르면 worktree를 남겨 둔 채 WorkspaceError를 낸다. 기록은
    `<run_root>/<run_id>/workspace.json`에 쓴다.
    """
    if not _RUN_ID.fullmatch(run_id):
        raise WorkspaceError(f"run_id에 쓸 수 없는 문자가 있습니다: {run_id!r}")
    environment = build_git_environment(environ)
    top, base_oid = _resolve_origin(origin, environment)
    git = Git(top, environment)
    branch = BRANCH_PREFIX + run_id
    if git.run("check-ref-format", "--branch", branch, check=False).returncode != 0:
        raise WorkspaceError(f"branch 이름으로 쓸 수 없는 run_id입니다: {run_id!r}")

    target = validate_run_root(run_root, run_id, git)
    if target.exists():
        raise WorkspaceError(f"run 폴더가 이미 있습니다. 덮어쓰지 않습니다: {target}")
    path = worktree_path(run_root, run_id)

    origin_state = inspect_origin(git)
    warnings = [TRUSTED_LOCAL_NOTICE, *environment.warnings()]
    warn_head = _warn_head(origin_state)
    if warn_head is not None:
        warnings.append(warn_head)

    target.mkdir(parents=True)
    try:
        # 같은 이름의 branch가 있으면 실패한다. 기존 branch를 덮어쓰지 않는다.
        git.run("worktree", "add", "-b", branch, str(path), base_oid)
    except GitError as exc:
        if not path.exists():
            # worktree가 생기지 않았으면 방금 만든 빈 run 폴더만 지운다.
            with contextlib.suppress(OSError):
                target.rmdir()
        raise WorkspaceError(f"run worktree를 만들지 못했습니다: {exc}") from exc

    worktree_git = Git(path, environment)
    base_tree = git.line("rev-parse", "--verify", f"{base_oid}^{{tree}}")
    # worktree 생성 hooks(post-checkout)가 실행된 뒤의 상태를 고정 HEAD와 비교한다.
    baseline = take_snapshot(worktree_git)
    status = worktree_git.run("status", "--porcelain=v2", "-z", "--no-renames").stdout
    if baseline.head_oid != base_oid or baseline.tree_oid != base_tree or status:
        raise WorkspaceError(
            "worktree를 만든 직후의 source가 고정 HEAD와 다릅니다. worktree를 그대로 두고 "
            f"중단합니다: {path}",
            preserved_path=path,
        )

    workspace = RunWorkspace(
        origin=top,
        run_root=run_root,
        path=path,
        run_id=run_id,
        branch=branch,
        base_oid=base_oid,
        base_tree=base_tree,
        baseline=baseline,
        origin_state=origin_state,
        environment=environment,
        warnings=tuple(warnings),
    )
    changed = workspace.origin_changes()
    if changed:
        raise WorkspaceError(
            "worktree를 만드는 동안 원본 저장소가 바뀌었습니다. 되돌리지 않고 중단합니다: "
            + ", ".join(changed),
            preserved_path=path,
        )
    (target / "workspace.json").write_text(
        json.dumps(workspace.record(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return workspace
