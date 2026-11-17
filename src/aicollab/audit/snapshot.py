"""작업 공간의 raw source snapshot과 Git tree OID를 수집한다.

raw manifest는 tracked 파일과 ignore되지 않은 untracked 파일의 경로, mode, 삭제 여부,
디스크 byte의 SHA-256이다. 줄바꿈을 통일하지 않는다. Git tree OID는 임시 index에
`git add -A`를 실행해 얻으므로 attributes와 filters가 적용된 결과다. 두 값은 서로 다른
것을 보므로 직접 같다고 비교하지 않는다(docs/03-roles-and-handoff.md "snapshot과 검사 기록").
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from aicollab.workspace.git import Git, decode_path, display_path, path_bytes, split_nul

FileState = Literal["present", "deleted"]
FileKind = Literal["tracked", "untracked"]
MetaCategory = Literal["ignored", "untracked-dir"]

MODE_FILE = "100644"
MODE_EXECUTABLE = "100755"
MODE_SYMLINK = "120000"
MODE_GITLINK = "160000"

_MAX_ATTEMPTS = 3
_CHUNK = 1024 * 1024


class SnapshotUnstableError(RuntimeError):
    """수집하는 동안 파일이 계속 바뀌어 snapshot을 고정하지 못했다."""


class _Changed(Exception):
    pass


@dataclass(frozen=True)
class FileEntry:
    """내용 hash를 계산한 파일 한 개."""

    path: str
    kind: FileKind
    mode: str
    state: FileState
    size: int
    sha256: str

    def record(self) -> dict[str, object]:
        return {
            "path": display_path(self.path),
            "kind": self.kind,
            "mode": self.mode,
            "state": self.state,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class MetaEntry:
    """내용을 hash하지 않고 경로, 종류, 크기, 수정 시각만 본 항목."""

    path: str
    category: MetaCategory
    type: str
    size: int
    mtime_ns: int

    def record(self) -> dict[str, object]:
        return {
            "path": display_path(self.path),
            "category": self.category,
            "type": self.type,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
        }


@dataclass(frozen=True)
class Snapshot:
    head_oid: str
    tree_oid: str
    manifest_sha256: str
    entries: tuple[FileEntry, ...]
    meta: tuple[MetaEntry, ...]

    def by_path(self) -> dict[str, FileEntry]:
        return {entry.path: entry for entry in self.entries}

    def record(self) -> dict[str, object]:
        return {
            "head_oid": self.head_oid,
            "tree_oid": self.tree_oid,
            "manifest_sha256": self.manifest_sha256,
            "entries": [entry.record() for entry in self.entries],
            "meta": [entry.record() for entry in self.meta],
        }


def manifest_digest(entries: tuple[FileEntry, ...]) -> str:
    """경로 byte 순으로 정렬한 manifest의 SHA-256. 필드는 NUL로 구분한다."""
    hasher = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: path_bytes(item.path)):
        for field in (
            path_bytes(entry.path),
            entry.mode.encode("ascii"),
            entry.state.encode("ascii"),
            entry.sha256.encode("ascii"),
        ):
            hasher.update(field + b"\0")
    return hasher.hexdigest()


def _stat_key(info: os.stat_result) -> tuple[int, int, int]:
    return (info.st_mode, info.st_size, info.st_mtime_ns)


def _disk_mode(info: os.stat_result, fallback: str) -> str:
    if stat.S_ISLNK(info.st_mode):
        return MODE_SYMLINK
    if os.name == "nt":
        # Windows 파일 시스템에는 실행 bit가 없어 index의 mode를 그대로 쓴다.
        return fallback
    return MODE_EXECUTABLE if info.st_mode & 0o111 else MODE_FILE


def _hash_file(root: Path, path: str, kind: FileKind, index_mode: str) -> FileEntry:
    if index_mode == MODE_GITLINK:
        # submodule은 지원 범위 밖이다. 안을 읽지 않고 항목만 남긴다.
        return FileEntry(path, kind, MODE_GITLINK, "present", 0, "")
    full = root / path
    try:
        before = os.lstat(full)
    except (FileNotFoundError, NotADirectoryError):
        return FileEntry(path, kind, index_mode, "deleted", 0, "")
    if stat.S_ISDIR(before.st_mode):
        # 파일이 있던 자리가 폴더가 됐다. 그 안의 파일은 untracked 목록에 따로 나온다.
        return FileEntry(path, kind, index_mode, "deleted", 0, "")
    hasher = hashlib.sha256()
    size = 0
    try:
        if stat.S_ISLNK(before.st_mode):
            # symlink는 따라가지 않고 대상 문자열을 hash한다.
            target = os.fsencode(os.readlink(full))
            hasher.update(target)
            size = len(target)
        elif stat.S_ISREG(before.st_mode):
            with open(full, "rb") as handle:
                while chunk := handle.read(_CHUNK):
                    hasher.update(chunk)
                    size += len(chunk)
        after = os.lstat(full)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise _Changed from exc
    if _stat_key(before) != _stat_key(after):
        raise _Changed
    return FileEntry(
        path, kind, _disk_mode(before, index_mode), "present", size, hasher.hexdigest()
    )


def _meta_entry(root: Path, raw_path: str, category: MetaCategory) -> MetaEntry | None:
    path = raw_path.rstrip("/")
    try:
        info = os.lstat(root / path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    if stat.S_ISLNK(info.st_mode):
        kind = "symlink"
    elif stat.S_ISDIR(info.st_mode):
        kind = "dir"
    elif stat.S_ISREG(info.st_mode):
        kind = "file"
    else:
        kind = "other"
    size = info.st_size if kind == "file" else 0
    return MetaEntry(path, category, kind, size, info.st_mtime_ns)


def _tracked_modes(git: Git) -> dict[str, str]:
    modes: dict[str, str] = {}
    for record in split_nul(git.run("ls-files", "-s", "-z").stdout):
        header, _, raw_path = record.partition(b"\t")
        mode = header.split(b" ", 1)[0].decode("ascii")
        # 충돌 상태면 같은 경로가 stage별로 여러 번 나온다. 첫 항목만 쓴다.
        modes.setdefault(decode_path(raw_path), mode)
    return modes


def _collect(git: Git) -> tuple[tuple[FileEntry, ...], tuple[MetaEntry, ...]]:
    root = git.cwd
    entries: list[FileEntry] = []
    meta: list[MetaEntry] = []
    tracked = _tracked_modes(git)
    for path, mode in tracked.items():
        entries.append(_hash_file(root, path, "tracked", mode))
    others = git.run("ls-files", "-z", "--others", "--exclude-standard").stdout
    for raw in split_nul(others):
        path = decode_path(raw)
        if path.endswith("/"):
            # 안에 다른 Git 저장소가 있는 폴더는 한 줄로 나온다. 안을 읽지 않는다.
            entry = _meta_entry(root, path, "untracked-dir")
            if entry is not None:
                meta.append(entry)
            continue
        if path in tracked:
            continue
        hashed = _hash_file(root, path, "untracked", MODE_FILE)
        if hashed.state == "deleted":
            raise _Changed
        entries.append(hashed)
    ignored = git.run(
        "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory"
    ).stdout
    for raw in split_nul(ignored):
        entry = _meta_entry(root, decode_path(raw), "ignored")
        if entry is not None:
            meta.append(entry)
    entries.sort(key=lambda item: path_bytes(item.path))
    meta.sort(key=lambda item: path_bytes(item.path))
    return tuple(entries), tuple(meta)


def write_tree(git: Git, exclude: tuple[str, ...] = ()) -> str:
    """작업 트리 전체를 stage한 결과의 tree OID. 작업 공간의 실제 index는 바꾸지 않는다.

    임시 index 파일을 쓰므로 blob과 tree object는 저장소의 object DB에 남는다.
    exclude는 stage하지 않을 경로다. 안에 다른 Git 저장소가 있는 untracked 폴더를 넘긴다.
    """
    pathspec = [".", *(f":(exclude,literal){path}" for path in exclude)]
    with tempfile.TemporaryDirectory(prefix="aicollab-index-") as tmp:
        index_env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git.run("read-tree", "HEAD", extra_env=index_env)
        git.run("add", "-A", "--", *pathspec, extra_env=index_env)
        tree = git.run("write-tree", extra_env=index_env).stdout
    return tree.decode("ascii").strip()


def take_snapshot(git: Git) -> Snapshot:
    """git.cwd(작업 트리의 최상위 폴더)의 snapshot을 수집한다."""
    for _ in range(_MAX_ATTEMPTS):
        try:
            entries, meta = _collect(git)
        except _Changed:
            continue
        nested = tuple(item.path for item in meta if item.category == "untracked-dir")
        tree_oid = write_tree(git, nested)
        try:
            again, _ = _collect(git)
        except _Changed:
            continue
        if again != entries:
            continue
        head_oid = git.line("rev-parse", "--verify", "HEAD^{commit}")
        return Snapshot(head_oid, tree_oid, manifest_digest(entries), entries, meta)
    raise SnapshotUnstableError(
        f"snapshot을 수집하는 동안 파일이 계속 바뀌었습니다 ({_MAX_ATTEMPTS}회 시도)"
    )
