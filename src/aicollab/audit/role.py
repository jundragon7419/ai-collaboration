"""역할 호출 한 번의 실행 전후 감사."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aicollab.audit.compare import Comparison, compare_snapshots
from aicollab.audit.evidence import write_audit_record
from aicollab.audit.scope import RoleScope, Violation, find_violations
from aicollab.audit.snapshot import Snapshot, take_snapshot
from aicollab.workspace.git import Git


@dataclass(frozen=True)
class AuditResult:
    scope: RoleScope
    comparison: Comparison
    violations: tuple[Violation, ...]
    record_dir: Path

    @property
    def ok(self) -> bool:
        """위반이 없다. False면 호출한 쪽이 run을 중단한다."""
        return not self.violations


def audit_role(git: Git, before: Snapshot, scope: RoleScope, record_dir: Path) -> AuditResult:
    """역할 실행 뒤 snapshot을 수집해 before와 비교하고 기록을 record_dir에 남긴다.

    위반이 있어도 작업 공간을 되돌리지 않는다. record_dir은 작업 공간 밖이어야 한다.
    """
    workspace = git.cwd.resolve()
    target = record_dir.resolve()
    if target == workspace or target.is_relative_to(workspace):
        raise ValueError(f"감사 기록 폴더가 작업 공간 안에 있습니다: {record_dir}")
    after = take_snapshot(git)
    comparison = compare_snapshots(git, before, after)
    violations = find_violations(comparison, scope)
    write_audit_record(git, comparison, scope, violations, record_dir)
    return AuditResult(scope, comparison, violations, record_dir)
