"""이슈 #14: raw byte snapshot과 Git tree 비교, NUL 구분 경로."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from workspace_audit_support import git, isolated_environ, make_repo, run_root, write

from aicollab.audit.compare import compare_snapshots
from aicollab.audit.snapshot import SnapshotUnstableError, take_snapshot
from aicollab.workspace.git import Git
from aicollab.workspace.worktree import RunWorkspace, create_run_workspace


def _workspace(tmp_path: Path, files: dict[str, bytes | str] | None = None) -> RunWorkspace:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env, files)
    return create_run_workspace(origin, "run-1", run_root=run_root(tmp_path), environ=env)


def test_unchanged_workspace_has_same_manifest_and_tree(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    again = take_snapshot(ws.git)
    assert again == ws.baseline
    comparison = compare_snapshots(ws.git, ws.baseline, again)
    assert comparison.changes == ()
    assert not comparison.raw_changed and not comparison.tree_changed
    paths = [entry.path for entry in ws.baseline.entries]
    assert paths == sorted(paths)
    assert {"src/app.py", "uv.lock", ".gitattributes"} <= set(paths)
    assert all(len(entry.sha256) == 64 for entry in ws.baseline.entries)


def test_crlf_rewrite_changes_raw_bytes_but_not_tree(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    write(ws.path / "src" / "app.py", b"print('base')\r\n")

    after = take_snapshot(ws.git)
    comparison = compare_snapshots(ws.git, ws.baseline, after)

    assert comparison.raw_changed
    assert not comparison.tree_changed
    assert after.tree_oid == ws.base_tree
    (change,) = comparison.changes
    assert (change.path, change.raw, change.tree) == ("src/app.py", "modified", None)
    assert change.classification == "raw-only"


def test_content_change_is_seen_by_both_comparisons(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    write(ws.path / "src" / "app.py", "print('changed')\n")
    write(ws.path / "src" / "new.py", "x = 1\n")
    (ws.path / "tests" / "test_app.py").unlink()

    comparison = compare_snapshots(ws.git, ws.baseline, take_snapshot(ws.git))

    found = {c.path: (c.raw, c.tree, c.classification) for c in comparison.changes}
    assert found == {
        "src/app.py": ("modified", "M", "raw-and-tree"),
        "src/new.py": ("added", "A", "raw-and-tree"),
        "tests/test_app.py": ("deleted", "D", "raw-and-tree"),
    }
    assert comparison.raw_changed and comparison.tree_changed
    assert comparison.after.by_path()["tests/test_app.py"].state == "deleted"
    assert comparison.after.by_path()["src/new.py"].kind == "untracked"


def test_change_then_revert_is_no_change(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    write(ws.path / "src" / "app.py", "print('temp')\n")
    write(ws.path / "src" / "app.py", "print('base')\n")
    after = take_snapshot(ws.git)
    assert after.manifest_sha256 == ws.baseline.manifest_sha256
    assert after.tree_oid == ws.base_tree


def test_ignored_dependencies_are_metadata_only(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    write(ws.path / "node_modules" / "dep" / "index.js", "module.exports = 1\n")
    write(ws.path / ".venv" / "pyvenv.cfg", "home = x\n")

    after = take_snapshot(ws.git)
    comparison = compare_snapshots(ws.git, ws.baseline, after)

    assert comparison.changes == ()
    assert after.manifest_sha256 == ws.baseline.manifest_sha256
    assert after.tree_oid == ws.base_tree
    assert [(m.path, m.category, m.type) for m in after.meta] == [
        (".venv", "ignored", "dir"),
        ("node_modules", "ignored", "dir"),
    ]
    assert [(c.path, c.change) for c in comparison.meta_changes if c.category == "ignored"] == [
        (".venv", "added"),
        ("node_modules", "added"),
    ]


def test_snapshot_does_not_change_the_real_index(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    env = dict(ws.environment.env)
    write(ws.path / "src" / "app.py", "print('unstaged')\n")
    write(ws.path / "src" / "new.py", "x = 1\n")
    index_file = Path(
        git(ws.path, env, "rev-parse", "--path-format=absolute", "--git-path", "index")
    )
    index_before = index_file.read_bytes()

    take_snapshot(ws.git)

    assert index_file.read_bytes() == index_before
    assert git(ws.path, env, "diff", "--cached", "--name-only") == ""


def test_korean_and_space_paths_are_not_escaped(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, {"문서/기존 파일.md": "기존\n"})
    write(ws.path / "문서" / "기존 파일.md", "수정\n")
    write(ws.path / "새 폴더" / "한글 이름 (1).txt", "내용\n")

    comparison = compare_snapshots(ws.git, ws.baseline, take_snapshot(ws.git))

    found = {c.path: (c.raw, c.tree) for c in comparison.changes}
    assert found == {
        "문서/기존 파일.md": ("modified", "M"),
        "새 폴더/한글 이름 (1).txt": ("added", "A"),
    }
    assert [c.record()["path"] for c in comparison.changes] == sorted(found, key=str.encode)


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows 파일 이름에는 줄바꿈과 따옴표를 쓸 수 없다"
)
def test_paths_with_newline_quote_and_tab(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    names = ["줄\n바꿈.txt", 'quo"te.txt', "tab\there.txt"]
    for name in names:
        write(ws.path / name, "x\n")
    comparison = compare_snapshots(ws.git, ws.baseline, take_snapshot(ws.git))
    assert {c.path for c in comparison.changes} == set(names)
    assert all((c.raw, c.tree) == ("added", "A") for c in comparison.changes)


@pytest.mark.skipif(sys.platform == "win32", reason="symlink와 실행 bit는 POSIX에서만 확인한다")
def test_symlink_and_executable_bit(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    os.symlink("app.py", ws.path / "src" / "link.py")
    os.chmod(ws.path / "src" / "app.py", 0o755)
    after = take_snapshot(ws.git)
    entries = after.by_path()
    assert entries["src/link.py"].mode == "120000"
    assert entries["src/link.py"].size == len(b"app.py")
    assert entries["src/app.py"].mode == "100755"
    found = {c.path: (c.raw, c.tree) for c in compare_snapshots(ws.git, ws.baseline, after).changes}
    assert found == {"src/app.py": ("modified", "M"), "src/link.py": ("added", "A")}


def test_untracked_nested_repository_is_not_read(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    env = dict(ws.environment.env)
    nested = ws.path / "vendor" / "nested"
    nested.mkdir(parents=True)
    git(nested, env, "init", "-q")
    write(nested / "inner.txt", "inner\n")
    after = take_snapshot(ws.git)
    assert "vendor/nested/inner.txt" not in after.by_path()
    assert [(m.path, m.category, m.type) for m in after.meta] == [
        ("vendor/nested", "untracked-dir", "dir")
    ]
    assert after.tree_oid == ws.base_tree
    comparison = compare_snapshots(ws.git, ws.baseline, after)
    assert [(c.path, c.change, c.category) for c in comparison.meta_changes] == [
        ("vendor/nested", "added", "untracked-dir")
    ]


def test_snapshot_fails_when_files_keep_changing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = _workspace(tmp_path)
    counter = {"n": 0}
    import aicollab.audit.snapshot as snapshot_module

    real = snapshot_module.write_tree

    def mutate_then_write(git_: Git, exclude: tuple[str, ...] = ()) -> str:
        counter["n"] += 1
        write(ws.path / "src" / "app.py", f"print({counter['n']})\n" * (counter["n"] + 1))
        return real(git_, exclude)

    monkeypatch.setattr(snapshot_module, "write_tree", mutate_then_write)
    with pytest.raises(SnapshotUnstableError):
        take_snapshot(ws.git)
    assert counter["n"] == 3
