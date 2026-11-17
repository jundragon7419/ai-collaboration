# AI 협업 CLI 기획 문서

기준일: 2026-11-17. 상태: M0 확인 실험 완료와 결과 반영, 구현 전. D01부터 D13까지 결정됐다. M0 결과 중 결정과 맞지 않는 3건을 D14부터 D16까지 새 선택 사항으로 올렸고 아직 결정하지 않았다. 제품 코드의 prepare와 doctor 시험, 실제 원격 push와 PR 생성은 하지 않았다.

| 파일 | 설명 |
|---|---|
| [01-plan.md](01-plan.md) | Python과 trusted-local MVP, 고정 HEAD와 prepare, 평소 hooks 및 무변경 종료, 단계와 완료 조건 |
| [02-config-spec.md](02-config-spec.md) | 확정값과 제안값을 구분한 설정, prepare 및 blocked check, Windows launcher와 최소 CLI 버전, 예시와 프리셋 |
| [03-roles-and-handoff.md](03-roles-and-handoff.md) | 역할 수와 입력, prepare/check/check-probe 분리, 역할 및 시스템 기록 Schema, 실패와 Git 인계 |
| [04-review.md](04-review.md) | 기존 항목 상태 갱신, 3차 R56부터 R71까지, empty commit 오류의 경위, 미확인과 M0 결과, 점검 결과 |
| [05-open-decisions.md](05-open-decisions.md) | 결정된 D01부터 D13까지, M0 결과로 생긴 선택 사항 D14부터 D16까지 |
| [probes/](probes/README.md) | M0 확인 실험 결과 5건(Claude Code, Codex exec, Windows 프로세스, Git, prepare)과 fixture |

결정 source는 [docs/decisions.md 결정 기록](decisions.md#결정-기록)이다. 현재 원문에 2026-11-17 결정 :19-28이 모두 있다. 이전의 누락 보고는 당시 이력으로 남겼고 현재 결정으로 사용하지 않는다. claude-docs는 읽기만 한다.

## 결정 상태

- 기존 8개였던 D01, D05부터 D11까지를 모두 결정됨으로 옮겼다. Python, trusted-local, planner와 coder 각각 한 명, warn-head, custom doctor 1회 시험, Windows 직접 실행과 제한 wrapper, 자동 prepare, 평소 hooks와 사람 개입 서명의 중단이 적용된다.
- 무변경 성공은 “변경 없음”으로 종료하며 commit과 push 및 PR을 만들지 않는다. empty commit을 사용자 결정으로 쓴 R55를 철회하고 R66에 경위를 기록했다.
- D12는 기존 lock 유지와 부재 및 불일치 시 중단, D13은 새 의존성 필요 표시와 자동 재준비 중단으로 확정됐다. 원문 밖 경로와 timeout 및 회차 기본값은 제안이다.

## 검토 집계

| 구분 | 전체 | 높음 | 중간 | 낮음 |
|---|---|---|---|---|
| 1차 발견 이력 | 31 | 16 | 14 | 1 |
| 2차 R32부터 R55까지 | 24 | 11 | 10 | 3 |
| 3차 R56부터 R71까지 | 16 | 8 | 7 | 1 |
| 전체 발견 이력 | 71 | 35 | 31 | 5 |

위 집계는 당시 분류와 철회 2건을 포함한 이력이며 현재 열린 결함 수가 아니다. R03은 다중 배정을 필수 요구로 본 오류, R55는 empty commit을 결정으로 만든 오류로 철회했다. 철회를 제외한 검토 기록은 69건이다.

## 확인과 점검 상태

Claude 2.1.316은 Fable의 최소 2.1.321보다 낮다. doctor는 agent의 version-check를 실패시키고 모델을 호출하지 않아야 한다. M0에서는 2.1.316의 Fable 호출이 성공해 [D14](05-open-decisions.md#d14-fable과-최소-cli-버전-규칙)로 올렸다. 결정 전까지 기존 규칙을 유지한다. Node v24.14.0과 직접 npm 및 npx JS의 11.9.0은 M0에서 다시 확인했다. 다른 version manager 및 Corepack 환경, check 네트워크 차단, 한도 오류, 실제 서명과 gh는 미확인이다. 미확인 목록과 M0 결과의 대응은 [04-review 미확인 사실과 확인 방법](04-review.md#미확인-사실과-확인-방법)에 있다.

trusted-local은 본인 저장소에서 AI 실수를 사후 탐지하는 범위다. 악의적 저장소와 prompt injection 방어, test_paths 사전 차단은 MVP 보장이 아니다. 검사 단계의 네트워크 정책은 blocked이며 prepare 허용과 구분한다.

정적 점검: TOML 6개와 JSON 7개, Schema 부분집합 3개와 역할 결과 예시 3개, 프리셋 참조 및 확정 정책 조건 검사 통과. 상대 링크와 내부 anchor 74개, UTF-8과 문장 규칙, 번호 및 집계 점검 통과. 원문 5개의 SHA-256 일치. jsonschema 미설치로 별도 meta-schema 검증은 하지 않았고 prepare와 검사 시험, 모델 호출 및 Git end-to-end도 실행하지 않았다. [산출물 점검 상태](04-review.md#산출물-점검-상태).
