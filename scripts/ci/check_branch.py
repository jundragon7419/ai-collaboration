"""PR의 head 브랜치 이름과 본문의 이슈 연결을 검사한다.

규칙은 CONTRIBUTING.md "브랜치" 절에 있다. CI의 check 작업이 PR마다 실행한다.
표준 라이브러리만 쓴다. 프로젝트 골격 전에도 돌아야 하기 때문이다.
"""

from __future__ import annotations

import os
import re
import sys

BRANCH_KINDS = ("feat", "fix", "refactor", "test", "probe", "docs", "chore")

BRANCH_PATTERN = re.compile(
    rf"^({'|'.join(BRANCH_KINDS)})/([1-9][0-9]*)-([a-z0-9]+(?:-[a-z0-9]+)*)$"
)

CLOSES_PATTERN = re.compile(r"\bcloses\s+#(\d+)\b", re.IGNORECASE)


def closed_issues(body: str | None) -> list[int]:
    """PR 본문에서 `Closes #N`으로 연결한 이슈 번호를 모은다."""
    return [int(m.group(1)) for m in CLOSES_PATTERN.finditer(body or "")]


def check_pull_request(head: str, base: str, body: str | None) -> list[str]:
    """규칙에 어긋난 내용을 돌려준다. 비어 있으면 통과."""
    # 배포 PR은 develop을 그대로 main에 합친다.
    if base == "main" and head == "develop":
        return []

    match = BRANCH_PATTERN.match(head)
    if not match:
        return [
            f'브랜치 이름 "{head}"이 규칙과 다릅니다. 형식: <종류>/<이슈 번호>-<짧은 설명>, '
            f"종류: {', '.join(BRANCH_KINDS)}, 짧은 설명: 영어 소문자, 숫자, 하이픈"
        ]
    issue = int(match.group(2))
    if issue not in closed_issues(body):
        return [f'PR 본문에 브랜치의 이슈 번호와 같은 "Closes #{issue}"가 없습니다.']
    return []


def main() -> int:
    head = os.environ.get("HEAD_REF", "")
    errors = check_pull_request(
        head=head,
        base=os.environ.get("BASE_REF", ""),
        body=os.environ.get("PR_BODY"),
    )
    for error in errors:
        print(f"::error::{error}")
    if errors:
        return 1
    print(f"브랜치 이름 확인: {head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
