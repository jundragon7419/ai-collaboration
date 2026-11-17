# 설정 명세

기준일: 2026-11-17. config v2 개정안, 구현 전. [결정 원문](decisions.md#결정-기록) :19-28을 반영했다.

## 결정값과 설계 제안

설정은 .aicollab/config.toml의 UTF-8 TOML이다. v2는 미구현 명세의 식별자이며 이전 예시의 project.dirty_policy는 project.uncommitted_changes로 바꾼다. 값과 의미를 추측해 자동 변환하지 않는다.

원문에 있는 trusted-local, warn-head, 준비 및 검사 네트워크 정책, hooks와 서명 및 무변경 처리, 역할 수는 결정값이다. 그 밖의 root와 state 경로, timeout과 회차 상한, cache 및 scratch 위치는 설계 제안이다. 표의 “제안”은 사용자 결정이 아니고 예시도 권장 구현안을 보여 준다. 준비 명령과 인자에는 등록한 값을 그대로 사용하며 --locked 같은 옵션을 몰래 더하지 않는다.

setup 순서는 flow → 역할별 회사와 모델 → Claude 사용 시 환경 → 검사 → 의존성 준비 명령 → 차단 등급 → 공개 방식이다. 기획자와 코더는 각각 한 명이며 reviewer에만 추가 배정을 허용한다. 동일 provider, 전체 모델 ID와 effort 및 perspective 설정이면 같은 agent로 묶되 역할마다 새 세션과 권한을 사용한다. 사용할 AI를 따로 묻지 않는다.

정적 검증, doctor와 run 검증을 구분한다. unknown 키, 잘못된 타입, 중복 ID와 참조 오류를 거부한다. ID는 [a-z][a-z0-9_-]*를 사용하며 run_id는 시스템 생성 UUID다. 사용자 확인한 control 설정을 workspace 밖에 고정하고 hash를 기록한다. 미커밋 실행 설정을 사용하면 HEAD와의 차이를 표시하되 run 소스에 섞지 않는다.

정적 검증은 `src/aicollab/config.py`의 `load_config()`와 `parse_config()`가 한다. 어긋난 항목을 모두 모아 `ConfigError`로 알리며, 항목마다 키 경로와 오류 코드를 가진다. 오류 코드는 unreadable, invalid-toml, missing-key, unknown-key, invalid-type, invalid-value, duplicate-id, unknown-reference, invalid-count, invalid-path, conflict다. 최소 CLI 버전 미달은 오류가 아니다. `version_checks()`가 설치 버전, 최소 버전, 상태(ok, below-minimum, minimum-unknown, installed-unknown)를 경고 정보로 돌려준다.

시점이 doctor나 run인 규칙(실행 파일, Git root, WSL 배포판, 절대 경로 확인 등)은 정적 검증에서 하지 않는다. effort는 모델별 허용 값이 정해지기 전이라 문자열인지만 본다. 표에 값이 적히지 않아 구현에서 정한 규칙은 다음과 같다.

- agents가 참조하는 회사마다 providers.<id> table이 있어야 한다.
- prepare.dependency_paths는 키가 필수이고 빈 배열을 허용한다.
- roles.<id>.access는 역할 기본 정책과 같은 값만 허용한다.
- checks.commands[].trial은 source가 custom이면 doctor-once, candidate이면 not-required만 허용한다. doctor가 기록하는 pending, passed, failed는 설정에 쓸 수 없다.
- 값만으로 판정되는 시간 관계를 정적으로 검사한다. pipeline.invocation_timeout_seconds는 run_timeout_seconds 이하이고, checks.commands[].timeout_seconds도 run_timeout_seconds 이하다.
- 경로 키는 저장소 안의 상대 경로만 허용한다. 상위 경로, drive, UNC와 device 경로, Windows 예약 이름, 대소문자만 다른 중복을 거부한다.

## provider registry와 최소 버전

Python의 provider_registry 모듈 한 곳에 회사별 모델과 근거 및 확인일을 둔다. UI와 프리셋 및 validator는 이 목록을 참조한다. 구현은 `src/aicollab/provider_registry.py`이고, `tests/test_provider_registry.py`가 아래 JSON과 표가 같은지 비교한다. 전체 모델 ID만 저장하고 별칭과 placeholder를 거부한다.

```json
{
  "registry_version": 1,
  "providers": [
    {
      "id": "claude", "menu_order": 1, "enabled": true,
      "models": [
        {"id": "claude-opus-5-5", "min_cli_version": "2.1.280"},
        {"id": "claude-fable-5-2", "min_cli_version": "2.1.321"},
        {"id": "claude-sonnet-5-5", "min_cli_version": "2.1.284"},
        {"id": "claude-haiku-5-5", "min_cli_version": "2.1.293"}
      ]
    },
    {
      "id": "codex", "menu_order": 2, "enabled": true,
      "models": [
        {"id": "gpt-6-astra", "min_cli_version": "unknown"},
        {"id": "gpt-6.1-sol", "min_cli_version": "unknown"},
        {"id": "gpt-6.1-terra", "min_cli_version": "unknown"},
        {"id": "gpt-6-luna", "min_cli_version": "unknown"}
      ]
    },
    {"id": "gemini", "menu_order": 3, "enabled": false, "models": []}
  ]
}
```

registry의 enabled는 메뉴 선택 대상이라는 뜻이며 계정 제공과 실행 성공을 뜻하지 않는다.

| 회사 | 전체 모델 ID | 확인된 최소 CLI 버전 | 현재 확인 | M0 실행 확인(2026-11-17, Windows) |
|---|---|---|---|
| Claude | claude-opus-5-5 | 2.1.280 | 설치 2.1.316은 버전 조건만 충족 | 2.1.316에서 실행됨 |
| Claude | claude-fable-5-2 | 2.1.321 | 설치 2.1.316은 미달. D14에 따라 경고 | 2.1.316에서 실행됨. stderr에 `unrecognized_model` 표시. [D14](05-open-decisions.md#d14-fable과-최소-cli-버전-경고) |
| Claude | claude-sonnet-5-5 | 2.1.284 | 설치 2.1.316은 버전 조건만 충족 | 2.1.316에서 실행됨 |
| Claude | claude-haiku-5-5 | 2.1.293 | 설치 2.1.316은 버전 조건만 충족 | 2.1.316에서 실행됨. `--json-schema`, `--effort` 시험 모델 |
| Codex | gpt-6-astra | 미확인 | binary catalog에 존재 | 0.167.0-alpha.3.2에서 실행됨. `--output-schema`, sandbox, effort 시험 모델 |
| Codex | gpt-6.1-sol | 미확인 | binary catalog에 존재 | 0.167.0-alpha.3.2에서 실행됨 |
| Codex | gpt-6.1-terra | 미확인 | binary catalog에 존재 | 0.167.0-alpha.3.2에서 실행됨 |
| Codex | gpt-6-luna | 미확인 | binary catalog에 존재 | 0.167.0-alpha.3.2에서 실행됨 |

근거: [Claude 목록](https://platform.claude.com/docs/en/models/overview), [Claude 모델 설정](https://code.claude.com/docs/en/model-config), [Codex Models](https://learn.chatgpt.com/docs/models), 이전에 실행한 codex debug models --bundled. 2026-11-17에도 claude --version에서 2.1.316을 확인했다. M0 실행 확인 열은 [claude-headless](probes/claude-headless.md)와 [codex-exec](probes/codex-exec.md) 결과다. 이 계정에서 8개 모델 모두 실행됐다. Schema 수락은 표에 적은 시험 모델에서만 확인했다. Codex 실행 파일은 PATH에 없었고 Codex 앱 폴더의 `codex.exe`(0.167.0-alpha.3.2)를 썼다. 기존 기록의 0.169.0-alpha.11.1과 버전이 다르다.

`min_cli_version`은 CLI가 그 모델 ID를 인식하는 첫 버전이다([D14](05-open-decisions.md#d14-fable과-최소-cli-버전-경고)). doctor는 실제 선택 runtime의 CLI 버전을 모델별 최소값과 비교한다. 미달이면 version-warning을 표시하고, 해당 agent의 probe 호출 결과로 사용 가능 여부를 판정한다. 경고에는 설치 버전과 최소 버전, CLI가 모델을 인식하지 못해 context window를 200K로 가정하고 effort 같은 기능이 기대대로 적용되지 않을 수 있다는 점, `claude update` 안내를 표시한다. 전체 ID와 최소 버전을 바꾸거나 자동 업데이트 및 fallback하지 않는다. 최소값 미확인은 버전 성공이 아니며 별도 기능 probe가 필요하다.

## project와 최상위

| 이름 | 타입 | 기본값 또는 결정값 | 허용 값과 검증 규칙 | 시점 |
|---|---|---|---|---|
| schema_version | integer | 필수 | 2 | 정적 |
| project | table | 필수 | 아래 키만 허용 | 정적 |
| project.root | string | .., 제안 | 설정 디렉터리 기준 실제 Git root와 일치 | 정적, run |
| project.run_root | string | runtime 사용자 state 아래 aicollab/runs, 제안 | 원본 checkout과 공유 Git 관리 경로 밖 절대 경로 | doctor, run |
| project.runtime | string | Claude 없으면 windows-native, 있으면 선택 | windows-native, wsl2. 실제 flow가 Codex-only이면 wsl2 오류 | 정적, doctor |
| project.wsl_distribution | string | native에서는 생략 | WSL2에서 설치 배포판 이름 필수. 모든 provider와 prepare 및 check가 같은 runtime 사용 | doctor |
| project.threat_model | string | trusted-local, 결정 | MVP에서 trusted-local만 허용. untrusted와 미선택 상태를 지원값으로 표시하지 않음 | 정적, run |
| project.uncommitted_changes | string | warn-head, 결정 | 원본 변경을 경고하고 고정 HEAD에서 시작. 원본 소스 변경은 포함하지 않음 | run |
| providers, agents, roles | table 각각 | 필수 | 등록 참조와 역할 cardinality 검사 | 정적 |
| pipeline, prepare, checks, git, output | table 각각 | 필수 | 아래 키와 규칙 적용 | 정적 |

원본 HEAD는 실행 시작에 commit OID로 고정한다. planner와 검사 및 reviewer의 source를 원본 checkout에서 다시 읽지 않는다. 미커밋 .aicollab 설정은 별도로 확인한 control 입력일 수 있으며 source와 commit 대상이 아니다. workspace에서 바뀐 설정을 재로딩하지 않는다.

source와 test_paths의 경로 탈출, UNC와 device 경로, drive-relative 경로 및 대소문자 충돌을 거부하는 구현안을 제안한다. 의존성의 생성된 링크와 toolchain 링크는 대상과 runtime을 기록하고 무조건 재귀 순회하지 않는다. 기존 환경을 공유하는 링크 전략을 D05의 미결정 선택지로 남기지 않는다. 실행 파일은 버전 관리자의 shim과 실제 target을 구분해 기록한다.

## provider와 agent

| 이름 | 타입 | 기본값 | 허용 값과 검증 규칙 | 시점 |
|---|---|---|---|---|
| providers.<id>.executable | string | native의 claude.exe/codex.exe, WSL2의 claude/codex, 제안 | 공식 CLI 경로와 버전 고정, shell 문자열 금지 | doctor |
| providers.<id>.auth_expectation | string | subscription, 기존 MVP 제안 | 본인 기존 로그인 사용. 토큰 추출과 로그인 방식 자동 전환 없음 | doctor |
| agents.<id>.provider | string | 필수 | 활성 registry의 등록 회사 | 정적 |
| agents.<id>.model | string | 필수 | 등록 전체 ID와 일치. Gemini는 선택 불가 | 정적, doctor |
| agents.<id>.effort | string | 생략, 모델 기본값 사용 제안 | provider와 모델의 지원을 확인. 실효값 미확인은 unknown | doctor |
| agents.<id>.perspective | string | general, 제안 | general, adversarial, spec, security | 정적 |

모델과 effort 변환은 Claude의 --model 및 --effort, Codex의 --model 및 -c model_reasoning_effort를 사용한다. 같은 agent를 여러 role에 배정해도 권한은 합치지 않는다.

## 역할과 pipeline

| 이름 | 타입 | 기본값 | 허용 값과 검증 규칙 | 시점 |
|---|---|---|---|---|
| roles.<id>.agents | array of string | 필수 | planner와 coder 각각 1개, tester 활성 시 1개. reviewer는 1개 이상. 같은 배열의 중복 거부 | 정적 |
| roles.<id>.access | string | 기본 역할별 정책, 설계 제안 | planner/reviewer read-only, coder workspace-write, tester path-write. 실제 강제와 사후 감사를 구분 | doctor, run |
| roles.tester.test_paths | array of string | ["tests/"], 결정 | 상대 디렉터리 하나 이상. tester flow의 coder 쓰기 범위에서 제외 | 정적, run |
| pipeline.flow | string | setup 첫 선택 필수 | plan-code-review, plan-code-test-review | 정적 |
| pipeline.max_revision_rounds | integer | 2, 제안 | 0 이상. 모든 쓰기 role이 공유 | run |
| pipeline.invocation_timeout_seconds | integer | 600, 제안 | 1 이상. AI 호출 상한 | run |
| pipeline.run_timeout_seconds | integer | 3600, 제안 | invocation 상한 이상, 사람 대기 제외한 누적 실행 시간 | run |
| pipeline.block_up_to | string | P2, 사용자 권장값 | P0부터 P5까지. 선택 등급까지 차단 | 정적, run |

workspace → prepare → planner → approve → coder → [tester] → check 또는 검사 미실행 → reviewer 순서다. tester 입력은 plan과 diff뿐이다. 검사 실패도 reviewer가 판정한다. gate 성공 뒤 변경 있는 경우에만 commit과 publish로 간다.

## prepare

| 이름 | 타입 | 기본값 또는 결정값 | 허용 값과 검증 규칙 | 시점 |
|---|---|---|---|---|
| prepare.network | string | allowed, 결정 | 의존성 준비용 프로젝트 명령과 자식 프로세스의 네트워크 허용 | prepare |
| prepare.commands | array of tables | [], 제안 | 등록 순서로 실행. 빈 배열은 준비 명령 없음으로 표시하고 필요한 의존성 누락을 성공으로 보지 않음 | 정적, prepare |
| prepare.dependency_paths | array of string | 저장소별 등록 필수 | .venv와 node_modules 등 생성 경로. source와 control 경로를 덮는 root 금지 | prepare 감사 |
| prepare.manifest_paths | array of string | 탐지 후 사용자 확인, 제안 | dependency manifest와 lock의 source 상대 파일 목록 | doctor, prepare, run |
| prepare.on_lock_change | string | stop, 결정 | stop만 허용. 기존 lock 유지, 부재와 불일치 및 run 안 변경 시 중단 | 예외 발생 시 |
| prepare.on_dependency_change | string | stop, 결정 | stop만 허용. 자동 재준비 없음, 사람이 의존성 추가 후 재시작 | 구현 중 변경 시 |
| prepare.commands[].id | string | 필수 | 준비 명령 고유 ID | 정적 |
| prepare.commands[].argv | array of string | 필수 | 등록한 명령과 인자 그대로. 자동 옵션 추가와 다른 명령 대체 금지 | prepare |
| prepare.commands[].cwd | string | ., 제안 | workspace 안의 상대 디렉터리 | 정적 |
| prepare.commands[].launcher | string | direct, 제안 | direct, node-npm, node-npx, cmd-wrapper. 아래 Windows 규칙 적용 | doctor |
| prepare.commands[].timeout_seconds | integer | 900, 제안 | 1 이상. 자식 트리 종료까지 처리 | prepare |
| prepare.commands[].success_exit_codes | array of integer | [0], 제안 | 제안 명세에서는 [0]만 허용 | prepare |

workspace를 만든 직후 prepare를 실행하고 성공해야 planner로 간다. lifecycle script도 등록 명령의 실제 동작에 포함한다. 버전과 cwd 및 config hash, source와 lock 전후 상태, 의존성 산출물과 종료 상태를 기록한다. 설치 인증은 패키지 관리자의 기존 경로를 사용하며 오케스트레이터가 토큰을 추출해 AI와 check에 전달하지 않는다.

lock 일치 확인은 설정 항목이 아니라 오케스트레이터 내장 단계다. [D16](05-open-decisions.md#d16-lock-일치-사전-확인)에 따라 등록 명령 전에 lock 종류별 확인 명령(uv는 `uv lock --check`)을 실행하고, 실패하면 prepare를 시작하지 않는다. npm 확인 명령은 정하지 않았다. uv sync는 lock을 만들거나 갱신할 수 있고 npm ci는 기존 lock이 필요하다. source와 lock 변경을 성공 baseline으로 숨기지 않는다. D12에 따라 기존 lock을 유지하고 부재와 불일치 및 run 안 변경이면 중단한다. doctor가 부재를 미리 알리고 run 밖 lock 생성 명령을 안내한다. 선택된 등록 명령에 몰래 --locked를 추가하거나 npm install로 대체하지 않는다. [uv sync](https://docs.astral.sh/uv/concepts/projects/sync/), [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/).

첫 준비 실패와 timeout 또는 취소에서 멈추고 부분 환경을 보존한다. 실패 환경을 준비 완료로 재사용하거나 자동 삭제 및 재시도하지 않는다. 재개는 source와 lock, 명령 및 환경을 다시 확인한다. 설치 stdout과 stderr는 모델 입력에 자동 첨부하지 않는다.

M0 확인 결과([prepare-behavior](probes/prepare-behavior.md), Linux, uv 0.11.32, npm 10.9.9):

- lock이 맞으면 `uv sync`와 `npm ci`는 source와 lock을 바꾸지 않고 의존성 산출물만 만든다.
- `uv sync`는 lock 부재에서 lock을 만들고 불일치에서 lock을 고친 뒤 exit 0이다. `uv sync --frozen`은 불일치를 알리지 않고 성공해 전후 비교로도 탐지되지 않는다. [D16](05-open-decisions.md#d16-lock-일치-사전-확인)에 따라 등록 명령 전에 `uv lock --check`로 부재(exit 2)와 불일치(exit 1)를 먼저 확인하고, 전후 비교도 유지한다.
- `uv sync --locked`는 실패해도 `.venv`를 먼저 만든다. `npm ci`는 실행할 때마다 기존 `node_modules`를 지우고, 루트 `postinstall`이 실패해도 설치한 의존성을 남긴다. 의존성 폴더 존재는 준비 완료의 근거가 아니다.
- `npm ci`는 루트 `preinstall`, `postinstall`, `prepare` script를 실행하고 script가 source를 바꿀 수 있다.
- 상속 환경 변수가 대상을 바꿀 수 있다. `UV_PROJECT_ENVIRONMENT`가 절대 경로면 `uv sync`가 worktree 밖 환경을 고치고 선언되지 않은 패키지를 지운다. `npm_config_global`, `npm_config_prefix` 등도 설치 위치를 바꾼다. prepare 실행 환경에서 이런 변수를 어떻게 다룰지는 문서에 없다.
- Windows 실행과 lifecycle script의 `cmd.exe` 실행은 미확인이다.

## checks와 직접 입력 시험

| 이름 | 타입 | 기본값 또는 결정값 | 허용 값과 검증 규칙 | 시점 |
|---|---|---|---|---|
| checks.enabled | boolean | true, 결정 | tester flow에서 false 오류 | 정적 |
| checks.network | string | blocked, 결정 | 검사와 check-probe의 프로젝트 명령 및 자식에게 적용. 준비 허용을 상속하지 않음 | check, probe |
| checks.commands | array of tables | [], 제안 | enabled=true이면 하나 이상 | 정적 |
| checks.commands[].id | string | 필수 | 검사 고유 ID. plan은 ID만 참조 | 정적 |
| checks.commands[].source | string | 필수 | candidate, custom. candidate라고 적어도 실제 후보와의 일치 재검사 | doctor |
| checks.commands[].trial | string | custom은 doctor-once, 결정 반영 | custom은 doctor-once 고정. candidate의 not-required는 제안이며 정상 실행 준비 확인은 여전히 필요 | doctor |
| checks.commands[].argv | array of string | 필수 | 실행 파일과 인자 배열. shell 문자열 조합 금지 | doctor, check |
| checks.commands[].launcher | string | direct, 제안 | direct, node-npm, node-npx, cmd-wrapper | doctor |
| checks.commands[].cwd | string | ., 제안 | workspace 상대 디렉터리 | 정적 |
| checks.commands[].timeout_seconds | integer | 300, 제안 | 1 이상. run 상한 이하 | probe, check |
| checks.commands[].success_exit_codes | array of integer | [0], 제안 | 제안 명세에서는 [0]만 허용 | check |
| checks.commands[].scratch_paths | array of string | [], 제안 | 새 검사 산출물 전용. source와 test, lock 및 control 경로와 겹침 금지 | probe, check |

후보는 Python, JavaScript와 TypeScript, C와 C++, Java, Go, Rust 종류별로 제시한다. 기존 후보의 pytest, node --test, ctest, JUnit, go test, cargo test --offline --locked를 실제 toolchain과 준비 상태로 확인한다. watch, 자동 수정, 설치와 네트워크가 필요한 검사는 거부한다. 준비할 build와 compiler cache도 check에서 자동 다운로드하지 않는다.

custom은 고정 HEAD의 별도 doctor probe worktree에서 등록 prepare 성공 후 1회 실행한다. 원본과 진행 중 run을 시험 대상으로 쓰지 않는다. 시간 안에 종료되고 source와 test, lock 및 기존 파일을 바꾸지 않았는지 확인한다. 별도 등록한 scratch의 새 로그와 산출물은 source 변경과 구분한다. 의존성 디렉터리의 자동 설치는 scratch로 위장해 허용하지 않는다.

명령이 실제 테스트를 수행하고 실패한 관측과 실행 파일 누락으로 시작하지 못한 경우를 구분한다. 전자는 실행 동작 관측과 baseline 테스트 실패를 따로 기록할 수 있고 후자는 자격 확인 성공이 아니다. 실행 파일과 JS 진입점 및 버전, argv와 cwd, 설정과 script 및 lock, runtime에 시험 결과를 묶는다. 바뀌면 재시험한다. 한 번의 관측은 미래 종료와 무부작용의 보장이 아니므로 매 check의 timeout과 사후 감사는 유지한다.

checks.enabled=false는 기본 flow에서 not-run-disabled로 기록한다. 검사 성공으로 계산하지 않고 결과와 push 확인 및 PR에 “검사 미실행”을 표시한다. tester flow에서는 거부한다.

## CLI adapter의 옵션 변환

아래는 공식 옵션의 기능 대응이며 조합의 실제 성공은 별도 probe 대상이다. 역할 정책과 도구 목록의 세부 기본 구성은 구현 제안이다. Git hooks를 평소 실행하는 결정과 AI CLI의 hooks 및 MCP 설정은 구분한다.

| 기능 | Claude Code | Codex CLI |
|---|---|---|
| 비대화형과 모델 | -p와 stdin, --model 전체 ID | exec -와 --model 전체 ID |
| effort | --effort | -c의 model_reasoning_effort 값 |
| 구조화 결과 | --output-format json과 --json-schema, structured_output 추출 | --output-schema와 새 -o 파일. --json은 별도 JSONL 이벤트 |
| 새 세션 | continue와 resume 금지, --no-session-persistence 지원 확인 | resume와 fork 금지, --ephemeral |
| 읽기 전용 역할 | --tools로 필요한 파일 조회 도구만 노출하는 제안. allowedTools는 자동 승인과 구분 | --sandbox read-only와 상위 -a never 사용 제안 |
| coder와 tester | 역할별 파일 도구 제한과 사후 manifest 검사 | --sandbox workspace-write와 사후 범위 검사. tester 경로 사전 차단으로 표시하지 않음 |
| 자동 설정과 확장 | restricted와 safe-mode 및 MCP 정책의 유효 범위를 버전별 확인. managed 설정이 남을 수 있음 | 사용자와 managed 제한을 약화하지 않는 유효 profile 확인. ignore-rules를 기본 사용하지 않음 |

Claude --bare는 구독 OAuth를 읽지 않는 옵션이므로 구독 실행의 일괄 해결책으로 쓰지 않는다. tool 제한과 sandbox는 악의적 저장소 방어를 보장하는 동일 경계가 아니다. [Claude CLI](https://code.claude.com/docs/en/cli-reference), [Codex 비대화형 실행](https://learn.chatgpt.com/docs/non-interactive-mode).

### M0에서 확인한 출력과 판정 근거

Windows에서 Claude Code 2.1.316과 Codex CLI 0.167.0-alpha.3.2로 확인했다. 자세한 내용은 [claude-headless](probes/claude-headless.md)와 [codex-exec](probes/codex-exec.md)에 있다. adapter 설계에 영향을 주는 사실만 적는다.

| 항목 | Claude Code | Codex CLI |
|---|---|---|
| 성공과 실패 | exit code와 `is_error`, `terminal_reason`. 오류에서도 `subtype`은 `success` | exit code와 마지막 이벤트(`turn.completed` 또는 `turn.failed`) |
| 구조화 결과 위치 | `structured_output`. `result`에는 같은 내용이 문자열로 들어감 | `-o` 파일. 실패한 turn은 파일을 만들지 않음 |
| 공통 Schema | role-result Schema 수락(haiku) | role-result Schema 수락(`gpt-6-astra`). required에 없는 property가 있으면 `invalid_json_schema`(400)로 거부 |
| 모델 오류 | exit 1, `api_error_status` 404. stderr `unrecognized_model` 표시는 실행되는 모델에도 나옴 | exit 1, `turn.failed`의 메시지 |
| 인증 오류 | exit 1, `api_error_status` null, `result` 문장으로만 구분 | 재시도 뒤 exit 1, `turn.failed`의 401 메시지. 구조화된 오류 코드 없음 |
| effort | `low`, `medium`, `high`, `xhigh`, `max`. 알 수 없는 값은 경고 뒤 기본값으로 진행(exit 0) | API가 검사. 모델마다 지원 값이 다름. 지원하지 않는 값은 400으로 실패 |
| 도구와 권한 | `--tools`에 없는 도구는 쓰지 못함. 목록에 있어도 `--allowedTools`가 없으면 `-p`에서 거부되고 `permission_denials`에 기록. 거부돼도 exit 0 | sandbox가 OS 접근 거부로 막음. `-a never`에서 승인 대기 없음. 실패한 명령은 `command_execution.exit_code`로 기록되고 turn은 계속 |
| 새 세션 | `--no-session-persistence` 사용 | `--ephemeral`이면 세션 파일이 늘지 않음 |
| 확장 설정 | 사용자 MCP 도구 노출 가능성 있음(미확인) | 사용자 홈의 `.agents\skills`를 읽음 |

- 모델 응답 문장으로 판정하지 않는다는 원칙에 맞추려면 Claude 인증 오류는 `api_error_status`와 exit code를 우선 쓴다. 인증 없음을 가리키는 구조화 필드는 두 CLI 모두 없었다.
- Claude는 알 수 없는 effort를 거부하지 않으므로 effort 값 검증은 오케스트레이터가 모델별로 한다.
- Codex read-only sandbox에서 명령 작업 폴더가 `-C`와 다르게 잡힌 관찰이 있다. 역할 prompt와 명령은 작업 폴더의 절대 경로를 써야 할 수 있다([04-review U13](04-review.md#미확인-사실과-확인-방법)).
- Codex 명령 출력(`aggregated_output`)의 한글은 대체 문자로 손실될 수 있다. 판정 근거로 쓰지 않는다.
- 한도 오류 형태는 두 CLI 모두 확인하지 못했다.

## Windows 실행과 wrapper

직접 .exe를 우선한다. npm과 npx는 .cmd를 실행하지 않고 doctor가 확인한 node.exe와 npm-cli.js 또는 npx-cli.js를 조합한다. 예를 들어 등록 argv가 npm ci이면 실제 실행은 해당 node와 확인한 npm JS 뒤에 ci를 전달한다. 등록 인자를 임의로 바꾸지 않는다.

doctor는 실제 node, npm JS와 버전을 한 조합으로 고정한다. 인접 node_modules 경로만 추정하지 않고 global prefix와 version manager 및 Corepack shim을 구분한다. shim 선택을 바꾸는 nvm use나 자동 설치는 하지 않는다. 경로와 버전이 바뀌면 관련 기록을 무효화한다. [npm launcher](https://github.com/npm/cli/blob/latest/bin/npm.cmd), [Corepack](https://github.com/nodejs/corepack).

현재 PC에서는 Node v24.14.0과 node로 실행한 npm 및 npx JS의 11.9.0을 확인했다. M0에서 node 옆 `node_modules\npm\bin`의 JS 진입점이 `npm.cmd`, `npx.cmd`와 같은 버전임을 다시 확인했다([windows-process W2](probes/windows-process.md#w2-npm과-npx를-node로-직접-실행할-때-경로-탐색)). 다른 version manager와 Corepack 관리 환경의 resolver 성공은 미확인이다. node로 진입해도 npm package scripts는 Windows에서 cmd.exe를 사용할 수 있다. outer launcher 우회와 전체 shell 제거를 같은 뜻으로 쓰지 않는다. [npm run](https://docs.npmjs.com/cli/v11/commands/npm-run/).

대체할 수 없는 gradlew.bat, mvn.cmd와 mvnw.cmd 같은 확인한 wrapper만 고정 경로와 고정 인자로 cmd.exe /d /s /c 실행을 허용한다. prompt와 handoff 문자열을 command에 합치지 않는다. /d와 /s가 자동으로 안전한 quoting을 제공한다고 주장하지 않는다. 공백과 한글, 따옴표와 shell 특수문자 처리는 doctor 시험 대상이다. [Microsoft cmd](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd), [Python subprocess](https://docs.python.org/3/library/subprocess.html#security-considerations).

M0에서 argv `["cmd.exe","/d","/s","/c",<wrapper>,<인자>]`를 Python `subprocess`에 넘기면 wrapper 경로에 공백이 있을 때 wrapper가 실행되지 않았고 `&` 인자가 명령으로 실행됐다. 바깥 따옴표를 한 겹 더 씌운 명령 줄이나 공백 없는 경로에서는 실행됐지만, 모든 방식에서 `%VAR%`가 확장되고 `^`가 사라졌다([windows-process W3](probes/windows-process.md#w3-cmd-d-s-c-wrapper-인자-처리)). [D15](05-open-decisions.md#d15-cmd-wrapper-허용-조건)에 따라 wrapper 경로에 공백이 없고 인자에 `%`, `^`, `&`, `|`, `"`, `<`, `>`, `!`, 줄바꿈이 없을 때만 argv 배열로 `cmd.exe /d /s /c`를 실행하고, 나머지는 setup과 doctor가 거부한다.

프로세스 트리 종료는 Python `Popen.kill()`과 `subprocess.run(timeout=)`만으로는 손자 프로세스가 남았다. `taskkill /T /F`, Job Object, 프로세스 그룹과 `CTRL_BREAK_EVENT`는 손자까지 끝냈다([windows-process W1](probes/windows-process.md#w1-시간-상한-뒤-자식-프로세스까지-종료)). 자식 프로세스의 출력 인코딩은 도구마다 달랐다(Python 자식 cp949, node와 git UTF-8). git 경로 목록은 `-z`로 받아야 한글이 escape되지 않는다([windows-process W4](probes/windows-process.md#w4-출력-인코딩)).

npx의 로컬 대상과 Gradle 및 Maven 배포본, compiler와 plugin은 prepare에서 준비해야 한다. check에서 누락되면 실패하고 자동 설치하지 않는다. npx의 offline과 no 옵션은 방어 수단 제안일 뿐 cache 설치까지 모두 막는 보장으로 쓰지 않는다. 등록 인자와 local dependency 확인, 네트워크 차단 및 사후 감사를 함께 검사한다. [npm exec](https://docs.npmjs.com/cli/v11/commands/npm-exec/), [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html), [Maven Wrapper](https://maven.apache.org/tools/wrapper/).

## git과 output

| 이름 | 타입 | 기본값 또는 결정값 | 허용 값과 검증 규칙 | 시점 |
|---|---|---|---|---|
| git.hooks | string | run, 결정 | 평소 hooks 실행. hooksPath override와 no-verify로 우회하지 않음 | workspace, commit, push |
| git.interactive_signing | string | stop-before-commit, 결정 | 사람 개입이 필요하거나 무인 준비를 확인할 수 없으면 commit 전 중단. 서명을 끄지 않음 | commit 전 |
| git.on_no_change | string | finish-without-commit, 결정 | 성공하고 Git 결과 tree가 같으면 “변경 없음”. commit과 push 및 PR 생략 | gate 후 |
| output.mode | string | branch, 결정 | branch만. patch 거부 | 정적 |
| output.publish | string | push, 결정 | push, draft-pr. 둘 다 사람 확인 뒤 실행 | publish |
| output.remote | string | origin, 제안 | 실제 remote와 대상 저장소 확인 | publish |
| output.base_branch | string | 확인한 원격 기본 branch 제시, 제안 | Draft PR에서 값 고정, 모호하면 사용자 확인 | publish |
| output.github_repo | string | 확인한 OWNER/REPO 제시, 제안 | gh의 암묵적 repo 선택에 맡기지 않음 | publish |

commit이 필요한 경우에만 사용자 identity를 확인한다. 평소 hooks가 reviewed tree와 source를 바꾸면 기존 gate는 무효다. commit이 이미 생겼으면 committed-unverified와 SHA를 기록하고 publish를 막는다. reset과 amend로 없던 일로 만들지 않는다. 서명 프로그램과 agent 상태만으로 모든 사람 개입을 사전 예측할 수 있다는 보장은 하지 않는다.

무변경 성공은 publish 명령을 실행하지 않는다. 변경 있는 경우 승인에 remote와 공개 범위, branch와 SHA, identity 및 실제 검사 상태를 묶는다. PR에는 base와 제목 및 본문도 포함한다. 토큰 추출과 자동 로그인, merge는 하지 않는다. PR 미리보기는 로컬에서만 만들고 gh pr create --dry-run으로 대신하지 않는다.

## 예시 전체 설정

다음은 Python 저장소의 mixed tester flow 예시다. 기존 pyproject.toml과 uv.lock, 준비 명령 및 toolchain을 가정한 설계 제안이며 이 문서 폴더에 있다는 뜻은 아니다. 시간과 경로는 제안값이고 등록할 실제 argv는 사용자 확인 대상이다. D12와 D13의 처리 값은 stop이다. Fable을 쓰는 프리셋은 현재 설치에서 version-check가 실패한다.

```toml
schema_version = 2
[project]
root = ".."
runtime = "windows-native"
threat_model = "trusted-local"
uncommitted_changes = "warn-head"

[providers.claude]
executable = "claude.exe"
auth_expectation = "subscription"
[providers.codex]
executable = "codex.exe"
auth_expectation = "subscription"

[agents.plan]
provider = "claude"
model = "claude-opus-5-5"
[agents.code]
provider = "codex"
model = "gpt-6.1-terra"
[agents.test]
provider = "claude"
model = "claude-sonnet-5-5"
[agents.review]
provider = "codex"
model = "gpt-6-astra"
perspective = "adversarial"

[roles.planner]
agents = ["plan"]
[roles.coder]
agents = ["code"]
[roles.tester]
agents = ["test"]
test_paths = ["tests/"]
[roles.reviewer]
agents = ["review"]

[pipeline]
flow = "plan-code-test-review"
max_revision_rounds = 2
invocation_timeout_seconds = 600
run_timeout_seconds = 3600
block_up_to = "P2"

[prepare]
network = "allowed"
dependency_paths = [".venv/"]
manifest_paths = ["pyproject.toml", "uv.lock"]
on_lock_change = "stop"
on_dependency_change = "stop"
[[prepare.commands]]
id = "python-deps"
argv = ["uv.exe", "sync", "--locked"]
launcher = "direct"
cwd = "."
timeout_seconds = 900
success_exit_codes = [0]

[checks]
enabled = true
network = "blocked"
[[checks.commands]]
id = "tests"
source = "candidate"
trial = "not-required"
argv = [".venv/Scripts/python.exe", "-m", "pytest", "-p", "no:cacheprovider", "--basetemp", ".test-tmp"]
launcher = "direct"
cwd = "."
timeout_seconds = 300
success_exit_codes = [0]
scratch_paths = [".test-tmp/"]

[git]
hooks = "run"
interactive_signing = "stop-before-commit"
on_no_change = "finish-without-commit"

[output]
mode = "branch"
publish = "push"
remote = "origin"
```

Python bytecode와 cache의 별도 처리도 실제 실행 환경에 표시하고 기록하는 설계 제안이다. 제안 옵션을 등록 명령에 숨겨 넣지 않는다. WSL2에서는 해당 배포판의 실행 파일과 .venv/bin/python 경로로 설정한다.

## 프리셋 3종

setup의 첫 flow 선택은 프리셋이 덮어쓰지 않는다. 프리셋은 해당 회사 범위의 초기 역할 배정 제안이다. 아래 블록은 전체 예시의 providers, agents와 roles 묶음을 교체한다. 공통 project, 선택한 pipeline.flow, prepare와 checks 및 git과 output은 유지한다. 런타임 설정 병합 기능을 뜻하지 않는다. 모두 tester를 배정하며 기본 flow를 선택하면 tester는 비활성이다.

claude-only:

```toml
[providers.claude]
executable = "claude.exe"
auth_expectation = "subscription"
[agents.plan]
provider = "claude"
model = "claude-opus-5-5"
[agents.code]
provider = "claude"
model = "claude-fable-5-2"
[agents.test]
provider = "claude"
model = "claude-sonnet-5-5"
[agents.review]
provider = "claude"
model = "claude-opus-5-5"
perspective = "adversarial"
[roles.planner]
agents = ["plan"]
[roles.coder]
agents = ["code"]
[roles.tester]
agents = ["test"]
test_paths = ["tests/"]
[roles.reviewer]
agents = ["review"]
```

이 프리셋의 Fable은 현재 설치 CLI 버전에서 지원 요건을 충족하지 못한다. 모델 선택은 유지하고 실행 전에 버전 부족을 해결해야 한다.

codex-only:

```toml
[providers.codex]
executable = "codex.exe"
auth_expectation = "subscription"
[agents.plan]
provider = "codex"
model = "gpt-6.1-sol"
[agents.code]
provider = "codex"
model = "gpt-6.1-terra"
[agents.test]
provider = "codex"
model = "gpt-6-luna"
[agents.review]
provider = "codex"
model = "gpt-6-astra"
perspective = "adversarial"
[roles.planner]
agents = ["plan"]
[roles.coder]
agents = ["code"]
[roles.tester]
agents = ["test"]
test_paths = ["tests/"]
[roles.reviewer]
agents = ["review"]
```

mixed는 위 전체 예시의 배정을 사용한다. 회사가 역할에 고정되는 것은 아니며 다음처럼 Codex를 기획자, Claude를 코더와 테스터로 배정할 수도 있다.

```toml
[providers.claude]
executable = "claude.exe"
auth_expectation = "subscription"
[providers.codex]
executable = "codex.exe"
auth_expectation = "subscription"
[agents.plan]
provider = "codex"
model = "gpt-6.1-sol"
[agents.code]
provider = "claude"
model = "claude-sonnet-5-5"
[agents.review]
provider = "codex"
model = "gpt-6-astra"
perspective = "adversarial"
[roles.planner]
agents = ["plan"]
[roles.coder]
agents = ["code"]
[roles.tester]
agents = ["code"]
test_paths = ["tests/"]
[roles.reviewer]
agents = ["review"]
```

mixed의 coder와 tester는 같은 tuple이므로 같은 agent를 참조하지만 새 세션과 다른 파일 권한으로 실행한다. reviewer를 추가하면 동일 snapshot과 독립 입력으로 순차 호출하고 전원 완료를 요구한다. planner와 coder는 각각 정확히 한 명이며 배열을 늘리면 설정 오류다.


## 추가 명령 예시

다음은 Node.js 저장소에서 전체 예시의 prepare table을 교체하는 예시다. npm JS의 경로는 저장한 임의 문자열이 아니라 doctor가 발견한 실제 진입점으로 고정한다.

```toml
[prepare]
network = "allowed"
dependency_paths = ["node_modules/"]
manifest_paths = ["package.json", "package-lock.json"]
on_lock_change = "stop"
on_dependency_change = "stop"
[[prepare.commands]]
id = "node-deps"
argv = ["npm", "ci"]
launcher = "node-npm"
cwd = "."
timeout_seconds = 900
success_exit_codes = [0]
```

다음은 직접 입력 wrapper 검사의 checks 교체 예시다. 필요한 Gradle 배포본과 의존성은 prepare에서 이미 확보해야 하며 build 산출물은 scratch로 분리한다. 실제 runner와 quoting, source 무변경은 doctor가 한 번 시험하기 전까지 미확인이다.

```toml
[checks]
enabled = true
network = "blocked"
[[checks.commands]]
id = "gradle-tests"
source = "custom"
trial = "doctor-once"
argv = ["gradlew.bat", "--offline", "test"]
launcher = "cmd-wrapper"
cwd = "."
timeout_seconds = 300
success_exit_codes = [0]
scratch_paths = ["build/", ".gradle/"]
```

## doctor 항목과 결과 표시

1. Git root와 고정 HEAD, 원본 변경 경고, control 설정의 출처와 hash를 확인한다. lock이 없으면 run을 시작하지 않고 run 밖에서 uv lock 또는 npm install 등으로 생성하도록 안내한다. manifest 불일치도 중단한다.
2. 실제 runtime의 CLI 버전을 각 모델의 최소 버전과 비교한다. 미달 agent는 probe 실패이고 모델 호출은 하지 않는다.
3. 실제 실행 파일과 node/npm JS, version manager 및 Corepack 경로, wrapper 고정 인자를 확인한다.
4. prepare의 등록 argv와 산출물 및 manifest 경로, 첫 실패 처리와 prepare/check 네트워크 구분을 확인한다.
5. custom 명령은 별도 probe workspace에서 prepare 뒤 1회 시험한다. 기록은 trial=pending/passed/failed와 관측 종료 및 파일 변화, baseline 테스트 결과를 나눠 표시한다. passed를 사용자가 설정 파일에 써서 위조하는 형태는 제공하지 않는다.
6. trusted-local 권한 옵션과 도구 제한 및 사후 범위 감사, timeout과 자식 종료, 평소 hooks와 서명 준비를 확인한다.
7. 구조화 출력과 모델 실제 접근은 별도 사용량 probe로 구분한다. 미확인 값을 성공으로 채우지 않는다.

CLI에는 trusted-local과 보장 제외 범위를 명시한다. AI의 공식 서비스 통신과 확인 후 Git 공개 통신을 프로젝트 의존성 네트워크와 구분한다. prepare 로그는 운영 기록이며 모델 prompt와 check 결과로 승격하지 않는다. 기능 검증은 아직 미확인이다.

## D13 계획과 승인

기획자 결과의 plan.new_dependencies_required(boolean)와 plan.dependency_reason(string)을 승인 화면에 표시한다. 새 의존성이 필요하면 사람이 run 밖에서 먼저 추가한 뒤 재시작한다. 코더가 승인 계획에 없던 manifest나 lock을 수정하면 중단한다. 계획에 있어도 run 안 lock 변경은 D12에 따라 중단하며 자동 prepare 재실행은 하지 않는다.
