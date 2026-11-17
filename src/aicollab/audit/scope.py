"""역할이 바꾼 경로가 허용 범위 안인지, manifest와 lock을 바꿨는지 판정한다.

판정은 실행 뒤 탐지다. 사전 차단이 아니며 되돌리지 않는다(D06 trusted-local).
lock 변경은 계획 여부와 무관하게 위반이고(D12), manifest 변경은 계획에 없으면 위반이다(D13).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Literal

from aicollab.audit.compare import Comparison, PathChange
from aicollab.workspace.git import display_path

DependencyKind = Literal["manifest", "lock"]
Rule = Literal[
    "out-of-scope", "unplanned-manifest", "lock-changed", "head-moved", "nested-repository"
]

# 파일 이름(소문자)으로 본다. 폴더 깊이와 무관하다.
LOCK_NAMES: frozenset[str] = frozenset(
    {
        "uv.lock",
        "poetry.lock",
        "pdm.lock",
        "pipfile.lock",
        "package-lock.json",
        "npm-shrinkwrap.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lock",
        "bun.lockb",
        "cargo.lock",
        "go.sum",
        "gradle.lockfile",
        "composer.lock",
        "gemfile.lock",
    }
)
MANIFEST_NAMES: frozenset[str] = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "pipfile",
        "package.json",
        "cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "composer.json",
        "gemfile",
    }
)
MANIFEST_PATTERNS: tuple[str, ...] = ("requirements*.txt", "constraints*.txt")


def dependency_kind(path: str) -> DependencyKind | None:
    name = path.rsplit("/", 1)[-1].lower()
    if name in LOCK_NAMES:
        return "lock"
    if name in MANIFEST_NAMES or any(fnmatch.fnmatchcase(name, p) for p in MANIFEST_PATTERNS):
        return "manifest"
    return None


def _matches(path: str, rules: tuple[str, ...]) -> bool:
    """규칙이 `/`로 끝나면 그 폴더 아래 전체, 아니면 정확히 같은 경로."""
    for rule in rules:
        if rule.endswith("/"):
            if path.startswith(rule):
                return True
        elif path == rule:
            return True
    return False


@dataclass(frozen=True)
class RoleScope:
    """한 역할 호출에 허용한 쓰기 범위. 저장소 최상위 기준 `/` 구분 상대 경로다."""

    role: str
    allowed: tuple[str, ...]
    denied: tuple[str, ...] = ()
    planned_manifests: tuple[str, ...] = ()

    def permits(self, path: str) -> bool:
        return _matches(path, self.allowed) and not _matches(path, self.denied)

    def record(self) -> dict[str, object]:
        return {
            "role": self.role,
            "allowed": list(self.allowed),
            "denied": list(self.denied),
            "planned_manifests": list(self.planned_manifests),
        }


@dataclass(frozen=True)
class Violation:
    rule: Rule
    path: str
    detail: str
    raw: str | None = None
    tree: str | None = None

    def record(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "path": display_path(self.path),
            "detail": self.detail,
            "raw": self.raw,
            "tree": self.tree,
        }


def _violation(rule: Rule, change: PathChange, detail: str) -> Violation:
    return Violation(rule, change.path, detail, change.raw, change.tree)


def find_violations(comparison: Comparison, scope: RoleScope) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    if comparison.head_moved:
        violations.append(
            Violation(
                "head-moved",
                "",
                f"작업 공간의 HEAD가 {comparison.before.head_oid}에서 "
                f"{comparison.after.head_oid}로 바뀌었습니다",
            )
        )
    for change in comparison.changes:
        kind = dependency_kind(change.path)
        if kind == "lock":
            violations.append(
                _violation("lock-changed", change, "run 안에서 lock 파일이 바뀌었습니다")
            )
            continue
        if kind == "manifest" and change.path not in scope.planned_manifests:
            violations.append(
                _violation("unplanned-manifest", change, "계획에 없는 manifest가 바뀌었습니다")
            )
            continue
        if kind == "manifest" and not _matches(change.path, scope.denied):
            continue
        if not scope.permits(change.path):
            violations.append(
                _violation(
                    "out-of-scope",
                    change,
                    f"{scope.role} 역할의 허용 범위 밖 경로가 바뀌었습니다",
                )
            )
    for meta in comparison.meta_changes:
        # 안에 다른 Git 저장소가 생긴 폴더는 내용을 감사할 수 없다. 범위 안이어도 위반이다.
        if meta.category == "untracked-dir" and meta.change != "removed":
            violations.append(
                Violation(
                    "nested-repository",
                    meta.path,
                    "작업 공간 안에 다른 Git 저장소가 생기거나 바뀌었습니다",
                )
            )
    return tuple(violations)
