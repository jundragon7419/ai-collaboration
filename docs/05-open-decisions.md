# 사용자 결정과 남은 항목

기준일: 2026-11-17. D01부터 D16까지 결정됨이다. D14부터 D16까지는 M0 확인 실험 결과가 기존 결정과 맞지 않아 새로 정한 항목이다. 원문은 [01-overview.md 결정 기록](decisions.md#결정-기록) :19-28이다.

## 결정됨

### D01 구현 언어

Python으로 구현한다. 다른 언어 선택지는 닫았다. 대화형 setup, subprocess와 Windows 프로세스 관리도 Python 구현 범위다. Python 최소 버전과 packaging 방식은 사용자 결정으로 꾸미지 않고 구현 시 제안한다.

### D02 Windows 실행 환경

저장소마다 정한다. 실제 flow에서 Claude를 쓰는 경우만 windows-native와 WSL2를 제시하고, Claude가 없으면 windows-native다. WSL2를 고르면 Codex와 prepare 및 check도 같은 배포판 안에서 실행한다.

별도 Git과 CLI 및 의존성, 로그인과 디스크 비용이 있다. native Claude shell에 Bash sandbox가 적용되지 않는다는 사실은 trusted-local 결정으로 없어지지 않는다. 사전 격리를 MVP에 강제하지 않으며 실제 쓰는 권한 옵션과 사후 감사 수준을 표시한다. WSL2 설치와 현재 여유 공간은 미확인이다. [Claude sandbox](https://code.claude.com/docs/en/sandboxing).

### D03 결과 보존과 공개

변경 있는 성공 run은 aicollab/<run_id>에 오케스트레이터가 사용자 Git identity로 commit한다. 기본은 확인 후 push이고 선택은 확인 후 push와 Draft PR이다. patch 결과는 없고 merge는 도구가 하지 않는다.

변경 없는 성공 run은 commit과 push 없이 “변경 없음”으로 끝낸다. Draft PR도 만들지 않는다. 기존의 “결정대로 empty commit”은 원문에 없는 추론을 사용자 결정으로 잘못 기록한 것이며 철회했다. R55의 해당 판단을 정정하고 경위를 [R66](04-review.md#r66-empty-commit을-사용자-결정으로-기록한-오류)에 남겼다. 실패와 미완료를 무변경 성공으로 바꾸지 않는다.

### D04 리뷰 차단 등급

P0부터 P5까지 중 고른 등급까지 차단하고 권장은 P2다. 원문 :17의 등급 정의를 03-roles-and-handoff에 반영한다. 취향은 어느 등급에도 넣지 않는다. 실제 check 실패와 리뷰 미완료는 등급을 낮춰 통과시키지 않는다.

### D05 의존성 준비

저장소에 준비 명령을 등록하고 작업 공간을 만든 직후 오케스트레이터가 실행한다. 준비 성공 뒤 planner와 coder로 진행한다. 프로젝트 의존성 네트워크는 이 준비 단계에서 허용하고 검사에서는 막는다. 이전의 run마다 사용자가 직접 환경을 준비한다는 추천은 채택되지 않았다.

등록한 uv sync와 npm ci 등은 install script와 자식 프로세스 실행을 포함할 수 있다. 원문은 그 script를 일괄 끄라고 결정하지 않았다. 명령과 toolchain, 산출물과 source 및 lock 변화, 실패와 부분 상태를 감사한다. 등록 명령을 자동 대체하지 않는다. lock 유지와 구현 중 재준비 중단은 D12와 D13으로 확정했다. [uv sync](https://docs.astral.sh/uv/concepts/projects/sync/), [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/).

### D06 위협 모델

trusted-local로 확정했다. 본인 저장소에서 AI의 실수를 막기 위해 권한 옵션과 도구 제한을 적용하고 범위 밖 변경은 실행 뒤 탐지해 중단한다. 악의적 저장소와 prompt injection 방어는 보장하지 않는다. test_paths 사전 차단은 MVP 필수가 아니며 사후 탐지와 중단으로 충족한다.

untrusted의 OS 격리와 사전 강제 조건은 이후 검토로 옮겼다. 새 CLI에 trusted-local과 보장 제외 범위를 표시하며 사후 탐지를 사전 차단 제품처럼 설명하지 않는다. 이 결정을 다시 보안 선택지로 묻지 않는다.

### D07 기획자와 코더 수

planner와 coder는 각각 정확히 한 명이다. reviewer 여러 명은 지원한다. 같은 agent를 서로 다른 역할에 재사용할 수 있지만 새 세션과 role 권한을 매번 적용한다. 다중 planner와 coder는 MVP 옵션이 아니다.

### D08 Windows 실행과 wrapper

실행 파일을 직접 실행한다. npm과 npx는 .cmd 대신 확인한 node와 npm JS 진입점을 호출한다. gradlew와 mvn처럼 대체할 수 없는 wrapper만 고정 경로 및 고정 인자로 cmd /d /s /c 실행을 허용한다. 명령이나 prompt의 동적 shell 조합은 만들지 않는다.

node와 npm 설치 위치, version manager와 Corepack 및 내부 scripts shell을 구분해야 한다. npx와 wrapper의 누락 도구 자동 다운로드는 check에서 허용하지 않으며 prepare에서 준비한다. 다른 설치 조합의 resolver와 실제 quoting은 미확인이다. [npm run](https://docs.npmjs.com/cli/v11/commands/npm-run/), [npm exec](https://docs.npmjs.com/cli/v11/commands/npm-exec/).

M0 확인 결과 cmd wrapper를 argv로 실행하는 방식이 이 결정대로 동작하지 않는 경우가 있어 [D15](#d15-cmd-wrapper-허용-조건)에서 허용 조건을 정했다.

### D09 미커밋 변경

warn-head다. 원본 변경을 경고하고 시작 시 고정한 HEAD commit OID에서 실행한다. staged와 unstaged 및 untracked 소스를 run에 넣지 않으며 자동 commit과 stash 또는 reset으로 정리하지 않는다.

작업 소스와 실행 설정은 구분한다. setup의 현재 설정은 별도로 확인한 control 입력이며 소스에 포함하지 않는 구현안을 적용한다. HEAD의 설정과 다르면 차이와 실제 hash를 표시한다. 모델은 run source만 읽고 workspace 설정을 다시 읽어 명령을 바꾸지 않는다.

### D10 검사 명령과 시험 실행

저장소 종류별 후보를 기본으로 한다. 직접 입력한 명령은 doctor에서 한 번 시험해 시간 안에 끝나는지와 파일을 바꾸지 않는지 확인한다. 등록한 check는 검사 단계의 네트워크 차단을 따른다.

첫 시험 자체의 부작용을 원본에 남기지 않기 위해 별도 probe worktree에서 prepare 뒤 시험하는 구현안을 제안한다. 유한 종료 및 무변경 관측은 테스트 성공이나 미래 안전 보장과 다르다. 실행 파일과 script, argv와 cwd, runtime과 설정 및 lock이 바뀌면 관련 기록을 다시 확인한다.

### D11 hooks와 서명

저장소 Git hooks를 평소처럼 실행한다. hooksPath를 바꾸거나 no-verify로 건너뛰지 않는다. 사람 개입이 필요한 서명은 commit 전에 중단하고 알린다. 서명을 해제하거나 unsigned로 전환하지 않는다.

hook이 파일이나 stage를 고치면 검토한 상태와 달라질 수 있다. 이미 commit이 생겼으면 그 사실과 SHA를 보존하고 publish를 막는다. 자동 reset과 amend는 하지 않는다. 임의 signing program과 agent의 사람 개입을 완전히 사전 판별할 수 있는지는 미확인이다. [Git hooks](https://git-scm.com/docs/githooks), [Git signing](https://git-scm.com/docs/git-config#Documentation/git-config.txt-gpgprogram).

### 모델별 최소 CLI 버전 확인

원문 :28에 따른 기술 확인 규칙이다. doctor는 선택 runtime에서 최소 CLI 버전을 비교한다. 미달 agent는 probe 실패이며 모델 호출을 하지 않는다. 설치 Claude 2.1.316은 Fable 5.2의 최소 2.1.321보다 낮다. 버전 미달을 경고만 하고 통과시키지 않으며 모델을 바꾸거나 CLI를 자동 업데이트하지 않는다.

이 규칙의 "미달이면 probe 실패, 모델 호출 안 함"은 [D14](#d14-fable과-최소-cli-버전-경고)로 바뀌었다. 모델을 바꾸거나 CLI를 자동 업데이트하지 않는다는 부분은 유지한다.

### D12 기존 lock 유지

prepare는 기존 lock을 유지한다. lock이 없거나 manifest와 맞지 않으면 중단한다. doctor는 lock이 없는 저장소를 미리 알리고 사용자가 run 밖에서 uv lock, npm install 등으로 한 번 lock을 만들도록 안내한다. run 안에서는 lock이 바뀌지 않으며 변경을 탐지하면 중단한다.

M0 확인 결과 등록 명령에 따라 불일치를 탐지하지 못하는 경우가 있어 [D16](#d16-lock-일치-사전-확인)에서 탐지 방법을 정했다.

### D13 새 의존성과 구현 중 변경

MVP는 구현 중 의존성이 바뀌어도 자동으로 다시 준비하지 않고 중단한다. 기획자 결과에 새 의존성 필요 여부를 적고 필요하면 승인 화면에서 사람에게 보인다. 사람은 의존성을 먼저 추가한 뒤 다시 시작한다. 코더가 계획에 없던 manifest나 lock을 바꾸면 중단한다. 계획이 허용하더라도 run 안 lock 변경은 D12에 따라 중단한다.

### D14 Fable과 최소 CLI 버전 경고

최소 CLI 버전보다 낮은 runtime에서도 모델을 막지 않는다. doctor는 미달을 경고로 표시하고, 해당 agent의 실제 probe 호출 결과로 사용 가능 여부를 판정한다. 모델을 바꾸거나 CLI를 자동 업데이트하지 않는다.

근거 확인(2026-11-17):

- [Claude 모델 설정](https://code.claude.com/docs/en/model-config) 문서는 Fable 5.1(v2.1.257), Opus 5.5(v2.1.280), Sonnet 5.5(v2.1.284), Haiku 5.5(v2.1.293)의 최소 버전만 적고 있다. Fable 5.2와 2.1.321은 나오지 않는다. 같은 문서는 이전 버전에서 요청이 실패하면 `claude update`로 올리라고 안내한다.
- Claude Code 2.1.321의 변경 기록은 `claude-fable-5-2`를 추가하고 기본 Fable 모델로 바꿨다고 적는다([2.1.321 정리](https://dev.classmethod.jp/en/articles/20261110-cc-updates-v2-1-321/)). 2.1.321은 CLI가 이 모델 ID를 인식하는 첫 버전이다. 실행에 꼭 필요한 버전이라는 공식 근거는 찾지 못했다.
- M0에서 2.1.316의 `claude-fable-5-2` 호출은 성공했고 stderr에 `[claude-code:unrecognized_model]`이 남았다([claude-headless C1](probes/claude-headless.md#c1-전체-모델-id-4개-지정)). 모델 설정 문서에 따르면 Claude Code는 인식하지 못한 모델 ID의 context window를 200K로 가정하고, effort 같은 기능은 모델 ID 패턴으로 켠다.

경고에 표시할 내용: 설치 버전과 최소 버전, CLI가 모델을 인식하지 못해 context window를 200K로 가정하고 일부 기능(effort 등)이 기대대로 적용되지 않을 수 있다는 점, `claude update` 안내. registry의 `min_cli_version`은 "CLI가 이 모델을 인식하는 첫 버전"으로 기록한다. Fable 5.2의 2.1.321도 이 뜻이다.

### D15 cmd wrapper 허용 조건

gradlew.bat, mvn.cmd, mvnw.cmd 같은 대체할 수 없는 wrapper는 다음 조건을 모두 만족할 때만 `cmd.exe /d /s /c`로 실행한다. 나머지는 setup과 doctor가 거부하고 이유를 표시한다.

- wrapper 경로에 공백이 없다.
- 등록 인자에 `%`, `^`, `&`, `|`, `"`, `<`, `>`, `!`, 줄바꿈이 없다.
- 실행은 argv 배열 `["cmd.exe","/d","/s","/c",<wrapper>,<인자>...]`로 한다. 명령 줄 문자열을 직접 만들지 않는다.

근거: M0에서 공백 있는 wrapper 경로를 argv로 넘기면 wrapper가 실행되지 않았고 `&` 인자가 명령으로 실행됐다. 공백 없는 경로에서는 인자 12개 중 10개가 그대로 전달됐고, 나머지 2개는 `%PATHEXT%` 확장과 `^` 제거였다([windows-process W3](probes/windows-process.md#w3-cmd-d-s-c-wrapper-인자-처리)). 한글이 들어간 공백 없는 경로와 `(`, `)`처럼 이번에 그대로 전달된 문자의 다른 조합은 doctor 시험에서 다시 확인한다.

### D16 lock 일치 사전 확인

prepare의 등록 명령을 실행하기 전에, 오케스트레이터가 lock 종류별 확인 명령을 따로 실행해 lock 부재와 manifest 불일치를 탐지한다. 등록 명령은 바꾸지 않고, 옵션을 덧붙이지 않는다. 확인 명령이 실패하면 prepare를 시작하지 않고 중단한다. doctor도 같은 확인을 해서 lock 부재와 불일치를 미리 알린다.

- uv(`uv.lock`): `uv lock --check`. M0 재확인(uv 0.11.32)에서 lock 없음 exit 2, 일치 exit 0, 불일치 exit 1이었고 lock 파일과 `.venv`를 만들거나 바꾸지 않았다. 의존성을 다시 해석하므로 네트워크나 cache가 필요할 수 있어 prepare 단계(네트워크 허용)에서 실행한다.
- npm(`package-lock.json`): 확인 명령은 정하지 않았다. 등록 명령이 `npm ci`이면 부재와 불일치에서 스스로 실패한다(M0 확인). 다른 등록 명령은 기존대로 lock 전후 비교로 탐지한다.
- lock 전후 비교는 그대로 유지한다. 사전 확인은 등록 명령이 불일치를 숨기는 경우(`uv sync --frozen` 등)를 잡기 위한 추가 단계다.

근거: [prepare-behavior](probes/prepare-behavior.md#lock-부재와-불일치-때의-동작). `uv sync --frozen`은 불일치에서도 lock을 바꾸지 않고 성공해 전후 비교로 탐지되지 않았다.

## 남은 결정

기준일: 2026-11-17.

### D17 검사 단계 네트워크 차단 방식

D05와 02-config-spec은 check와 check-probe의 프로젝트 명령 네트워크를 blocked로 정했지만, 무엇으로 막는지는 정하지 않았다. #30에서 Windows 일반 사용자 권한으로 후보를 확인했다([check-network-block](probes/check-network-block.md)).

| 선택지 | 내용 | 확인된 점 | 남는 문제 |
|---|---|---|---|
| A 협조형 | 프록시 환경 변수를 닫힌 로컬 포트로 지정하고 `NODE_USE_ENV_PROXY=1`과 npm, pip, uv offline 설정을 함께 적용 | 관리자 불필요. Python urllib, Node `fetch`와 `https`, curl, pip, npm, uv, Git이 모두 막힘 | 직접 소켓과 설정을 무시하는 프로그램은 못 막음. 차단을 보장이 아닌 방어 수단으로 표시해야 함 |
| B AppContainer | 검사 명령을 capability 없는 AppContainer에서 실행하고 workspace, toolchain, 의존성 환경, cache 폴더에 SID 권한을 부여 | 관리자 불필요. 손자 프로세스까지 OS가 차단 | 사용자 설치 Python이 권한 없이 시작되지 않음. 실제 검사가 통과하는 권한 범위와 ACL 부여의 되돌리기, Node와 uv 동작은 미확인 |
| C A와 B 단계적 적용 | MVP는 A로 시작하고 B는 doctor에서 실행 가능할 때 켜는 선택 사항으로 둠 | A의 결과와 같음 | B의 미확인 사항은 그대로 남음 |

Windows Firewall 규칙은 관리자 권한이 필요해 D02의 일반 사용자 실행 전제와 맞지 않으므로 선택지에서 뺐다. 어느 선택지든 프록시와 offline 설정은 결과 기록에 적용 방식으로 남기고 차단 성공을 보장으로 표시하지 않는다.

## 진행 방식

기획과 결정 기록을 ai-collaboration 레포의 docs/로 옮겼고 이슈는 06-issue-plan.md의 계획 순서와 범위를 따른다. M0 확인 실험(#3부터 #7까지)을 마쳤고 결과는 [docs/probes/](probes/README.md)에 있다. 결정과 충돌한 결과는 D14부터 D16까지로 정했다. M1 구현은 이 결정을 따른다. 검사 단계 네트워크 차단 확인(#30)에서 생긴 D17은 #15 구현 전에 정한다.
