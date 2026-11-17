# M0 확인 실험 결과

공식 CLI와 Git, Windows의 실제 동작을 확인한 결과다. 각 문서에 명령, CLI 버전, 실행 환경, 관찰 결과, 결론(확인됨/다름/확인 불가)이 있다. 실행 스크립트는 `scripts/probes/`에, 익명화한 원본 출력은 `fixtures/`에 있다.

| 이슈 | 문서 | 실행 환경 | 결과 요약 |
|---|---|---|---|
| #3 | [claude-headless.md](claude-headless.md) | Windows 11, Claude Code 2.1.316 | 모델 ID 4개 실행, Fable은 최소 버전 미달에서도 실행. `--tools`와 `--allowedTools` 차단, 공통 Schema 수락. 오류에도 `subtype: success`, 알 수 없는 effort 무시 |
| #4 | [codex-exec.md](codex-exec.md) | Windows 11, Codex CLI 0.167.0-alpha.3.2 | 모델 ID 4개 실행. sandbox 쓰기 차단, read-only에서 명령 작업 폴더가 `-C`와 다름. 공통 Schema 수락, required 누락 거부. 모델별 effort 지원 값, `--ephemeral` 확인 |
| #5 | [windows-process.md](windows-process.md) | Windows 11, Python 3.13.15 | `kill()`과 timeout은 손자를 남김. `taskkill /T`, Job Object, CTRL_BREAK는 종료. 공백 경로의 `cmd /d /s /c` argv 실행 실패와 주입. 자식별 출력 인코딩 차이 |
| #6 | [git-behavior.md](git-behavior.md) | Linux VM, Git 2.34.1 | worktree, hooks, tree 비교, 변경 없음 판정, 생성 전용 push lease 확인. commit-msg의 메시지 변경. 실제 서명과 gh는 미확인 |
| #7 | [prepare-behavior.md](prepare-behavior.md) | Linux 컨테이너, uv 0.11.32, npm 10.9.9 | `uv sync`의 lock 생성과 수정, `--frozen`의 불일치 무시, `npm ci` 실패와 부분 환경, 루트 lifecycle script의 source 변경 |

결과를 기획 문서에 반영한 위치는 [04-review 미확인 사실과 확인 방법](../04-review.md#미확인-사실과-확인-방법)이다. 기존 결정과 맞지 않는 결과는 [05-open-decisions](../05-open-decisions.md#결정됨)의 D14부터 D16까지로 정했다.
