"""감사 기록과 위반 증거를 run 제어 영역에 남긴다.

작업 공간은 되돌리지 않는다. 위반이 있으면 그 시점의 파일 byte 사본과 patch를 따로
남겨, 작업 공간이 나중에 바뀌어도 증거가 남게 한다.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from aicollab.audit.compare import Comparison
from aicollab.audit.scope import RoleScope, Violation
from aicollab.workspace.git import Git, display_path


def _write_json(path: Path, data: object) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def _copy_current(root: Path, path: str, dest: Path) -> dict[str, object]:
    """위반 경로의 현재 byte를 dest에 복사한다. symlink는 대상 문자열을 남긴다."""
    entry: dict[str, object] = {"path": display_path(path)}
    full = root / path
    try:
        info = os.lstat(full)
    except (FileNotFoundError, NotADirectoryError):
        entry["state"] = "deleted"
        return entry
    if stat.S_ISLNK(info.st_mode):
        data = os.fsencode(os.readlink(full))
        entry["state"] = "symlink"
    elif stat.S_ISREG(info.st_mode):
        data = full.read_bytes()
        entry["state"] = "present"
    else:
        entry["state"] = "not-a-file"
        return entry
    dest.write_bytes(data)
    entry["copy"] = f"{dest.parent.name}/{dest.name}"
    entry["size"] = len(data)
    entry["sha256"] = hashlib.sha256(data).hexdigest()
    return entry


def write_audit_record(
    git: Git,
    comparison: Comparison,
    scope: RoleScope,
    violations: tuple[Violation, ...],
    dest: Path,
) -> Path:
    """dest에 감사 기록을 쓴다. dest가 이미 있으면 덮어쓰지 않고 실패한다."""
    dest.mkdir(parents=True, exist_ok=False)
    _write_json(dest / "before.manifest.json", comparison.before.record())
    _write_json(dest / "after.manifest.json", comparison.after.record())
    summary: dict[str, object] = {
        "scope": scope.record(),
        "comparison": comparison.record(),
        "violations": [violation.record() for violation in violations],
        "git_environment": git.environment.record(),
        "workspace_restored": False,
    }
    if violations:
        patch = git.run(
            "diff",
            "--binary",
            "--no-renames",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            comparison.before.tree_oid,
            comparison.after.tree_oid,
        ).stdout
        (dest / "changes.patch").write_bytes(patch)
        files_dir = dest / "files"
        files_dir.mkdir()
        copies = []
        paths = sorted({v.path for v in violations if v.path})
        for number, path in enumerate(paths, start=1):
            # 경로에 Windows에서 쓸 수 없는 문자가 있을 수 있어 번호로 이름을 붙인다.
            copies.append(_copy_current(git.cwd, path, files_dir / f"{number:04d}.bin"))
        summary["evidence"] = {"patch": "changes.patch", "files": copies}
    _write_json(dest / "audit.json", summary)
    return dest
