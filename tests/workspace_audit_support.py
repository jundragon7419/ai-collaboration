"""이슈 #14 테스트의 임시 Git 저장소 도구. 사용자 저장소와 전역 설정을 쓰지 않는다."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def isolated_environ(tmp_path: Path) -> dict[str, str]:
    """테스트용 상속 환경. 실행한 쪽의 GIT_* 변수를 빼고 임시 전역 설정만 가리킨다."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    config = tmp_path / "global.gitconfig"
    if not config.exists():
        config.write_text(
            "[user]\n\tname = Test User\n\temail = test@example.invalid\n"
            "[init]\n\tdefaultBranch = main\n[core]\n\tautocrlf = false\n",
            encoding="utf-8",
            newline="\n",
        )
    env["GIT_CONFIG_GLOBAL"] = str(config)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def git(cwd: Path, env: dict[str, str], *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, check=True)
    return proc.stdout.decode("utf-8", "replace").strip()


def write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)


def make_repo(path: Path, env: dict[str, str], files: dict[str, bytes | str] | None = None) -> Path:
    """`* text=auto eol=lf`와 기본 파일이 있는 저장소를 만들고 한 번 commit한다."""
    path.mkdir(parents=True)
    git(path, env, "init", "-q")
    content: dict[str, bytes | str] = {
        ".gitattributes": "* text=auto eol=lf\n",
        ".gitignore": "node_modules/\n.venv/\n.aicollab/runs/\n",
        "src/app.py": "print('base')\n",
        "tests/test_app.py": "def test_base():\n    assert True\n",
        "pyproject.toml": '[project]\nname = "sample"\n',
        "uv.lock": "version = 1\n",
    }
    content.update(files or {})
    for name, data in content.items():
        write(path / name, data)
    git(path, env, "add", "-A")
    git(path, env, "commit", "-q", "-m", "base")
    return path
