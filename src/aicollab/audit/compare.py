"""두 snapshot을 raw byte와 Git tree로 나눠 비교한다.

M0와 Windows 확인에서 LF 파일을 CRLF로 다시 쓰면 raw byte는 달라지고 stage 뒤 tree는
같았다(docs/probes/git-behavior.md G5). 그래서 경로마다 두 비교 결과를 따로 남긴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aicollab.audit.snapshot import FileEntry, MetaEntry, Snapshot
from aicollab.workspace.git import Git, decode_path, display_path, path_bytes, split_nul

RawChange = Literal["added", "deleted", "modified"]
ChangeClass = Literal["raw-and-tree", "raw-only", "tree-only"]
MetaChangeKind = Literal["added", "removed", "changed"]


@dataclass(frozen=True)
class PathChange:
    path: str
    raw: RawChange | None
    tree: str | None  # git diff-tree의 상태 문자(A, D, M, T)

    @property
    def classification(self) -> ChangeClass:
        if self.raw is not None and self.tree is not None:
            return "raw-and-tree"
        return "raw-only" if self.raw is not None else "tree-only"

    def record(self) -> dict[str, object]:
        return {
            "path": display_path(self.path),
            "raw": self.raw,
            "tree": self.tree,
            "classification": self.classification,
        }


@dataclass(frozen=True)
class MetaChange:
    path: str
    change: MetaChangeKind
    category: str

    def record(self) -> dict[str, object]:
        return {
            "path": display_path(self.path),
            "change": self.change,
            "category": self.category,
        }


@dataclass(frozen=True)
class Comparison:
    before: Snapshot
    after: Snapshot
    changes: tuple[PathChange, ...]
    meta_changes: tuple[MetaChange, ...]

    @property
    def head_moved(self) -> bool:
        return self.before.head_oid != self.after.head_oid

    @property
    def raw_changed(self) -> bool:
        return self.before.manifest_sha256 != self.after.manifest_sha256

    @property
    def tree_changed(self) -> bool:
        return self.before.tree_oid != self.after.tree_oid

    def record(self) -> dict[str, object]:
        return {
            "before": {
                "head_oid": self.before.head_oid,
                "tree_oid": self.before.tree_oid,
                "manifest_sha256": self.before.manifest_sha256,
            },
            "after": {
                "head_oid": self.after.head_oid,
                "tree_oid": self.after.tree_oid,
                "manifest_sha256": self.after.manifest_sha256,
            },
            "head_moved": self.head_moved,
            "raw_changed": self.raw_changed,
            "tree_changed": self.tree_changed,
            "changes": [change.record() for change in self.changes],
            "meta_changes": [change.record() for change in self.meta_changes],
        }


def _present(entry: FileEntry | None) -> bool:
    return entry is not None and entry.state == "present"


def _raw_changes(before: Snapshot, after: Snapshot) -> dict[str, RawChange]:
    old = before.by_path()
    new = after.by_path()
    result: dict[str, RawChange] = {}
    for path in old.keys() | new.keys():
        a, b = old.get(path), new.get(path)
        was, now = _present(a), _present(b)
        if was and not now:
            result[path] = "deleted"
        elif now and not was:
            result[path] = "added"
        elif a is not None and b is not None and (a.mode, a.sha256) != (b.mode, b.sha256):
            result[path] = "modified"
    return result


def tree_changes(git: Git, before_tree: str, after_tree: str) -> dict[str, str]:
    """두 tree 사이에 달라진 경로와 상태 문자. 이름 바꿈은 삭제와 추가로 받는다."""
    if before_tree == after_tree:
        return {}
    output = git.run(
        "diff-tree", "-r", "-z", "--no-renames", "--raw", before_tree, after_tree
    ).stdout
    fields = split_nul(output)
    result: dict[str, str] = {}
    for meta, raw_path in zip(fields[0::2], fields[1::2], strict=True):
        status = meta.rsplit(b" ", 1)[-1].decode("ascii")
        result[decode_path(raw_path)] = status[:1]
    return result


def _meta_changes(before: Snapshot, after: Snapshot) -> tuple[MetaChange, ...]:
    old: dict[str, MetaEntry] = {entry.path: entry for entry in before.meta}
    new: dict[str, MetaEntry] = {entry.path: entry for entry in after.meta}
    changes: list[MetaChange] = []
    for path in sorted(old.keys() | new.keys(), key=path_bytes):
        if path not in old:
            changes.append(MetaChange(path, "added", new[path].category))
        elif path not in new:
            changes.append(MetaChange(path, "removed", old[path].category))
        elif old[path] != new[path]:
            changes.append(MetaChange(path, "changed", new[path].category))
    return tuple(changes)


def compare_snapshots(git: Git, before: Snapshot, after: Snapshot) -> Comparison:
    raw = _raw_changes(before, after)
    tree = tree_changes(git, before.tree_oid, after.tree_oid)
    changes = tuple(
        PathChange(path, raw.get(path), tree.get(path))
        for path in sorted(raw.keys() | tree.keys(), key=path_bytes)
    )
    return Comparison(before, after, changes, _meta_changes(before, after))
