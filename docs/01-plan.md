# AI 협업 CLI 확정 기획

기준일: 2026-11-17. 상태: D12와 D13 확정 반영, M0 확인 실험 준비, 구현 전. [설정 명세](02-config-spec.md), [검토 기록](04-review.md), [결정 기록](05-open-decisions.md).

## 결정의 출처와 목표

[01-overview.md 결정 기록](decisions.md#결정-기록)의 2026-11-16 항목과 2026-11-17 결정 기록을 기준으로 한다. 이전 검토 때와 달리 현재 원문에는 이번 8개 결정이 모두 있다. 무변경 성공에 empty commit을 만든다는 기존 기술은 사용자 결정이 아니었으며 철회했다. 경위는 R66에 기록한다.

Python으로 로컬 CLI를 구현한다. 공식 claude와 codex를 호출하고 사용자가 선택한 역할과 순서로 계획, 구현과 리뷰를 실행한다. 테스터를 넣는 flow도 지원한다. 같은 설정은 같은 agent로 묶되 역할마다 새 세션과 권한을 적용한다. planner와 coder는 각각 한 명, tester는 한 명, reviewer는 한 명 이상을 지원한다. Claude-only와 Codex-only가 모두 동작해야 한다.

위협 모델은 trusted-local이다. 본인 저장소에서 AI 실수를 막기 위해 권한 옵션과 도구 제한을 적용하고, 범위 밖 변경을 실행 뒤 탐지해 중단한다. 악의적 저장소와 prompt injection 방어는 보장하지 않는다. test_paths 사전 차단은 MVP 필수가 아니며 사후 탐지와 중단으로 충족한다. 이 한계는 setup 요약, doctor와 run 시작 및 최종 결과에서 표시한다.

## 범위

| 구분 | MVP에 포함 | 이후 단계 또는 범위 밖 |
|---|---|---|
| 언어와 실행 | Python, 본인 로컬의 공식 CLI와 기존 본인 로그인 | 직접 API 호출, 인증 자료 추출과 중계, 원격 대행 |
| 모델과 배정 | 전체 모델 ID registry, 같은 agent의 다중 역할, 복수 reviewer | 복수 planner와 coder, 병렬 쓰기, 투표 |
| flow | 기획자 → 코더 → 리뷰어, 기획자 → 코더 → 테스터 → 리뷰어 | 범용 DAG와 모델의 동적 실행 제어 |
| 환경 | 저장소별 native, Claude 사용 시만 WSL2 선택. 선택하면 Codex와 prepare 및 check도 WSL2 | Codex-only의 WSL2 선택, runtime 혼용 |
| 준비 | workspace 생성 직후 등록 prepare 명령을 오케스트레이터가 직렬 실행, 준비 단계의 의존성 네트워크 허용 | prepare 실패 뒤 자동 명령 대체와 무제한 재시도 |
| 검사 | 기본 켜짐, 기본 flow에서 끄기, tester flow 필수. custom 명령은 doctor 1회 시험 | 검사 중 설치와 네트워크, watch와 자동 소스 수정 |
| 결과 | 변경 있는 성공은 aicollab/<run_id>에 사용자 identity로 commit, 변경 없으면 commit과 push 없이 종료 | patch 결과, empty commit, AI의 Git 쓰기 |
| Git와 공개 | 평소 hooks 실행, 사람 개입 서명은 commit 전 중단, 확인 후 push와 선택적 Draft PR | hooks 우회, 서명 자동 해제, 기존 ref 강제 갱신, merge |
| 보장 | 권한 옵션, 도구 제한과 사후 변경 감사, 중단과 증거 보존 | 악의적 저장소 방어와 prompt injection 차단, OS 수준 경로별 사전 강제 |

작업 대상은 유효한 HEAD가 있는 Git 저장소다. 원본의 staged, unstaged와 untracked 소스가 있으면 경고하고 시작 시 해석한 HEAD commit OID에서 run worktree를 만든다. 그 변경을 run에 복사하지 않는다. 자동 stash, reset과 clean은 하지 않는다. Git 없는 폴더와 submodule 지원은 이후 범위다.

## 개념과 입력 기준

| 용어 | 정의 |
|---|---|
| provider | 공식 CLI의 옵션과 출력을 변환하는 adapter |
| provider registry | 회사와 모델 전체 ID, 확인한 최소 CLI 버전과 근거를 한 Python 모듈에서 관리하는 목록 |
| agent | provider와 모델, effort와 관점의 설정. 세션과 권한은 소유하지 않음 |
| role | 책임과 입력, 출력 및 허용 파일 범위. planner, coder, tester, reviewer |
| pipeline | 고정 flow의 역할 호출과 workspace, prepare, 승인, check, commit 및 publish 순서 |
| run | 요청과 설정, base commit OID에 묶인 실행 |
| snapshot | tracked 파일과 승인 새 파일, 삭제 상태의 byte 기준 manifest와 digest |
| gate | 현재 snapshot의 검사 상태와 전원 리뷰, 차단 등급을 코드로 판단하는 조건 |

작업 소스와 실행 설정을 구분한다. 작업 소스는 고정 HEAD에서 만든 run workspace에서만 읽는다. setup으로 만든 현재 설정과 prepare 및 check argv, 역할 prompt는 사용자가 별도로 확인한 control 입력으로 고정하고 hash를 기록한다. 원본의 미커밋 설정을 control 입력으로 선택했다면 HEAD의 설정과 다르다는 사실을 보여 주며 소스나 자동 commit 대상으로 섞지 않는다. workspace의 설정을 다시 읽어 승인한 명령을 덮어쓰지 않는다.

## setup 순서

1. 기본 flow와 tester flow 중 하나를 고른다.
2. 역할마다 1 Claude, 2 Codex의 회사와 전체 모델 ID를 고르고 effort와 관점을 설정한다. Gemini는 선택 불가인 추가 자리다. 사용할 AI를 따로 묻지 않고 같은 설정은 같은 agent를 재사용한다.
3. 실제 flow에 Claude가 있으면 저장소 runtime을 묻는다. 없으면 windows-native다. WSL2 선택 시 모든 실행은 같은 배포판을 사용한다.
4. 검사를 설정한다. 종류별 후보 또는 직접 입력이며 tester flow는 끄기를 허용하지 않는다.
5. 저장소의 의존성 준비 명령과 생성할 의존성 경로를 등록한다. uv sync, npm ci 등의 실제 argv를 보여 주고 control 설정으로 확인한다.
6. P0부터 P5까지 차단 기준을 고른다. 권장 P2를 제시한다.
7. 확인 후 push 또는 확인 후 push와 Draft PR을 고른다. 기본은 확인 후 push다.

원문이 정하지 않은 시간 상한과 경로 기본값은 설정 명세에서 제안으로 구분한다. D12와 D13은 확정됐다. 기획 문서 다듬기는 멈추고 M0 확인 실험으로 진행한다.

## 실행 순서와 prepare

```text
control 설정 확인과 doctor → 원본 변경 경고, base HEAD OID 고정
→ run worktree 생성과 평소 Git hooks → HEAD 기준 소스 확인
→ prepare(의존성 네트워크 허용) → 준비 결과와 source 및 lock 변화 감사
→ planner → 사람 계획 승인 → coder → [tester] → check 또는 검사 미실행 → reviewer
→ gate 충족 → 변경 없음이면 종료
             → 변경 있으면 서명 준비 확인 → 평소 hooks와 commit → tree 재확인
             → 사람 공개 확인 → push → 선택 시 Draft PR
```

prepare는 모델보다 먼저 실행한다. 등록 명령에 포함된 install script와 자식 프로세스도 실제 준비 작업이다. 명령은 직렬로 실행하고 첫 실패, timeout과 취소에서 prepare-failed로 멈춘다. 부분 환경과 로그는 보존하고 planner와 coder를 시작하지 않는다. uv sync를 다른 명령으로 바꾸거나 npm ci 실패를 npm install로 자동 대체하지 않는다.

prepare 전후 source와 lock을 비교한다. .venv와 node_modules 등 등록한 의존성 산출물은 별도 환경 manifest로 기록하고 모델의 코드 diff와 commit 대상에서 제외한다. source와 lock 변경을 준비 baseline에 묻지 않는다. D12에 따라 기존 lock을 유지한다. lock이 없거나 manifest와 맞지 않으면 중단한다. doctor는 lock 부재를 미리 알리고 사용자가 run 밖에서 uv lock이나 npm install 등으로 한 번 생성하도록 안내한다. run 안의 lock 변경은 중단한다. M0에서 `uv sync`는 lock 부재와 불일치에서 lock을 만들거나 고친 뒤 성공(exit 0)했으므로, 이 중단은 명령의 exit code가 아니라 lock 전후 비교로 건다. [D16](05-open-decisions.md#d16-lock-일치-사전-확인)에 따라 등록 명령 전에 lock 종류별 확인 명령(uv는 `uv lock --check`)을 실행해, `uv sync --frozen`처럼 불일치를 숨기는 등록도 시작 전에 중단한다.

prepare의 네트워크 허용은 프로젝트 의존성 준비용이다. check와 그 자식 프로세스는 network=blocked이며 missing dependency를 설치하지 않는다. 공식 AI 서비스 통신과 사람이 확인한 Git 공개 통신은 의존성 설치 네트워크와 구분한다. hooks는 평소대로 실행하되 준비되지 않은 도구나 외부 통신 요구로 실패하면 우회하지 않고 중단한다. 이 정책의 실제 적용은 단계 0 확인 대상이다.

prepare stdout과 stderr는 운영 진단 자료다. 역할 prompt나 검사 입력, 리뷰 지시로 자동 연결하지 않는다. planner와 coder에는 오케스트레이터가 확인한 준비 완료 상태와 필요한 환경 식별자만 제공한다. tester 입력은 승인 계획과 최신 누적 diff만 유지한다. reviewer는 check 결과와 필요한 준비 상태를 구분해 받으며 준비 로그의 성공 문구를 검사 성공으로 인정하지 않는다.

## check와 수정 회차

직접 입력 검사는 doctor가 별도 probe worktree를 만들고 등록 prepare 성공 뒤 한 번 시험한다. 원본 checkout과 진행 중 run에서는 최초 시험을 하지 않는다. 같은 runtime과 argv, cwd, 시간 상한, 네트워크 차단 및 파일 감사를 적용한다. 실제 테스트 실패와 명령 시작 실패를 구분하고, 유한 종료 및 파일 무변경 관측을 테스트 성공과 별도로 기록한다.

한 번의 시험은 영구 안전 인증이 아니다. 명령과 scripts, 실행 파일 및 버전, 설정과 lock, 환경 조건이 달라지면 관련 시험 기록을 무효화한다. 실제 check마다 시간 상한과 자식 프로세스 종료, 파일 감사를 적용한다. 악의적 subprocess의 모든 외부 부작용을 막는 보장은 아니다.

기본 flow에서 검사를 끄면 not-run-disabled와 completed-unchecked를 사용하고 결과와 공개 확인 및 PR에 “검사 미실행”을 표시한다. tester flow에서는 끌 수 없다. 실행한 검사 실패도 reviewer에게 보내 코드와 테스트 중 수정 대상을 판단한다. 판정이 갈리거나 환경 문제이면 사람에게 넘긴다.

최초 구현은 회차 0이고, reviewer가 요청한 수정 묶음을 시작할 때 공유 회차를 1 소비한다. coder 수정이면 tester flow의 tester와 check 및 모든 리뷰를 다시 실행한다. tester만 수정하면 tester부터 시작한다. 역할을 바꿔도 상한이 초기화되지 않는다. tester에는 코더 설명과 검사 및 prepare 로그를 추가하지 않는다.

기획자 결과에 새 의존성 필요 여부와 근거를 적고 승인 화면에 표시한다. 필요하면 사람이 run 밖에서 의존성을 먼저 추가하고 다시 시작한다. D13에 따라 구현 중 의존성 변경은 자동 재준비하지 않고 중단한다. 코더가 계획에 없던 manifest나 lock을 바꾸면 중단하며, lock 변경은 계획에 있어도 D12에 따라 중단한다.

## trusted-local 완료 조건과 제한

권한 옵션과 도구 제한을 적용하고 source와 test_paths 밖 변경을 실행 뒤 탐지해 중단한다. 자동 복원하지 않는다. test_paths 사전 차단과 승인 목록 밖 읽기 차단, 악의적 controller 위조 방어는 MVP 필수 보장이 아니다. worktree도 보안 sandbox가 아니다. [Git worktree](https://git-scm.com/docs/git-worktree#_refs).

CLI는 “trusted-local: 본인 저장소의 AI 실수 탐지용. 악의적 저장소와 prompt injection 방어 보장 없음. 범위 위반은 실행 뒤 탐지”를 setup 요약, doctor, run 시작과 결과에 표시한다. 권한 시험을 통과했다는 이유로 untrusted 입력까지 안전하다고 표시하지 않는다.

tracked와 승인 새 파일은 내용 hash를 계산하고, 그 밖의 ignored 파일은 경로와 크기 및 수정 시각을 감사한다. prepare 의존성은 환경 manifest로 분리하고 매 단계 전체 내용을 hash하지 않는다. JSON Schema는 구조 검사이며 prompt injection 제거 수단이 아니다. 역할 출력으로 권한과 명령 및 공개 승인을 바꾸지 않는다.

## hooks, commit과 변경 없음

Git hooks는 평소처럼 실행한다. hooksPath를 바꾸거나 no-verify로 우회하지 않는다. worktree 생성 hooks와 prepare 뒤에도 고정 HEAD의 소스를 확인한다. 원본이나 run source의 예상 밖 변경이 있으면 보존하고 중단한다. [Git hooks](https://git-scm.com/docs/githooks).

gate 이후 승인 파일의 Git 결과 tree가 base tree와 같으면 “변경 없음”으로 종료한다. 이 판정은 승인 파일을 stage한 뒤 `git write-tree`를 base commit의 tree와 비교하는 방식으로 M0에서 확인했다. 변경이 없을 때 `git commit`은 exit 1이므로 판정 뒤 commit을 호출하지 않는다. commit과 push, Draft PR은 실행하지 않는다. ignored 의존성이 생겼다는 이유로 코드 변경이 있다고 판단하지 않고 모델의 자기 보고로 무변경을 확정하지 않는다. 실패와 미완료를 무변경 성공으로 바꾸지 않는다.

변경이 있으면 사용자 Git identity로 commit한다. 사람 개입이 필요한 서명은 commit 시작 전에 중단하고 알린다. 서명을 끄거나 unsigned로 바꾸지 않는다. 임의 signing program의 개입 여부를 설정만으로 완전히 예측한다고 보장하지 않는다. 무인 준비를 확인하지 못했으면 시작하지 않고 예상 밖 prompt와 timeout도 실패 처리한다. [Git signing 설정](https://git-scm.com/docs/git-config#Documentation/git-config.txt-gpgprogram).

raw source snapshot과 Git의 expected_tree_oid를 구분한다. M0에서 pre-commit이 다시 stage한 변경은 `git write-tree`와 `HEAD^{tree}`의 차이로, stage 밖 변경과 post-commit 변경은 tree가 같아 `git status`로만 드러났다. 줄바꿈 정규화로 raw byte가 달라도 stage 뒤 tree는 같았다. 두 비교가 모두 필요하다([git-behavior G3](probes/git-behavior.md#g3-hook의-파일-변경과-tree-불일치-탐지), [G5](probes/git-behavior.md#g5-변경-없음-판정)). commit-msg hook은 commit 메시지를 바꿀 수 있다. 메시지 변경을 확인할지는 정하지 않았다. 줄바꿈과 filters의 대응을 기록하고 commit 후 실제 tree와 source를 다시 확인한다. pre-commit이 stage 내용을 고치거나 post-commit이 소스를 바꾸면 기존 검사와 리뷰를 재사용하지 않는다. commit이 이미 생겼으면 committed-unverified와 실제 SHA를 기록하고 publish를 막는다. 자동 reset과 amend를 하지 않는다. 재개하려면 현재 diff의 검사와 리뷰가 필요하다.

## 공개

변경 있는 성공만 aicollab/<run_id>를 공개한다. branch 충돌을 덮어쓰지 않는다. 확인 화면에는 remote와 공개 범위, branch와 SHA, author와 committer, 실제 검사 상태를 표시한다. Draft PR은 제목과 본문 및 base도 확인받는다. 확인은 해당 묶음에만 유효하다.

확인 후 지정 ref만 push하고 기존 ref 강제 갱신과 merge는 하지 않는다. 최초 새 ref는 부재 조건을 둔 생성 전용 lease를 사용한다는 구현안은 기존 설계 제안으로 유지한다. GitHub 공개는 기존 인증만 사용하며 토큰 추출과 자동 로그인은 하지 않는다. PR 미리보기는 로컬에서 만들고 gh pr create --dry-run으로 대신하지 않는다. [Git push](https://git-scm.com/docs/git-push), [gh PR 생성](https://cli.github.com/manual/gh_pr_create).

local-committed, pushed, draft-created와 committed-unverified를 구분한다. push 뒤 PR만 실패하면 이미 공개된 상태를 숨기지 않는다. 재개 전 remote와 기존 PR을 확인하고 필요한 단계만 수행한다.

## 단계와 MVP 완료 조건

| 단계 | 작업과 완료 기준 |
|---|---|
| 0 | Python 실행 환경과 두 CLI의 최소 버전, 구조화 출력, native 및 WSL2 경로, prepare와 check 네트워크 구분, 프로세스 종료와 Git 동작을 확인. 미확인 기능을 성공으로 표시하지 않음. M0(#3부터 #7까지)에서 실행했고 결과는 [docs/probes/](probes/README.md)에 있다. WSL2, check 네트워크 차단, 한도 오류, 실제 서명과 gh는 남은 미확인이다 |
| 1 | setup, 배정 명령, flow 2종과 prepare, tester 및 check, P gate와 무변경 종료, 평소 hooks 및 사용자 commit, 확인 후 publish 구현 |
| 2 | 실행 이력과 비교 실험, custom probe와 준비 캐시의 사용성 개선, 필요한 역할 확장 |
| 이후 별도 검토 | untrusted 저장소와 prompt injection 방어, OS 수준 경로별 사전 차단과 controller 격리. MVP 완료 조건에 포함하지 않음 |

- setup은 flow → 역할별 회사와 모델 → Claude 사용 시 환경 → 검사 → 의존성 준비 명령 → 차단 등급 → 공개 방식 순서를 지킨다.
- planner와 coder 각각 한 명, 복수 reviewer, 같은 agent의 다중 역할과 프리셋 3종을 실제 실행한다.
- 원본 변경을 경고하고 고정 HEAD의 run 소스만 사용한다. 별도 확인한 control 설정을 고정하고 원본 변경을 덮어쓰지 않는다.
- doctor가 lock 부재와 불일치를 확인 명령으로 알리고 run 밖 생성을 안내한다(D16). run 안 lock 변경과 계획 밖 manifest 변경을 탐지해 중단한다. 승인 화면은 계획의 새 의존성 필요 여부를 표시한다.
- workspace 생성 직후 등록 prepare를 실행한다. 성공 후 모델을 시작하며 실패와 부분 상태를 보존한다. 준비 산출물과 소스 및 로그 입력 경계가 동작한다.
- trusted-local 권한 옵션과 도구 제한을 적용하고 범위 밖 source 및 test_paths 변경의 사후 탐지와 중단을 확인한다. 사전 차단 성공은 완료 필수가 아니다.
- cmd wrapper는 공백 없는 경로와 특수문자 없는 인자만 허용하고 나머지를 거부한다(D15).
- custom 검사를 별도 doctor workspace에서 1회 시험하고 검사 off 및 tester flow의 off 거부, 검사 단계 네트워크 차단과 수정 회차를 확인한다.
- 모델별 최소 CLI 버전보다 낮으면 version-warning을 표시하고 probe 호출 결과로 판정한다([D14](05-open-decisions.md#d14-fable과-최소-cli-버전-경고)). 설치 Claude 2.1.316에서 Fable 5.2(최소 2.1.321)의 경고 표시와 probe 결과를 확인한다.
- 평소 hooks를 실행하고, 사람 개입 서명은 commit 전에 중단한다. hook에 의한 tree 변경과 이미 생성된 미검증 commit의 publish를 차단한다.
- gate 성공과 Git 결과 무변경이면 commit과 push 없이 “변경 없음”으로 종료한다. 변경 있으면 사용자 identity commit과 확인 후 공개를 수행한다.
- timeout과 Ctrl+C 후 자식 프로세스 종료를 확인하고 그 전까지 lock을 유지한다. M0에서 Windows의 `Popen.kill()`과 표준 timeout은 손자 프로세스를 남겼으므로 트리 단위 종료가 필요하다. 실제 미확인과 보장 제외 범위를 CLI 결과에 표시한다.

아직 구현 전이다. M0에서 확인 실험용 스크립트로 모델 호출(Claude 18회, Codex 20회), prepare 명령, 임시 저장소의 Git commit과 로컬 bare remote push를 실행했다. 제품 코드의 prepare와 custom probe, 실제 원격 push와 PR 생성은 실행하지 않았다. 다양성 효과와 tester 품질, P 등급 일관성은 고정 작업과 사람 판정으로 이후 측정한다.
