"""이슈 #14: git 실행 환경의 상속 변수 처리와 NUL 구분 출력 해석."""

from __future__ import annotations

from pathlib import Path

from workspace_audit_support import git, isolated_environ, make_repo

from aicollab.workspace.git import (
    UNPARSED_CONFIG_KEY,
    build_git_environment,
    decode_path,
    display_path,
    path_bytes,
    split_nul,
)
from aicollab.workspace.worktree import create_run_workspace


def test_location_variables_are_removed_and_reported() -> None:
    result = build_git_environment(
        {
            "PATH": "/bin",
            "GIT_DIR": "/elsewhere/.git",
            "git_work_tree": "/elsewhere",
            "GIT_INDEX_FILE": "/elsewhere/index",
            "GIT_COMMON_DIR": "x",
            "GIT_OBJECT_DIRECTORY": "x",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": "x",
            "GIT_NAMESPACE": "x",
            "GIT_PREFIX": "x",
        }
    )
    assert dict(result.env) == {"PATH": "/bin"}
    assert result.removed_location_vars == (
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_WORK_TREE",
    )
    (warning,) = result.warnings()
    assert "GIT_DIR" in warning and "GIT_WORK_TREE" in warning
    assert "/elsewhere" not in warning
    assert result.record()["removed_location_vars"] == list(result.removed_location_vars)


def test_config_variables_pass_through_with_keys_and_hash_only() -> None:
    environ = {
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/secret/hooks",
        "GIT_CONFIG_KEY_1": "http.extraHeader",
        "GIT_CONFIG_VALUE_1": "Authorization: Bearer TOKEN-VALUE",
        "GIT_CONFIG_PARAMETERS": "'user.name=Someone Else' 'core.autocrlf'='true'",
        "GIT_CONFIG_GLOBAL": "/home/someone/alt.gitconfig",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    result = build_git_environment(environ)
    assert dict(result.env) == environ
    assert result.removed_location_vars == ()
    assert result.config_vars == tuple(sorted(environ))
    assert result.config_keys == (
        "core.autocrlf",
        "core.hooksPath",
        "http.extraHeader",
        "user.name",
    )
    assert len(result.config_sha256) == 64
    shown = " ".join(result.warnings()) + repr(result.record())
    for name in environ:
        assert name in shown
    for secret in ("/secret/hooks", "TOKEN-VALUE", "Someone Else", "/home/someone"):
        assert secret not in shown

    changed = build_git_environment({**environ, "GIT_CONFIG_VALUE_1": "other"})
    assert changed.config_sha256 != result.config_sha256
    assert changed.config_keys == result.config_keys


def test_unparsable_config_parameters_are_marked() -> None:
    result = build_git_environment({"GIT_CONFIG_PARAMETERS": "'unterminated"})
    assert result.config_keys == (UNPARSED_CONFIG_KEY,)
    assert result.env["GIT_CONFIG_PARAMETERS"] == "'unterminated"


def test_other_git_variables_pass_through_without_warning() -> None:
    environ = {
        "GIT_SSH_COMMAND": "ssh -i key",
        "GIT_ASKPASS": "askpass",
        "GIT_AUTHOR_NAME": "A",
        "GIT_COMMITTER_EMAIL": "c@example.invalid",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": "/home/u",
    }
    result = build_git_environment(environ)
    assert dict(result.env) == environ
    assert result.warnings() == ()
    assert result.config_sha256 == ""
    assert result.record() == {
        "removed_location_vars": [],
        "config_vars": [],
        "config_keys": [],
        "config_sha256": "",
    }


def test_inherited_git_dir_does_not_redirect_the_run(tmp_path: Path) -> None:
    env = isolated_environ(tmp_path)
    target = make_repo(tmp_path / "target", env)
    other = make_repo(tmp_path / "other", env, {"src/app.py": "print('other')\n"})
    other_before = git(other, env, "for-each-ref")
    inherited = {
        **env,
        "GIT_DIR": str(other / ".git"),
        "GIT_WORK_TREE": str(other),
        "GIT_INDEX_FILE": str(tmp_path / "stray.index"),
    }

    workspace = create_run_workspace(target, "run-env", environ=inherited)

    assert workspace.environment.removed_location_vars == (
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_WORK_TREE",
    )
    assert any("GIT_DIR" in warning for warning in workspace.warnings)
    assert git(target, env, "branch", "--list", "aicollab/run-env")
    assert git(other, env, "for-each-ref") == other_before
    assert not (tmp_path / "stray.index").exists()
    assert (workspace.path / "src" / "app.py").read_bytes() == b"print('base')\n"


def test_split_nul_and_path_round_trip() -> None:
    assert split_nul(b"") == []
    assert split_nul(b"a\0b c\0") == [b"a", b"b c"]
    assert split_nul("한글.txt\0줄\n바꿈\0".encode()) == ["한글.txt".encode(), "줄\n바꿈".encode()]
    raw = b"caf\xe9/\xed\x95\x9c.txt"  # UTF-8이 아닌 byte가 섞인 경로
    path = decode_path(raw)
    assert path_bytes(path) == raw
    assert display_path(path) == "caf\\xe9/한.txt"
    assert display_path(decode_path("한글 경로/파일.txt".encode())) == "한글 경로/파일.txt"
