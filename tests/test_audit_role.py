"""이슈 #14: 역할별 실행 전후 감사, 범위 밖 변경과 manifest, lock 변경 탐지, 증거 보존."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from workspace_audit_support import git, isolated_environ, make_repo, run_root, write

from aicollab.audit.role import AuditResult, audit_role
from aicollab.audit.scope import RoleScope, dependency_kind
from aicollab.workspace.worktree import RunWorkspace, create_run_workspace

CODER = RoleScope(role="coder", allowed=("src/", "tests/"))
TESTER = RoleScope(role="tester", allowed=("tests/",))
TESTER_FLOW_CODER = RoleScope(role="coder", allowed=("src/", "tests/"), denied=("tests/",))


def _workspace(tmp_path: Path, files: dict[str, bytes | str] | None = None) -> RunWorkspace:
    env = isolated_environ(tmp_path)
    origin = make_repo(tmp_path / "origin", env, files)
    return create_run_workspace(origin, "run-1", run_root=run_root(tmp_path), environ=env)


def _audit(ws: RunWorkspace, scope: RoleScope, sequence: int = 1) -> AuditResult:
    return audit_role(ws.git, ws.baseline, scope, ws.audit_dir(sequence, scope.role))


def _summary(result: AuditResult) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((result.record_dir / "audit.json").read_text("utf-8"))
    return data


def _rules(result: AuditResult) -> list[tuple[str, str]]:
    return [(v.rule, v.path) for v in result.violations]


def test_change_inside_scope_passes_and_is_recorded(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    write(ws.path / "src" / "app.py", "print('feature')\n")
    write(ws.path / "tests" / "test_feature.py", "def test_feature():\n    assert True\n")

    result = _audit(ws, CODER)

    assert result.ok
    assert result.record_dir == run_root(tmp_path) / "run-1" / "audit" / "001-coder"
    summary = _summary(result)
    assert summary["violations"] == []
    assert summary["workspace_restored"] is False
    assert [c["path"] for c in summary["comparison"]["changes"]] == [
        "src/app.py",
        "tests/test_feature.py",
    ]
    assert "evidence" not in summary
    assert (result.record_dir / "before.manifest.json").is_file()
    assert (result.record_dir / "after.manifest.json").is_file()
    assert not (result.record_dir / "changes.patch").exists()
    # 원본 저장소는 그대로다. 기록은 run_root 아래에만 생긴다.
    assert ws.origin_changes() == ()
    env = dict(ws.environment.env)
    assert git(ws.origin, env, "status", "--porcelain", "--untracked-files=all") == ""
    assert not (ws.origin / ".aicollab").exists()


def test_out_of_scope_change_is_detected_and_evidence_is_preserved(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, {"docs/guide.md": "guide\n"})
    env = dict(ws.environment.env)
    write(ws.path / "src" / "app.py", "print('feature')\n")
    write(ws.path / "docs" / "guide.md", "rewritten by role\n")
    write(ws.path / "scripts" / "한글 도구.sh", "echo 범위 밖\n")
    (ws.path / ".gitattributes").unlink()

    result = _audit(ws, CODER)

    assert not result.ok
    assert _rules(result) == [
        ("out-of-scope", ".gitattributes"),
        ("out-of-scope", "docs/guide.md"),
        ("out-of-scope", "scripts/한글 도구.sh"),
    ]
    summary = _summary(result)
    assert [v["path"] for v in summary["violations"]] == [
        ".gitattributes",
        "docs/guide.md",
        "scripts/한글 도구.sh",
    ]
    files = {item["path"]: item for item in summary["evidence"]["files"]}
    assert files[".gitattributes"] == {"path": ".gitattributes", "state": "deleted"}
    for path, expected in {
        "docs/guide.md": b"rewritten by role\n",
        "scripts/한글 도구.sh": "echo 범위 밖\n".encode(),
    }.items():
        copy = result.record_dir / files[path]["copy"]
        assert copy.read_bytes() == expected
        assert files[path]["sha256"] == hashlib.sha256(expected).hexdigest()
    patch = (result.record_dir / "changes.patch").read_bytes()
    assert b"rewritten by role" in patch and b"docs/guide.md" in patch

    # 자동 복원하지 않는다. 작업 공간과 원본은 그대로다.
    assert (ws.path / "docs" / "guide.md").read_bytes() == b"rewritten by role\n"
    assert not (ws.path / ".gitattributes").exists()
    assert git(ws.path, env, "rev-parse", "HEAD") == ws.base_oid
    assert (ws.origin / "docs" / "guide.md").read_bytes() == b"guide\n"
    assert ws.origin_changes() == ()
    assert git(ws.origin, env, "status", "--porcelain", "--untracked-files=all") == ""
    assert result.record_dir.is_relative_to(run_root(tmp_path))

    # 작업 공간이 나중에 바뀌어도 증거는 남는다.
    write(ws.path / "docs" / "guide.md", "changed again\n")
    assert (result.record_dir / files["docs/guide.md"]["copy"]).read_bytes() == (
        b"rewritten by role\n"
    )


def test_unplanned_manifest_change_is_detected(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    write(ws.path / "src" / "app.py", "import requests\n")
    write(ws.path / "pyproject.toml", '[project]\nname = "sample"\ndependencies = ["requests"]\n')

    result = _audit(ws, RoleScope(role="coder", allowed=("src/", "pyproject.toml")))

    assert _rules(result) == [("unplanned-manifest", "pyproject.toml")]
    summary = _summary(result)
    (item,) = summary["evidence"]["files"]
    assert (result.record_dir / item["copy"]).read_bytes().endswith(b'["requests"]\n')
    assert (result.record_dir / "changes.patch").is_file()


def test_planned_manifest_change_passes(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    write(ws.path / "pyproject.toml", '[project]\nname = "sample"\ndescription = "x"\n')
    scope = RoleScope(role="coder", allowed=("src/",), planned_manifests=("pyproject.toml",))
    assert _audit(ws, scope).ok


def test_lock_change_is_always_a_violation(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    write(ws.path / "uv.lock", "version = 2\n")
    write(ws.path / "web" / "package-lock.json", "{}\n")
    scope = RoleScope(
        role="coder",
        allowed=("src/", "uv.lock", "web/"),
        planned_manifests=("uv.lock", "pyproject.toml"),
    )

    result = _audit(ws, scope)

    assert _rules(result) == [
        ("lock-changed", "uv.lock"),
        ("lock-changed", "web/package-lock.json"),
    ]
    assert (ws.path / "uv.lock").read_bytes() == b"version = 2\n"


def test_tester_may_only_change_test_paths(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    write(ws.path / "tests" / "test_new.py", "def test_new():\n    assert True\n")
    assert _audit(ws, TESTER, 1).ok
    write(ws.path / "src" / "app.py", "print('tester touched source')\n")
    result = _audit(ws, TESTER, 2)
    assert _rules(result) == [("out-of-scope", "src/app.py")]


def test_coder_in_tester_flow_may_not_change_test_paths(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    write(ws.path / "src" / "app.py", "print('ok')\n")
    write(ws.path / "tests" / "test_app.py", "def test_base():\n    assert 1\n")
    result = _audit(ws, TESTER_FLOW_CODER)
    assert _rules(result) == [("out-of-scope", "tests/test_app.py")]


def test_raw_only_change_outside_scope_is_detected(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, {"docs/guide.md": "guide\n"})
    write(ws.path / "docs" / "guide.md", b"guide\r\n")

    result = _audit(ws, CODER)

    (violation,) = result.violations
    assert (violation.rule, violation.path) == ("out-of-scope", "docs/guide.md")
    assert (violation.raw, violation.tree) == ("modified", None)
    assert not result.comparison.tree_changed
    (item,) = _summary(result)["evidence"]["files"]
    assert (result.record_dir / item["copy"]).read_bytes() == b"guide\r\n"


def test_commit_made_inside_workspace_is_detected(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    env = dict(ws.environment.env)
    write(ws.path / "src" / "app.py", "print('committed by role')\n")
    git(ws.path, env, "commit", "-q", "-am", "role commit")

    result = _audit(ws, CODER)

    assert ("head-moved", "") in _rules(result)
    assert _summary(result)["comparison"]["head_moved"] is True


def test_nested_repository_inside_scope_is_detected(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    env = dict(ws.environment.env)
    nested = ws.path / "src" / "vendored"
    nested.mkdir()
    git(nested, env, "init", "-q")
    write(nested / "lib.py", "x = 1\n")
    git(nested, env, "add", "-A")
    git(nested, env, "commit", "-q", "-m", "inner")

    result = _audit(ws, CODER)

    assert _rules(result) == [("nested-repository", "src/vendored")]
    assert (nested / "lib.py").is_file()


def test_second_role_is_compared_with_its_own_start(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    write(ws.path / "src" / "app.py", "print('coder')\n")
    first = _audit(ws, CODER, 1)
    assert first.ok
    write(ws.path / "tests" / "test_more.py", "def test_more():\n    assert True\n")
    second = audit_role(ws.git, first.comparison.after, TESTER, ws.audit_dir(2, "tester"))
    assert second.ok
    assert [c.path for c in second.comparison.changes] == ["tests/test_more.py"]


def test_record_dir_rules(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    with pytest.raises(ValueError, match="작업 공간 안"):
        audit_role(ws.git, ws.baseline, CODER, ws.path / "audit")
    result = _audit(ws, CODER, 1)
    marker = result.record_dir / "audit.json"
    before = marker.read_bytes()
    with pytest.raises(FileExistsError):
        _audit(ws, CODER, 1)
    assert marker.read_bytes() == before


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("uv.lock", "lock"),
        ("web/package-lock.json", "lock"),
        ("Cargo.lock", "lock"),
        ("go.sum", "lock"),
        ("pyproject.toml", "manifest"),
        ("services/api/package.json", "manifest"),
        ("requirements-dev.txt", "manifest"),
        ("Cargo.toml", "manifest"),
        ("src/package.json.py", None),
        ("docs/lock.md", None),
        ("src/app.py", None),
    ],
)
def test_dependency_kind(path: str, expected: str | None) -> None:
    assert dependency_kind(path) == expected
