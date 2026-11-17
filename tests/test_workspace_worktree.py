"""이슈 #14: 고정 HEAD worktree와 warn-head(D09)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from workspace_audit_support import git, isolated_environ, make_repo, write

from aicollab.workspace.worktree import (
    TRUSTED_LOCAL_NOTICE,
    WorkspaceError,
    create_run_workspace,
    default_audit_dir,
    inspect_origin,
)


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """`.git`과 run 제어 영역을 뺀 모든 파일의 byte."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative.startswith((".git/", ".aicollab/runs/")) or not path.is_file():
            continue
        result[relative] = path.read_bytes()
    return result


def test_run_starts_from_fixed_head_and_preserves_origin_changes(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env)
    head = git(origin, env, "rev-parse", "HEAD")
    # 원본에 staged, unstaged, untracked 변경을 만든다. CRLF와 한글 경로를 섞는다.
    write(origin / "src" / "app.py", "print('staged')\n")
    git(origin, env, "add", "src/app.py")
    write(origin / "tests" / "test_app.py", b"def test_base():\r\n    assert False\r\n")
    write(origin / "새 폴더" / "메모 파일.txt", "미커밋 내용\n")
    files_before = _tree_bytes(origin)
    status_before = git(origin, env, "status", "--porcelain=v2", "--untracked-files=all")
    index_before = (origin / ".git" / "index").read_bytes()
    stash_before = git(origin, env, "stash", "list")

    workspace = create_run_workspace(origin, "run-1", environ=env)

    # 고정 HEAD에서 시작한다. 원본의 변경은 run에 들어가지 않는다.
    assert workspace.base_oid == head
    assert workspace.branch == "aicollab/run-1"
    assert workspace.path.resolve() == (origin / ".aicollab/runs/run-1/worktree").resolve()
    assert git(workspace.path, env, "rev-parse", "HEAD") == head
    assert git(workspace.path, env, "status", "--porcelain") == ""
    assert (workspace.path / "src" / "app.py").read_bytes() == b"print('base')\n"
    assert (workspace.path / "tests" / "test_app.py").read_bytes() == (
        b"def test_base():\n    assert True\n"
    )
    assert not (workspace.path / "새 폴더").exists()
    assert workspace.baseline.tree_oid == workspace.base_tree

    # 원본 변경은 그대로다. stash, reset, clean을 하지 않았다.
    assert (origin / ".git" / "index").read_bytes() == index_before
    assert _tree_bytes(origin) == files_before
    assert git(origin, env, "status", "--porcelain=v2", "--untracked-files=all") == status_before
    assert git(origin, env, "stash", "list") == stash_before
    assert git(origin, env, "rev-parse", "HEAD") == head
    assert git(origin, env, "symbolic-ref", "--short", "HEAD") == "main"

    # warn-head 경고와 기록
    assert workspace.origin_state.staged == ("src/app.py",)
    assert workspace.origin_state.unstaged == ("tests/test_app.py",)
    assert workspace.origin_state.untracked == ("새 폴더/메모 파일.txt",)
    assert workspace.warnings[0] == TRUSTED_LOCAL_NOTICE
    warn_head = workspace.warnings[-1]
    assert "staged 1개, unstaged 1개, untracked 1개" in warn_head
    assert head in warn_head
    record = json.loads(
        (origin / ".aicollab" / "runs" / "run-1" / "workspace.json").read_text(encoding="utf-8")
    )
    assert record["base_oid"] == head
    assert record["origin_state"]["untracked"] == ["새 폴더/메모 파일.txt"]
    assert record["git_environment"]["config_vars"] == ["GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"]
    assert env["GIT_CONFIG_GLOBAL"] not in json.dumps(record["git_environment"])
    assert workspace.origin_changes() == ()


def test_clean_origin_has_no_warn_head(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env)
    workspace = create_run_workspace(origin, "run-clean", environ=env)
    assert not workspace.origin_state.dirty
    assert not any("미커밋" in warning for warning in workspace.warnings)


def test_run_folder_inside_origin_is_not_an_origin_change(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    # 원본이 .aicollab/runs/를 ignore하지 않는 저장소
    origin = make_repo(tmp_path / "origin", env, {".gitignore": "node_modules/\n"})
    workspace = create_run_workspace(origin, "run-1", environ=env)
    assert (origin / ".aicollab" / "runs" / "run-1" / "workspace.json").is_file()
    assert workspace.origin_changes() == ()
    second = create_run_workspace(origin, "run-2", environ=env)
    assert not second.origin_state.dirty
    assert second.baseline.tree_oid == second.base_tree


def test_head_is_fixed_at_start_even_if_origin_moves_later(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env)
    head = git(origin, env, "rev-parse", "HEAD")
    workspace = create_run_workspace(origin, "run-fixed", environ=env)

    write(origin / "src" / "app.py", "print('later')\n")
    git(origin, env, "commit", "-q", "-am", "later")

    assert git(workspace.path, env, "rev-parse", "HEAD") == head
    assert (workspace.path / "src" / "app.py").read_bytes() == b"print('base')\n"
    changes = workspace.origin_changes()
    assert any(change.startswith("HEAD: ") for change in changes)


def test_origin_changes_reports_edits_to_uncommitted_files(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env)
    write(origin / "notes.txt", "one\n")
    workspace = create_run_workspace(origin, "run-edit", environ=env)
    assert workspace.origin_changes() == ()
    write(origin / "notes.txt", "one\ntwo and more\n")
    write(origin / "한글.txt", "새 파일\n")
    assert workspace.origin_changes() == ("path: notes.txt", "path: 한글.txt")


def test_existing_branch_is_not_overwritten(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env)
    git(origin, env, "branch", "aicollab/run-dup")
    write(origin / "src" / "app.py", "print('next')\n")
    git(origin, env, "commit", "-q", "-am", "next")
    branch_before = git(origin, env, "rev-parse", "aicollab/run-dup")

    with pytest.raises(WorkspaceError, match="만들지 못했습니다"):
        create_run_workspace(origin, "run-dup", environ=env)

    assert git(origin, env, "rev-parse", "aicollab/run-dup") == branch_before
    assert not (origin / ".aicollab" / "runs" / "run-dup" / "worktree").exists()


def test_existing_worktree_path_is_not_overwritten(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env)
    target = tmp_path / "elsewhere"
    write(target / "keep.txt", "keep\n")
    with pytest.raises(WorkspaceError, match="이미 있습니다"):
        create_run_workspace(origin, "run-x", worktree_path=target, environ=env)
    assert (target / "keep.txt").read_bytes() == b"keep\n"
    assert git(origin, env, "branch", "--list", "aicollab/run-x") == ""


def test_custom_worktree_and_record_paths(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env)
    target = tmp_path / "작업 공간" / "wt"
    record = tmp_path / "records" / "workspace.json"
    workspace = create_run_workspace(
        origin / "src", "run-custom", worktree_path=target, record_path=record, environ=env
    )
    assert workspace.origin.samefile(origin)
    assert workspace.path == target
    assert (target / "src" / "app.py").is_file()
    assert json.loads(record.read_text(encoding="utf-8"))["run_id"] == "run-custom"
    assert not (origin / ".aicollab").exists()
    assert default_audit_dir(origin, "run-custom", 2, "coder") == (
        origin / ".aicollab" / "runs" / "run-custom" / "audit" / "002-coder"
    )


@pytest.mark.parametrize("run_id", ["", "a/b", "..", "-lead", "sp ace", "x" * 65, "a..b.lock"])
def test_invalid_run_id_is_rejected(tmp_path: Path, run_id: str) -> None:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env)
    with pytest.raises(WorkspaceError):
        create_run_workspace(origin, run_id, environ=env)
    assert git(origin, env, "branch", "--list", "aicollab/*") == ""


def test_folder_without_git_and_repo_without_head_are_rejected(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    env["GIT_CEILING_DIRECTORIES"] = str(tmp_path)
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(WorkspaceError, match="Git 저장소가 아닙니다"):
        create_run_workspace(plain, "run-1", environ=env)
    empty = tmp_path / "empty"
    empty.mkdir()
    git(empty, env, "init", "-q")
    with pytest.raises(WorkspaceError, match="유효한 HEAD"):
        create_run_workspace(empty, "run-1", environ=env)


def test_source_changed_by_worktree_hook_stops_and_preserves(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env)
    hook = origin / ".git" / "hooks" / "post-checkout"
    write(hook, "#!/bin/sh\necho 'changed by hook' >> src/app.py\n")
    os.chmod(hook, 0o755)

    with pytest.raises(WorkspaceError, match="고정 HEAD와 다릅니다") as info:
        create_run_workspace(origin, "run-hook", environ=env)

    preserved = info.value.preserved_path
    assert preserved is not None
    # 되돌리지 않고 남겨 둔다.
    assert (preserved / "src" / "app.py").read_bytes() == b"print('base')\nchanged by hook\n"
    assert (origin / "src" / "app.py").read_bytes() == b"print('base')\n"


def test_inspect_origin_does_not_touch_the_index(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env)
    # 내용은 같고 수정 시각만 바뀐 파일. 일반 status는 index의 stat 정보를 갱신한다.
    target = origin / "src" / "app.py"
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    index_before = (origin / ".git" / "index").read_bytes()
    workspace = create_run_workspace(origin, "run-index", environ=env)
    state = inspect_origin(workspace.origin_git, workspace.exclude_prefixes)
    assert state.entries == ()
    assert (origin / ".git" / "index").read_bytes() == index_before
