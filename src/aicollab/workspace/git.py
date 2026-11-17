"""오케스트레이터가 실행하는 git의 환경 변수 처리와 실행 도구.

환경 변수 처리는 이슈 #14에서 정했다(docs/probes/git-behavior.md "상속 환경 변수 처리").

- 저장소 위치를 바꾸는 변수는 항상 지우고 이름을 경고와 기록에 남긴다.
- 명령 범위 설정 변수와 설정 파일 위치 변수는 그대로 넘긴다. 변수 이름과 설정 key를
  경고와 기록에 남기고, 값은 남기지 않고 전체의 SHA-256만 남긴다.
- 그 밖의 GIT_* 변수는 그대로 넘기고 경고하지 않는다.

git 출력은 bytes로 받는다. 경로 목록은 NUL 구분(-z) 출력만 해석한다.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# cwd와 무관하게 대상 저장소, 작업 트리, index, object 저장 위치를 바꾸는 변수.
LOCATION_VARS: frozenset[str] = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
    }
)

# 설정 파일 위치를 가리키는 변수.
CONFIG_FILE_VARS: frozenset[str] = frozenset(
    {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM"}
)

_CONFIG_KEY_VAR = re.compile(r"GIT_CONFIG_KEY_\d+")
_CONFIG_VALUE_VAR = re.compile(r"GIT_CONFIG_VALUE_\d+")

UNPARSED_CONFIG_KEY = "<해석 실패>"


def _is_command_config_var(upper_name: str) -> bool:
    return (
        upper_name in {"GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"}
        or _CONFIG_KEY_VAR.fullmatch(upper_name) is not None
        or _CONFIG_VALUE_VAR.fullmatch(upper_name) is not None
    )


def _keys_from_parameters(value: str) -> list[str]:
    """GIT_CONFIG_PARAMETERS에서 설정 key만 꺼낸다. 값은 돌려주지 않는다."""
    try:
        tokens = shlex.split(value, posix=True)
    except ValueError:
        return [UNPARSED_CONFIG_KEY]
    keys = []
    for token in tokens:
        key = token.split("=", 1)[0].strip()
        keys.append(key or UNPARSED_CONFIG_KEY)
    return keys


@dataclass(frozen=True)
class GitEnvironment:
    """git 자식 프로세스에 넘길 환경과 그 처리 기록."""

    env: Mapping[str, str]
    removed_location_vars: tuple[str, ...]
    config_vars: tuple[str, ...]
    config_keys: tuple[str, ...]
    config_sha256: str

    def warnings(self) -> tuple[str, ...]:
        """run 시작에 표시할 경고 문장."""
        messages = []
        if self.removed_location_vars:
            names = ", ".join(self.removed_location_vars)
            messages.append(f"저장소 위치를 바꾸는 상속 환경 변수를 지우고 실행합니다: {names}")
        if self.config_vars:
            names = ", ".join(self.config_vars)
            keys = ", ".join(self.config_keys) if self.config_keys else "없음"
            messages.append(
                "상속된 Git 설정 환경 변수를 그대로 적용합니다: "
                f"{names} (설정 key: {keys}, sha256: {self.config_sha256})"
            )
        return tuple(messages)

    def record(self) -> dict[str, object]:
        """run 기록에 남길 내용. 변수 값은 넣지 않는다."""
        return {
            "removed_location_vars": list(self.removed_location_vars),
            "config_vars": list(self.config_vars),
            "config_keys": list(self.config_keys),
            "config_sha256": self.config_sha256,
        }


def build_git_environment(environ: Mapping[str, str] | None = None) -> GitEnvironment:
    """상속 환경에서 git 실행 환경을 만든다. 변수 이름은 대소문자를 구분하지 않고 본다."""
    source = dict(os.environ if environ is None else environ)
    env: dict[str, str] = {}
    removed: list[str] = []
    config: list[tuple[str, str]] = []
    keys: list[str] = []
    for name, value in source.items():
        upper = name.upper()
        if upper in LOCATION_VARS:
            removed.append(upper)
            continue
        env[name] = value
        if upper in CONFIG_FILE_VARS or _is_command_config_var(upper):
            config.append((upper, value))
            if _CONFIG_KEY_VAR.fullmatch(upper):
                keys.append(value)
            elif upper == "GIT_CONFIG_PARAMETERS":
                keys.extend(_keys_from_parameters(value))
    config.sort()
    digest = ""
    if config:
        hasher = hashlib.sha256()
        for name, value in config:
            hasher.update(name.encode("utf-8") + b"\0")
            hasher.update(value.encode("utf-8", "surrogateescape") + b"\0")
        digest = hasher.hexdigest()
    return GitEnvironment(
        env=env,
        removed_location_vars=tuple(sorted(removed)),
        config_vars=tuple(name for name, _ in config),
        config_keys=tuple(sorted(set(keys))),
        config_sha256=digest,
    )


class GitError(RuntimeError):
    """git 명령이 0이 아닌 exit code로 끝났다."""

    def __init__(self, argv: Sequence[str], returncode: int, stderr: bytes) -> None:
        self.argv = tuple(argv)
        self.returncode = returncode
        self.stderr = stderr
        detail = stderr.decode("utf-8", "replace").strip()
        super().__init__(f"{' '.join(self.argv)} 실패 (exit {returncode}): {detail}")


@dataclass(frozen=True)
class GitResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class Git:
    """한 작업 디렉터리에서 argv 배열로 git을 실행한다."""

    cwd: Path
    environment: GitEnvironment
    executable: str = "git"

    def run(
        self,
        *args: str,
        check: bool = True,
        extra_env: Mapping[str, str] | None = None,
    ) -> GitResult:
        """git을 실행한다. extra_env는 오케스트레이터가 직접 정한 값만 넣는다."""
        argv = (self.executable, *args)
        env = dict(self.environment.env)
        if extra_env:
            env.update(extra_env)
        proc = subprocess.run(
            argv,
            cwd=self.cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        if check and proc.returncode != 0:
            raise GitError(argv, proc.returncode, proc.stderr)
        return GitResult(argv, proc.returncode, proc.stdout, proc.stderr)

    def line(self, *args: str) -> str:
        """한 줄 출력(object ID, ref 이름)을 문자열로 받는다. 경로 출력에는 쓰지 않는다."""
        return self.run(*args).stdout.decode("utf-8", "replace").strip()

    def at(self, cwd: Path) -> Git:
        return Git(cwd, self.environment, self.executable)


def split_nul(data: bytes) -> list[bytes]:
    """NUL로 끝나는 레코드 목록을 나눈다."""
    if not data:
        return []
    parts = data.split(b"\0")
    if parts[-1] == b"":
        parts.pop()
    return parts


def decode_path(raw: bytes) -> str:
    """git이 준 경로 byte를 내부 경로 문자열로 바꾼다. 원래 byte로 되돌릴 수 있다."""
    return raw.decode("utf-8", "surrogateescape")


def path_bytes(path: str) -> bytes:
    """내부 경로 문자열을 git이 준 byte로 되돌린다."""
    return path.encode("utf-8", "surrogateescape")


def display_path(path: str) -> str:
    """기록과 화면에 쓸 경로. UTF-8로 해석할 수 없는 byte는 \\xNN으로 적는다."""
    return path_bytes(path).decode("utf-8", "backslashreplace")
