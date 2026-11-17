# 초안 적대적 검토 결과

최종 갱신: 2026-11-17. 1차와 2차 검토일은 2026-11-16, 3차는 2026-11-17이다. 대상: `claude-docs/`의 원문 4개 전체. 원문은 수정하지 않는다. 3차 검토와 2026-11-17 사용자 결정, M0 확인 실험(#3부터 #7까지) 결과까지 반영했다. 구현의 안전성과 품질을 검증한 결과가 아니라 기획의 모순과 실행 전제를 검토한 결과다.

문서 검토의 심각도는 높음, 중간, 낮음이며 제품 리뷰의 P0부터 P5까지와 구분한다. 높음은 권한이나 gate 우회, 사용자 변경 손실, 필수 요구 미충족으로 이어지는 항목이다. 중간은 구현 전 보완이 필요한 계약과 근거 부족이다. 낮음은 사용성과 단계 구분 문제다. 1차 위치는 당시 원문의 1부터 시작하는 줄 번호다. 2차 항목은 현재 문서의 절과 C1부터 C11까지의 원문 위치를 사용한다. 1차 항목의 반영과 상태는 이번 결정에 맞게 갱신했다.

## 명령 실행 기록

| ID | 명령 | 관측 결과 | 확인 범위 |
|---|---|---|---|
| C01 | `Get-Command claude,codex` | 두 실행 파일 발견. Claude는 사용자 로컬 bin, Codex는 설치된 WindowsApps 경로 | 설치 발견. 로그인과 모델 접근은 확인하지 않음 |
| C02 | `claude --version` | exit 0, `2.1.316 (Claude Code)` | 설치 버전 |
| C03 | `claude --help` | exit 0. `-p`, `--model`, `--effort`, `--fallback-model`, `--tools`, `--allowedTools`, `--json-schema`, `--output-format`, `--max-budget-usd`, `--restricted`, `--safe-mode`, `--bare` 표시 | 옵션의 존재와 도움말 의미. 실제 옵션 조합의 성공은 미확인 |
| C04 | `claude --max-turns 1 --help` | exit 0, 도움말 출력 | turn 제한의 실제 작동을 검증한 명령이 아님 |
| C05 | `codex --version` | exit 0, `codex-cli 0.169.0-alpha.11.1` | 설치 버전. 안정판 전체의 동작으로 일반화하지 않음 |
| C06 | `codex --help` | exit 0. `-a never`, sandbox 3종, `-c`, `-m`, `-C` 표시 | 상위 옵션의 존재 |
| C07 | `codex exec --help` | exit 0. `--output-schema`, `-o`, `--json`, `--ephemeral`, `--skip-git-repo-check`, `--ignore-user-config`, `--ignore-rules` 표시 | 해당 옵션의 존재. 전용 turn, dollar 상한 옵션은 이 도움말에 없음 |
| C08 | `codex exec resume --help` | exit 0, resume subcommand와 session 선택 옵션 표시 | 세션 재개 기능의 존재. 오케스트레이터 checkpoint 기능이 아님 |
| C09 | `codex login status --help`, `codex sandbox --help` | exit 0 | 도움말만 실행. 로그인 상태와 sandbox 명령은 실행하지 않음 |
| C10 | `git status --short` | `fatal: not a git repository` | 현재 문서 폴더에 Git 저장소 없음. Git 초기화하지 않음 |
| C11 | `git --version` | `git version 2.53.0.windows.2` | 설치 버전 |

Codex 도움말 호출에는 임시 디렉터리 정리와 PATH alias 생성의 `Access denied (os error 5)` 경고가 있었다. 도움말은 반환됐지만 sandbox의 권한 강제를 확인한 결과는 아니다. 이 경고를 제품 권한 시험의 성공으로 세지 않는다.

모델 호출, 로그인 변경, 인증 파일 열람, 한도 소진 시험, 파일 변경을 유도하는 권한 probe는 실행하지 않았다. 공식 문서 URL은 아래 각 항목의 확인 근거다. 공식 문서와 설치 버전의 기능 범위가 다를 수 있으므로 도움말 확인과 실제 실행 확인을 구분한다.

## 방향 전환 후 교훈의 유효 범위

| 초안 내용 | 판정 | 이유와 반영 |
|---|---|---|
| `02-lessons.md:9,26-29,35-45,51,57`의 역할 위반, 신뢰 경계, 반복 상한, 최신 결과 gate, 구체적 지적 | 유효 | 로컬 권한, checkpoint, snapshot gate와 handoff 필드 설계의 근거로 사용 |
| `02-lessons.md:10-13`의 댓글 꼬리 제거, 리뷰 시작 감시와 여러 댓글 신호 | 직접 이식하지 않음 | CLI envelope와 이벤트 parser로 대체. 예전 출력 문구를 현재 CLI의 사실로 단정하지 않음 |
| `02-lessons.md:19-21`, `03-adversarial-review.md:19-21`의 계정별 token과 댓글 gate, cloud PR 반입 | 로컬 MVP에서 무효 | 원격 GitHub 자동 흐름의 장치. 본인 subprocess 실행의 출처 인증과 다름 |
| `02-lessons.md:49`, `03-adversarial-review.md:26-27`의 과거 실적과 충분성 주장 | 설계 참고만 유효 | 원본 운영 로그는 제공되지 않았고 다른 실행 흐름의 비교 기준선도 아님 |

선행 교훈의 도메인은 새 문서에 옮기지 않는다. 기록된 사례는 작성자의 운영 보고로 취급하며 별도 원본 로그로 재검증한 사실이라고 표시하지 않는다.

## 검토 항목

### R01 GitHub 계정 gate가 단일 provider 요구와 충돌

- 대상: 03-adversarial-review.md:20. 대조: [01-overview.md](decisions.md#결정-기록):10,22-26, 04-cli-config-review.md:11.
- 심각도: 높음.
- 문제: Codex 계정의 리뷰만 인정하면 Claude-only 구성이 완료될 수 없다. 댓글 계정으로 구현자와 리뷰어를 가르던 규칙을 로컬 subprocess에 적용했다.
- 근거: 위 원문 간 모순. 로컬 호출에서는 회사별 댓글 계정이 출처를 증명하지 않는다.
- 반영: 01-plan의 provider 독립 gate와 03-roles-and-handoff의 trusted record로 대체했다. 같은 provider의 정식 리뷰도 인정한다.

### R02 cloud와 GitHub Actions 대응을 로컬 흐름에 혼합

- 대상: 03-adversarial-review.md:19,21,24-25,31-32. 대조: [01-overview.md](decisions.md#결정-기록):8,14,24.
- 심각도: 중간.
- 문제: push 뒤 자동 리뷰 감시, Codex cloud의 별도 PR 반입, 계정별 프로토콜은 로컬 CLI 실행의 필수 문제가 아니다.
- 근거: C07의 `codex exec`는 로컬 비대화형 실행이다. [Codex 비대화형 문서](https://learn.chatgpt.com/docs/non-interactive-mode)는 scripts에서 호출하는 흐름을 설명한다.
- 반영: 사용자 결정으로 갱신. GitHub Actions와 cloud 규칙은 이식하지 않으며 로컬 브랜치 자동 commit과 확인 후 push 및 선택적 Draft PR을 MVP에 포함한다. patch 선택은 삭제했다.
- 상태: 2차 결정과 검토 반영.

### R03 다중 agent를 필수 요구로 본 판단 철회

- 대상: 1차 common-docs의 역할 다중 배정 계약, 2차 검토 C1:19-24.
- 심각도: 높음.
- 상태: 철회.
- 문제: 1차 R03은 Claude의 잘못된 요약을 필수 요구로 받아 planner와 coder 다중 배정을 MVP에 넣었다. 사용자 정정은 역할별 모델 선택과 같은 모델의 다중 역할이지 역할당 여러 agent 필수가 아니다.
- 근거: C1과 이번 사용자 지시의 C1 처리 결정. 과거 01-overview:9의 요약과 다르더라도 최신 정정을 기준으로 한다.
- 반영: 철회 상태 유지. 2026-11-17 결정 :21에 따라 planner와 coder는 각각 한 명, 복수 reviewer는 지원한다.

### R04 도구 제한을 읽기 전용 보장으로 취급

- 대상: [01-overview.md](decisions.md#결정-기록):25,31, 04-cli-config-review.md:21,100, 03-adversarial-review.md:22.
- 심각도: 높음.
- 문제: `--allowedTools`는 자동 승인 설정이고 `--tools`는 사용 가능한 built-in 도구 제한이다. Bash를 빼는 조치만으로 프로세스 전체와 확장 도구의 쓰기를 막았다고 할 수 없다.
- 근거: C03의 두 옵션 설명. [Claude CLI reference](https://code.claude.com/docs/en/cli-reference)와 [sandbox 밖 실행 경로](https://code.claude.com/docs/en/sandboxing#what-runs-outside-the-sandbox).
- 반영: trusted-local로 확정했다. 권한 옵션과 도구 제한 및 실행 뒤 범위 감사와 중단을 MVP 기준으로 삼고 사전 경로 강제를 보장으로 쓰지 않는다.
- 상태: 2026-11-17 결정 반영.

### R05 비대화형 시작 과정의 hooks와 자동 설정 실행 누락

- 대상: 04-cli-config-review.md:15,21,100,111.
- 심각도: 높음.
- 문제: 모델이 도구를 쓰기 전에도 project hooks와 확장 설정의 실행 경로가 있다. 무신뢰 레포에서 단순 schema 요청도 안전하다고 할 수 없다.
- 근거: C03은 `-p`의 workspace trust 생략을 명시한다. [Claude hooks의 workspace trust](https://code.claude.com/docs/en/hooks#workspace-trust)는 비대화형 세션의 신뢰 처리를 설명한다. managed 설정은 일반 사용자 설정으로 모두 끌 수 없다.
- 반영: trusted-local 보장 범위에서 설정과 확장 실행 경로를 기록한다. 악의적 hooks와 prompt injection 방어를 MVP 보장으로 표시하지 않는다.
- 상태: 2026-11-17 결정 반영.
- M0 결과: `claude -p`의 Bash 거부 사례에서 모델이 Drive, Docs 같은 MCP 도구를 언급했다. `--tools`와 별개로 사용자 MCP 서버가 노출됐을 수 있지만 출력에 도구 목록이 없어 미확인이다. `codex exec`는 모든 호출에서 사용자 홈의 `.agents\skills`를 읽었다. [claude-headless C2](probes/claude-headless.md#c2---tools로-쓰기-도구와-bash-제외), [codex-exec 공통 출력 형태](probes/codex-exec.md#공통-출력-형태)

### R06 Windows의 두 provider가 같은 sandbox를 제공한다는 전제

- 대상: 04-cli-config-review.md:15,100,136, [01-overview.md](decisions.md#결정-기록):31,63.
- 심각도: 높음.
- 문제: Windows 실행 파일이 있다는 사실과 역할별 권한을 강제할 수 있다는 사실이 다르다. 기존 초안은 필요한 기능을 이미 갖췄다고 단정했다.
- 근거: [Claude sandbox 문서](https://code.claude.com/docs/en/sandboxing)는 native Windows shell에 Bash sandbox가 적용되지 않는다고 설명한다. [Codex Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)는 native 구현과 장치 및 정책 조건을 설명한다. 이 PC의 차단 동작은 시험하지 않았다.
- 반영: 저장소별 runtime 규칙을 유지한다. native의 Bash sandbox 미적용은 알리되 untrusted의 사전 강제 조건을 MVP에서 뺐다.
- 상태: 2026-11-17 결정 반영.
- M0 결과: Codex 0.167.0-alpha.3.2의 native Windows sandbox에서 read-only는 작업 폴더 안과 밖 쓰기를, workspace-write는 밖 쓰기를 OS 접근 거부로 막았다. `-a never`에서 승인 대기는 없었다. read-only에서는 명령 작업 폴더가 `-C`와 달랐고 처음 명령이 `CreateProcessWithLogonW failed: 267`로 실패했다. [codex-exec X2](probes/codex-exec.md#x2-sandbox-read-only와-workspace-write--a-never)

### R07 사후 git status와 자동 복원이 사용자 변경을 잃게 할 수 있음

- 대상: 04-cli-config-review.md:100.
- 심각도: 높음.
- 문제: “있으면 되돌린 뒤 멈춘다”는 규칙은 동시에 발생한 사용자 변경까지 지울 수 있다. 사후 감시는 이미 일어난 유출이나 외부 파일 변경을 예방하지 못한다.
- 근거: [git status 설명](https://git-scm.com/docs/git-status)은 ignored 파일을 별도 옵션으로 다룬다. 단순 status는 전체 파일 감사도 아니다. 자동 복원의 손실 가능성은 원문이 동시 편집을 인정한 :105와의 충돌이다.
- 반영: warn-head로 확정했다. 원본 변경을 경고하고 고정 HEAD에서 시작하며 자동 복원과 원본 변경 포함을 하지 않는다.
- 상태: 2026-11-17 결정 반영.

### R08 worktree를 보안 격리로 오인할 수 있음

- 대상: 04-cli-config-review.md:82,105, [01-overview.md](decisions.md#결정-기록):64.
- 심각도: 높음.
- 문제: 별도 worktree는 사용자 checkout과 작업 파일을 나누지만 원본 repo의 Git 관리 데이터와 사용자 환경을 보호하지 않는다.
- 근거: [Git worktree의 refs와 config 공유](https://git-scm.com/docs/git-worktree#_refs).
- 반영: worktree는 작업 분리로만 설명한다. 평소 Git hooks를 실행하고 tree 및 source 변경은 사후 확인하며 악의적 격리를 보장하지 않는다.
- 상태: 2026-11-17 결정 반영.

### R09 JSON Schema를 prompt injection 방어로 과대평가

- 대상: 04-cli-config-review.md:101,111, [01-overview.md](decisions.md#결정-기록):32.
- 심각도: 높음.
- 문제: schema에 맞는 문자열에도 다음 모델을 속이는 지시가 들어갈 수 있다. “입력은 자료”라는 prompt만으로 제어 경계를 만들 수 없다.
- 근거: Schema의 타입 검사는 문자열의 지시 의미를 제거하지 않는다. [Claude의 prompt injection 설명](https://code.claude.com/docs/en/security#protect-against-prompt-injection)도 권한과 실행 경계의 필요성을 다룬다.
- 반영: Schema는 구조 검사로 한정한다. 실행 옵션과 권한, 명령 및 공개 승인을 자유 텍스트에서 받지 않는다. 새 reviewer 수정 판정만 유한 enum과 고정 전이로 검사해 처리한다.
- 상태: 2차 결정과 검토 반영.

### R10 로컬 결과와 승인 기록의 출처 및 쓰기 경계 미정

- 대상: [01-overview.md](decisions.md#결정-기록):23,33, 04-cli-config-review.md:90,101,110, 03-adversarial-review.md:20.
- 심각도: 높음.
- 문제: 코더가 result, check-results나 승인 파일을 쓸 수 있으면 schema에 맞는 통과 기록을 위조할 수 있다. 실행 ID를 모델이 자기 보고해도 해결되지 않는다.
- 근거: 원문은 JSON 파일 전달과 gate를 말하지만 해당 파일의 생성자와 권한을 정하지 않았다. 이는 설계상의 누락이다.
- 반영: 오케스트레이터가 별도 확인한 control 설정과 관측 결과를 고정한다. 악의적 controller 변조의 사전 차단은 현재 trusted-local 보장 밖이다.
- 상태: 2026-11-17 결정 반영.

### R11 HEAD만으로 최신 검사와 리뷰를 식별할 수 없음

- 대상: 02-lessons.md:43-44, [01-overview.md](decisions.md#결정-기록):53-55, 04-cli-config-review.md:90,110.
- 심각도: 높음.
- 문제: 로컬에서는 같은 `HEAD` 아래 미커밋 파일이 달라질 수 있다. 이전 코드 상태의 검사와 리뷰를 새 코드의 통과 근거로 쓸 수 있다.
- 근거: 선행 교훈은 현재 커밋 조건을 명시하지만 로컬 초안에는 미커밋 상태 식별 계약이 없다.
- 반영: snapshot과 plan 및 config hash로 결과를 묶는다. 전체 ignored 내용 hash는 폐기하고 tracked 및 승인 새 파일만 hash하며 나머지는 metadata로 감사한다.
- 상태: 2차 결정과 검토 반영.

### R12 check가 변경된 코드를 호스트에서 실행하는 경로

- 대상: [01-overview.md](decisions.md#결정-기록):53, 04-cli-config-review.md:79,109,111.
- 심각도: 높음.
- 문제: 고정된 테스트 명령도 코더가 바꾼 script와 import 코드를 실행한다. 모델이 명령을 직접 선택하지 않는다는 이유로 호스트에서 안전해지지 않는다. 검사 argv, cwd와 실패 처리도 없다.
- 근거: 변경 가능한 코드를 실행하는 구조에서 도출되는 설계 분석. [Codex 자동 실행 문서의 인증 환경 주의](https://learn.chatgpt.com/docs/non-interactive-mode#authenticate-in-automation)도 repo-controlled code와 credential 환경의 결합을 경고한다.
- 반영: 검사 off 규칙은 유지하고 prepare는 workspace 생성 직후 오케스트레이터가 수행한다. prepare와 check 및 check-probe를 구분하며 검사 네트워크는 blocked다.
- 상태: 2026-11-17 결정 반영.

### R13 두 CLI의 구조화 출력 수락 절차가 불충분

- 대상: 04-cli-config-review.md:22,101, 02-lessons.md:10-13.
- 심각도: 높음.
- 문제: Claude의 JSON envelope, `structured_output`, Codex의 JSONL 이벤트와 최종 JSON은 같은 형식이 아니다. exit 0이나 JSON 일부만으로 정상 결과라 판단하면 거절과 부분 출력을 통과시킬 수 있다.
- 근거: C03과 C07. [Claude 구조화 출력](https://code.claude.com/docs/en/headless#get-structured-output), [Codex 비대화형 출력](https://learn.chatgpt.com/docs/non-interactive-mode).
- 반영: provider별 parser와 공통 검증을 분리했다. 종료 상태, 완전한 결과, Schema와 의미 검증을 모두 요구한다. 옛 댓글 꼬리를 제거하는 parser를 재사용하지 않는다.
- M0 결과: Claude는 `structured_output`, Codex는 `-o` 파일과 `turn.completed`로 결과를 받았다. Claude는 오류에서도 `subtype`이 `success`여서 exit code와 `is_error`, `terminal_reason`으로 판정해야 한다. Codex 실패는 exit 1과 `turn.failed`다. [claude-headless 공통 출력 형태](probes/claude-headless.md#공통-출력-형태), [codex-exec 공통 출력 형태](probes/codex-exec.md#공통-출력-형태)

### R14 공통 Schema 제한과 지원 모델 범위를 단정할 수 없음

- 대상: 04-cli-config-review.md:25,101,108,137.
- 심각도: 중간.
- 문제: `additionalProperties: false`만으로 두 CLI와 모든 모델의 호환성이 확보되지 않는다. 모든 property의 required 처리도 필요하고, “일부 모델만 지원한다는 자료”는 출처가 없다.
- 근거: [OpenAI Structured Outputs 제한](https://developers.openai.com/api/docs/guides/structured-outputs). C07은 옵션 존재만 확인한다. CLI 모델별 수락 목록은 이번 확인 범위에서 미확인이다.
- 반영: 단순한 고정 root Schema와 전부 required인 객체로 초안을 작성했다. 역할별 의미 검사는 로컬에서 수행하고 선택 모델별 probe를 요구한다. 실제 공통 지원이 검증됐다고 표시하지 않는다.
- M0 결과: 공통 role-result Schema를 Claude haiku의 `--json-schema`와 Codex `gpt-6-astra`의 `--output-schema`가 모두 수락했고 결과가 로컬 부분집합 검사를 통과했다. Codex는 required에 없는 property가 있으면 `invalid_json_schema`(400)로 거부했다. 다른 모델과 `pattern`, `format`의 강제 여부는 미확인이다. [claude-headless C3](probes/claude-headless.md#c3---json-schema-출력과-schema-수락), [codex-exec X3](probes/codex-exec.md#x3---output-schema-엄격-규칙과--o)

### R15 자동 fallback이 한도와 부분 변경 문제를 해결한다는 가정

- 대상: 04-cli-config-review.md:20,51,104, 03-adversarial-review.md:19,21.
- 심각도: 중간.
- 문제: fallback 값이 모델명인지 agent ID인지 혼재한다. 같은 계정의 다른 모델은 한도를 공유할 수 있고, 코더가 남긴 부분 변경 위에 다른 모델이 자동 재실행할 위험이 있다.
- 근거: C03은 `--fallback-model`을 overloaded 또는 unavailable 모델에 대한 기능으로 설명한다. [Claude 구독 사용량 안내](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-max-or-ultra-plan)는 제품과 모델 간 사용 한도를 설명한다. 이 계정의 남은 양과 오류 형태는 미확인이다.
- 반영: MVP 자동 fallback을 제외했다. 한도에서 중단하고 부분 변경과 checkpoint를 보존한다. 인증과 청구 경로를 자동 전환하지 않는다.

### R16 구독 로그인 재사용과 제3자 인증 중계의 범위 혼동

- 대상: 04-cli-config-review.md:15,41,45,135, [01-overview.md](decisions.md#결정-기록):76.
- 심각도: 중간.
- 문제: `auth="subscription"` 설정만으로 로그인과 약관 조건을 해결할 수 없다. 본인이 공식 binary에 로그인하는 것과 제3자가 구독 자격증명을 수집해 요청을 중계하는 서비스는 다르다.
- 근거: [Claude 이용 범위 안내](https://code.claude.com/docs/en/legal-and-compliance)는 본인 unmodified CLI 로그인과 금지된 인증 중계 범위를 구분한다. [Codex 인증 안내](https://learn.chatgpt.com/docs/auth)는 구독과 API key 경로를 구분하고 programmatic workflow에 API key를 안내한다. 비대화형 기술 지원이 모든 배포 형태의 허가를 뜻하지 않는다.
- 반영: 본인 로컬 사용으로 한정하고 `auth_expectation`은 확인 조건으로 정의했다. 토큰 추출과 복사, 대행 로그인은 제외했다. 재배포나 서비스화의 구체적 허용 범위는 미확인으로 남긴다.

### R17 모델 별칭과 effort를 같은 수준의 실행 증거로 취급

- 대상: 04-cli-config-review.md:20,49-60,123-129,138.
- 심각도: 중간.
- 문제: effort 지정 방법을 모르는 상태에서 다양성 검증에 사용했고, 별칭 문자열이 실제 모델 버전과 동일하다고 볼 수 없다. `fable` 자체를 허구 모델로 고치는 것도 오류다.
- 근거: C03은 `fable`, `opus`, `sonnet` 별칭과 `--effort`를 명시한다. [Claude 모델 설정](https://code.claude.com/docs/en/model-config)은 버전 요건과 정책 제한을 설명한다. [Codex effort 설정](https://learn.chatgpt.com/docs/config-file/config-reference)의 지원 값은 모델과 client 의존적이다.
- 반영: 사용자 결정의 전체 모델 ID와 registry를 적용했다. 별칭 저장을 거부하고 Fable의 설치 버전 부족을 별도 표시한다. 계정 접근과 실효 effort는 미확인이다.
- 상태: 2차 결정과 검토 반영.
- M0 결과: Claude `--effort`는 `low`부터 `max`까지 받았고 알 수 없는 값은 경고 뒤 기본값으로 진행했다(exit 0). Codex는 API가 값을 검사해 `gpt-6-astra`의 `minimal`과 알 수 없는 값을 400으로 거부했다. 두 CLI 모두 실효 effort를 출력하지 않는다. [claude-headless C5](probes/claude-headless.md#c5---effort-값), [codex-exec X5](probes/codex-exec.md#x5-effort-값-이름)

### R18 비용과 turn 상한을 공통 실행 상한으로 사용할 수 없음

- 대상: 04-cli-config-review.md:23,109,137.
- 심각도: 중간.
- 문제: Claude의 API dollar 옵션은 구독 잔량을 제한하는 공통 기능이 아니다. Codex exec 도움말에는 대응하는 turn과 dollar 상한이 없으며, 없는 기능을 추측할 수 없다.
- 근거: C03, C04, C07과 [Claude CLI reference](https://code.claude.com/docs/en/cli-reference). 실제 상한 도달의 exit code와 JSON은 미확인이다.
- 반영: invocation과 run의 wall-clock 상한을 오케스트레이터에 뒀다. 비용을 정확히 고정하거나 구독 한도를 보장한다고 표현하지 않는다. provider별 추가 상한은 이후 단계다.

### R19 any와 majority가 차단 결함을 투표로 무시할 수 있음

- 대상: 04-cli-config-review.md:75,102. 대조: 02-lessons.md:42-45.
- 심각도: 높음.
- 문제: 한 리뷰어가 실제 차단 결함을 찾아도 다른 리뷰어의 찬성으로 통과할 수 있다. 동률과 분모, 미응답의 처리도 없다.
- 근거: 초안의 `any`, `majority`는 선행 교훈의 미해결 차단 지적 없음과 다르다.
- 반영: 투표를 제외하고 전원 리뷰 완료와 P0부터 block_up_to까지의 미해결 지적을 검사한다. 검사 off는 qualified 완료이며 검사 성공으로 계산하지 않는다.
- 상태: 2차 결정과 검토 반영.

### R20 pipeline 순서 설정으로 필수 gate를 제거할 수 있음

- 대상: 04-cli-config-review.md:78-83, [01-overview.md](decisions.md#결정-기록):53-55.
- 심각도: 높음.
- 문제: 자유로운 단계 배열만 있고 필수 단계와 순서 제약이 없다. 승인과 check를 빼거나 리뷰를 구현 앞으로 옮길 수 있다.
- 근거: 원문에는 정상 예시만 있고 거부해야 하는 배열의 조건이 없다.
- 반영: pipeline.flow의 고정 흐름 2종으로 갱신했다. tester와 check의 조건, commit과 확인 후 publish를 코드의 허용 전이로 제한한다.
- 상태: 2차 결정과 검토 반영.

### R21 기획자 중재가 차단 지적의 강제 통과 경로가 될 수 있음

- 대상: 04-cli-config-review.md:76,103, [01-overview.md](decisions.md#결정-기록):33,54.
- 심각도: 높음.
- 문제: `on_conflict="planner"`가 어떤 증거와 권한으로 코더와 리뷰어의 분쟁을 종결하는지 없다. 계획 작성자의 판단이 구현 결함의 기각 근거가 될 수 있다.
- 근거: 오케스트레이터가 gate를 판단한다는 원칙과 모델에게 최종 중재를 맡기는 설정 사이의 경계가 없다.
- 반영: MVP는 분쟁 시 사람에게 중단 보고한다. 기획자는 추가 설명을 할 수 있지만 승인이나 차단 기각 권한을 갖지 않는다. 검토 없이 수동 성공 처리하는 경로도 두지 않았다.

### R22 doctor와 실행 기록이 MVP 뒤로 밀림

- 대상: [01-overview.md](decisions.md#결정-기록):63-66, 04-cli-config-review.md:107-110.
- 심각도: 중간.
- 문제: 모델과 schema 지원 확인, 권한 강제와 최신 결과 판정에 필요한 기능을 이후 단계에 배치했다.
- 근거: 원문 :63의 두 CLI 검증과 :65-66의 기능 구현 단계가 분리되어 검증 결과를 실행 때 적용하는 계약이 없다.
- 반영: 대화형 setup과 역할 배정 명령, 최소 doctor 및 기록을 MVP로 옮겼다. 입력 순서와 동일 agent 묶기를 완료 조건으로 명시했다.
- 상태: 2차 결정과 검토 반영.

### R23 fresh session과 계획 없는 리뷰의 의미가 혼재

- 대상: 04-cli-config-review.md:125,127, [01-overview.md](decisions.md#결정-기록):36.
- 심각도: 중간.
- 문제: 같은 agent를 재사용할 때 세션과 권한을 초기화하는 합성 규칙이 없다. 계획 없이 diff만 보는 유일 리뷰어는 승인 요구 준수를 검토할 수 없고 주변 코드 영향도 빠질 수 있다.
- 근거: :125는 계획과 diff 입력을 고정하지만 :127은 계획 생략을 제안한다. 새 세션도 자동 memory와 설정 로딩 통제가 없으면 입력 격리를 증명하지 못한다.
- 반영: fresh context와 reviewer의 승인 요구 검토를 유지한다. tester는 사용자 결정에 따라 plan과 diff만 받으며 정보 부족의 한계는 R44에 기록했다.
- 상태: 2차 결정과 검토 반영.

### R24 다양성 문자열과 지적 수가 품질 향상을 증명하지 않음

- 대상: [01-overview.md](decisions.md#결정-기록):36-37, 04-cli-config-review.md:123-131, 03-adversarial-review.md:23,27.
- 심각도: 중간.
- 문제: persona만 바꿔도 경고를 피할 수 있다. 지적 수와 반복 수는 중복, 오탐과 작업 난도를 통제하지 못한다. 한 번 결함을 잡았다는 사실로 리뷰어의 충분성을 판단할 수 없다.
- 근거: 초안에는 독립성이나 품질 차이를 측정한 비교 실험이 없다. 효과는 미확인이다. 다른 회사가 항상 우수하다는 비교도 제시되지 않았다.
- 반영: 다양성 수단 제공과 효과 입증을 분리했다. 고정 작업 묶음, 알려진 결함 탐지, 사람 판정 고유 결함과 오탐, 시간과 사용량을 함께 평가하도록 01-plan에 정의했다.

### R25 과거 GitHub 기록을 새 로컬 제품의 기준선으로 사용

- 대상: 03-adversarial-review.md:26-27, 02-lessons.md:49-51.
- 심각도: 중간.
- 문제: 회사 조합이 같다고 과거 실행 흐름과 작업 난도, 사람 대기 조건까지 같아지는 것은 아니다. 과거 운영 수치의 원본도 제공되지 않았다.
- 근거: 02의 기록은 GitHub Actions의 생성과 merge, 대기 시간을 다루며 01의 목표는 로컬 CLI다.
- 반영: 이전 기록은 반복 방지와 측정 필드의 근거로만 사용했다. 새 제품은 새 비교 기준선을 만들며 이전 도메인과 수치는 결과 문서에 옮기지 않았다.

### R26 파일만 추가하는 범용 역할 확장의 계약 누락

- 대상: [01-overview.md](decisions.md#결정-기록):35,67, 04-cli-config-review.md:33,86-91.
- 심각도: 중간.
- 문제: 임의 schema를 정의해도 scheduler가 입력과 출력의 의미, 실패와 gate, 새 쓰기 역할을 처리하는 방법은 정해지지 않는다.
- 근거: 원문 role 파일 예시는 prompt, access, inputs와 output_schema만 있고 제어 계약이 없다.
- 반영: tester를 첫 추가 쓰기 역할로 허용했다. 새 쓰기 역할은 kind와 입력, 파일 소유권, scheduler와 회차 및 validator 계약을 등록한 뒤 추가한다.
- 상태: 2차 결정과 검토 반영.

### R27 Windows timeout과 Ctrl+C의 자식 프로세스 처리 누락

- 대상: 04-cli-config-review.md:109, [01-overview.md](decisions.md#결정-기록):34.
- 심각도: 중간.
- 문제: 부모 CLI만 죽으면 shell과 검사 프로세스가 남아 timeout 이후 파일을 바꿀 수 있다. 시작한 프로세스 트리의 종료 확인 계약이 없다.
- 근거: [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)는 프로세스 집합 관리와 제한을 설명하며 예외도 있다. 이 프로젝트의 실제 구현과 종료 시험은 없다.
- 반영: 프로세스 트리 종료 확인 전 lock을 풀지 않도록 명시했다. 구체 구현은 언어와 runtime 선택 뒤 검증한다. Job Object 자체를 보안 sandbox로 표현하지 않는다.
- M0 결과: Windows에서 `Popen.kill()`과 `subprocess.run(timeout=)`은 손자 프로세스를 남겼다. `taskkill /T /F`, Job Object(`KILL_ON_JOB_CLOSE`), `CREATE_NEW_PROCESS_GROUP`과 `CTRL_BREAK_EVENT`는 손자까지 끝냈다. 구현 방식은 아직 정하지 않았다. [windows-process W1](probes/windows-process.md#w1-시간-상한-뒤-자식-프로세스까지-종료)

### R28 설정 타입과 경로 및 shell 경계가 미정

- 대상: 04-cli-config-review.md:36-91,109.
- 심각도: 중간.
- 문제: 필수값, 기본값과 허용값, 참조 검증이 없다. 실행 command와 prompt를 shell 문자열로 조합하면 Windows 인자와 경로의 경계를 잃는다.
- 근거: [Python subprocess 보안 설명](https://docs.python.org/3/library/subprocess.html#security-considerations), [Windows 경로 규칙](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file). 초안은 `command="claude"` 이상을 정하지 않았다.
- 반영: Python으로 구현하며 project.uncommitted_changes와 prepare 및 git 항목을 반영했다. npm/npx 직접 node 호출, 제한 wrapper와 custom doctor 시험 규칙으로 갱신했다.
- 상태: 2026-11-17 결정 반영.

### R29 저장소 독립성과 Git 없는 폴더 지원을 구분하지 않음

- 대상: [01-overview.md](decisions.md#결정-기록):14,64, 04-cli-config-review.md:25,82.
- 심각도: 중간.
- 문제: worktree를 쓰는 MVP에는 Git과 유효한 HEAD가 필요하다. 특정 repo에 묶이지 않는다는 목표가 Git 없는 폴더까지 지원한다는 의미로 읽힐 수 있다.
- 근거: C07은 Git 검사 우회 옵션의 존재를 확인할 뿐 이 제품의 worktree 요구를 없애지 않는다. C10으로 현재 문서 폴더에도 Git이 없음을 확인했다.
- 반영: MVP 대상은 Git 저장소라고 명시하고 Git 없는 폴더를 범위 밖에 뒀다. 이번 작업에서 Git 초기화나 commit은 수행하지 않는다.

### R30 설정 CLI의 최소 범위와 probe 비용이 드러나지 않음

- 대상: [01-overview.md](decisions.md#결정-기록):8,65, 04-cli-config-review.md:7,107-108,113.
- 심각도: 낮음.
- 문제: 설정 파일만 있는 MVP가 CLI에서 모델과 역할을 설정한다는 요구를 어느 수준에서 만족하는지 없다. doctor의 짧은 모델 호출은 사용량을 소비할 수 있다.
- 근거: 원문은 마법사를 이후 단계에 두면서 최소 설정 동작과 probe의 경계를 쓰지 않았다.
- 반영: 사용자 결정의 setup 순서와 role assign 및 배정 조회를 MVP 완료 조건에 넣었다. 비용 없는 doctor와 모델 probe를 구분한다.
- 상태: 2차 결정과 검토 반영.

### R31 입력과 로그의 비밀 제거 범위를 정의하지 않음

- 대상: 04-cli-config-review.md:110-111, [01-overview.md](decisions.md#결정-기록):37.
- 심각도: 높음.
- 문제: “비밀 값은 지우고 저장”이라는 말만 있고 소스의 공개 범위와 raw 출력 보관 정책이 없다. 읽기 전용이어도 비밀 파일을 읽어 응답에 넣으면 외부 모델에 전달되거나 실행 기록에 남을 수 있다.
- 근거: 원문이 입력과 출력 기록을 요구하면서 탐지 가능한 비밀의 범위와 읽기 권한을 정의하지 않은 설계 누락이다. [Claude sandbox의 credential 보호 범위](https://code.claude.com/docs/en/sandboxing#protect-credentials)는 인증 자료와 일반 작업 파일을 구분한다.
- 반영: 입력과 정규화 기록의 공개 범위를 명시하고 raw 로그와 인증 자료의 자동 전달을 제외했다. 임의 소스의 비밀 제거와 파일 읽기 사전 제한은 기본 보장으로 주장하지 않는다.
- 상태: 2차 결정과 검토 반영.

## 2차 검토 반영

사용자 결정은 그대로 적용하고 기술적 한계와 미확인은 아래에 남긴다. C1부터 C11까지는 모두 R32부터 R42까지 대응한다. R43부터 R55까지는 새 결정의 추가 검토다. 1차 R03은 철회했으며 심각도 집계에는 발견 당시 이력으로 별도 표시한다.

### 2차 명령 및 공식 문서 확인

| 기록 | 실제 수행과 결과 | 확인 한계 |
|---|---|---|
| V01 | claude --version와 --help. 2.1.316, 전체 모델 이름 지정과 effort 옵션 확인 | 모델 목록 subcommand를 도움말에서 찾지 못했고 모델 호출하지 않음 |
| V02 | codex --version와 --help, exec --help, debug --help, debug models --help | 0.169.0-alpha.11.1. 옵션 존재 확인 |
| V03 | codex debug models --bundled, exit 0. 지정 Codex 4개 slug 모두 확인 | binary 내장 목록이며 계정 접근과 서버 실행 확인이 아님 |
| V04 | git --version, commit -h, push -h, worktree -h | 2.53.0.windows.2. 도움말 일부는 비정상 종료 코드를 사용함. 실제 Git 변경 없음 |
| V05 | gh --version, pr create --help, auth status --help | 2.100.0. 도움말만 확인, 로그인 상태와 token 조회는 하지 않음 |
| V06 | developers.openai.com/codex/models의 learn.chatgpt.com/docs/models redirect와 모델 명령 예시 확인 | 공식 도메인과 문서의 ID 확인. 계정 접근 증거 아님 |
| V07 | Claude 공식 모델 목록과 model-config의 전체 ID 및 최소 CLI 버전 확인 | Opus 2.1.280, Fable 2.1.321, Sonnet 2.1.284, Haiku 2.1.293. 실제 호출 미확인 |

Codex 조회에는 이전과 같은 임시 디렉터리와 PATH alias 생성 Access denied 경고가 있었지만 명령은 반환됐다. 이를 sandbox 또는 권한 차단 성공으로 해석하지 않는다. 모델 호출과 commit, push 및 PR 생성은 실행하지 않았다.

### R32 C1 다중 agent 필수 요구 오해

- 대상: 1차 R03, 01-plan 기본 배정, 02-config-spec 역할 cardinality. C1:19-24.
- 문제: 잘못된 요약으로 기획 후보와 순차 코더를 필수 MVP로 늘렸다.
- 근거: 사용자 C1 정정과 claude-docs/05-common-docs-review.md:22-24.
- 심각도: 높음.
- 반영: planner와 coder는 각각 한 명으로 확정했다. 복수 reviewer는 지원하며 R03의 잘못된 필수 요구 해석은 철회 상태다.
- 상태: 2026-11-17 결정 반영.

### R33 C2 위협 모델과 MVP 보장 수준 미결정

- 대상: 01-plan 권한과 MVP 조건, 05 D06. C2:26-31.
- 문제: 본인 저장소의 실수 탐지와 악의적 코드의 사전 방어를 구분하지 않아 강한 보안 조건을 무조건 요구했다.
- 근거: C2와 기존 01-plan의 모든 경로 사전 차단 완료 조건.
- 심각도: 높음.
- 반영: trusted-local로 결정됐다. 본인 저장소의 실수 탐지와 사후 중단이 MVP 기준이며 untrusted 사전 격리는 이후 검토로 옮겼다.
- 상태: 2026-11-17 결정 반영.

### R34 C3 새 worktree의 의존성 부재

- 대상: 01-plan workspace, 02 검사, 05 D05. C3:33-37.
- 문제: 새 worktree에 ignored 의존성이 없는데 준비된 환경을 전제하고 링크와 설치를 동시에 막았다.
- 근거: C3와 [Git worktree](https://git-scm.com/docs/git-worktree), [Python venv 이동 제한](https://docs.python.org/3/library/venv.html).
- 심각도: 높음.
- 반영: 등록 prepare 명령을 worktree 직후 실행하는 방식으로 확정했다. run마다 사용자 직접 준비 추천은 채택되지 않았다. lock과 구현 중 재준비는 새 선택 D12와 D13이다.
- 상태: 2026-11-17 결정 반영.

### R35 C4 대화형 설정과 역할 배정의 MVP 누락

- 대상: 01-plan setup와 완료 조건, 02 설정 순서. C4:39-43.
- 문제: 파일 편집 안내만으로 CLI에서 역할과 모델을 고르는 요구를 충족한다고 보았다.
- 근거: C4와 이번 사용자 결정의 setup 질문 순서.
- 심각도: 높음.
- 반영: flow부터 묻는 대화형 setup, role assign과 role list, 같은 tuple의 agent 재사용을 MVP에 넣었다.

### R36 C5 승인 입력 범위만 읽는다는 보장 근거 부족

- 대상: 01-plan 권한, 02 adapter, 03 입력. C5:47-51.
- 문제: read-only sandbox가 곧 승인 목록 밖 읽기 차단인 것처럼 약속했다.
- 근거: C5, [Codex permissions](https://learn.chatgpt.com/docs/config-file/config-reference), [Claude Read/Edit 규칙](https://code.claude.com/docs/en/permissions#read-and-edit).
- 심각도: 중간.
- 반영: 기본 보장에서 뺐다. Codex filesystem profile과 Claude 경로 규칙을 단계 0에서 시험하고 shell의 간접 읽기까지 같다고 주장하지 않는다.

### R37 C6 승인 경로와 실제 workspace 쓰기 경계 혼동

- 대상: 03 coder와 tester 권한, 02 access. C6:53-57.
- 문제: Codex workspace-write만으로 plan의 파일 경로별 사전 차단을 약속할 수 없다.
- 근거: C6와 [Codex 설정](https://learn.chatgpt.com/docs/config-file/config-reference)의 writable_roots 및 permissions filesystem 구분.
- 심각도: 중간.
- 반영: workspace 정책과 사후 manifest 탐지를 사용한다. test_paths 사전 강제는 MVP 필수가 아니라는 2026-11-17 결정을 반영했다.
- 상태: 2026-11-17 결정 반영.

### R38 C7 native Claude의 shell 제한이 구현 흐름에 미치는 영향

- 대상: 01-plan native 실행, 05 결정된 D02. C7:59-63.
- 문제: 파일 편집만 하는 코더는 직접 검사하며 수정하는 사용성과 다르지만 선택 영향에 빠졌다.
- 근거: C7와 [Claude sandbox](https://code.claude.com/docs/en/sandboxing).
- 심각도: 중간.
- 반영: 환경 규칙은 결정대로 유지하고 native의 파일 편집 및 check 피드백 흐름을 명시했다. 보호되지 않은 shell을 묵시적으로 열지 않는다.

### R39 C8 WSL2 설치와 디스크 및 로그인 비용 누락

- 대상: 05 결정된 D02, 02 runtime. C8:65-69.
- 문제: WSL2에 Git과 CLI, 의존성과 로그인을 별도로 준비하는 비용을 충분히 적지 않았다.
- 근거: C8의 환경 보고. 현재 WSL2 설치와 디스크 여유 공간은 실측하지 않았다.
- 심각도: 중간.
- 반영: 저장소별 선택 규칙은 유지하고 설치 용량과 이중 관리 비용을 적었다. 디스크 부족 보고를 현재 PC의 확인 사실로 표시하지 않는다.

### R40 C9 ignored 의존성의 전체 hash 비용

- 대상: 01-plan snapshot, 03 snapshot. C9:71-75.
- 문제: 의존성이 생기면 매 단계 전체 내용 hash가 커지는데 감사 범위가 없었다.
- 근거: C9와 기존 문서의 ignored 전체 감사 및 내용 hash 정의의 결합.
- 심각도: 중간.
- 반영: tracked와 승인 새 파일만 내용 hash를 계산하고 나머지는 metadata 감사로 바꿨다. metadata로 악의적 변조를 완전 탐지한다고 주장하지 않는다.

### R41 C10 원본 clean checkout 요구의 근거 부족

- 대상: 01-plan 원본 변경 정책, 05 D09. C10:79-83.
- 문제: 고정 HEAD에서 새 workspace를 만들면서 원본의 모든 미커밋 변경을 무조건 차단했다.
- 근거: C10와 기존 01-plan 기본 흐름 첫 항목.
- 심각도: 낮음.
- 반영: warn-head로 확정했다. 입력 source는 고정 HEAD worktree이며 확인한 실행 설정은 별도 control 입력으로 고정한다.
- 상태: 2026-11-17 결정 반영.

### R42 C11 공식 Codex 문서 도메인 확인

- 대상: 기존 learn.chatgpt.com 링크. C11:85-89.
- 문제: 2차 검토 환경의 접속 실패만으로 공식 링크를 잘못된 도메인으로 바꾸면 안 된다.
- 근거: [기존 공식 주소](https://developers.openai.com/codex/models)가 [Models](https://learn.chatgpt.com/docs/models)로 redirect되는 것을 확인했다.
- 심각도: 낮음.
- 반영: 기존 learn.chatgpt.com 링크를 유지했다. 도메인 확인을 모든 계정의 모델 접근 증거로 확장하지 않는다.

### R43 검사 실패 판정과 공유 수정 회차의 누락

- 대상: 새 tester 결정, 기존 01-plan의 검사 성공 뒤 리뷰 규칙, 개정 03 판정 흐름.
- 문제: 검사 성공 뒤에만 reviewer를 실행하면 코드와 테스트 중 잘못된 쪽을 판단할 수 없고 role별 상한은 반복을 늘릴 수 있다.
- 근거: 사용자 결정의 실패 판정 주체와 기존 gate 순서 사이 모순.
- 심각도: 높음.
- 반영: 정상 실패도 reviewer에게 보낸다. 최초 회차 0, 수정 묶음 시작 때 공유 counter 1회 소비, coder 수정 뒤 tester와 check 및 모든 리뷰 재실행으로 정했다.

### R44 계획과 diff만 받는 테스터의 정보 한계

- 대상: 새 tester 입력 결정, 03 역할 입력과 test_contract.
- 문제: 기존 fixture와 API 문맥, 실패 로그가 없으면 잘못된 테스트를 반복하거나 기대값을 오해할 수 있다. 입력 확대를 몰래 하면 사용자 결정을 위반한다.
- 근거: 이용할 수 없는 정보를 포함한 인터페이스의 설계 분석. 품질 효과는 미측정이다.
- 심각도: 중간.
- 반영: 입력은 그대로 유지한다. 계획에 framework와 API 및 기대값을 쓰고 최신 누적 diff를 제공한다. 정보 부족과 같은 실패 반복은 사람에게 넘긴다.

### R45 test_paths 밖 쓰기의 사전 차단 미확인

- 대상: roles.tester.test_paths, 03 coder와 tester 파일 소유권.
- 문제: tests만 수정하라는 정책과 Codex workspace-write의 실제 허용 범위가 다르다. tester가 assertion을 약화해 실패를 숨길 수도 있다.
- 근거: [Codex permissions](https://learn.chatgpt.com/docs/config-file/config-reference), [Claude 파일 규칙](https://code.claude.com/docs/en/permissions#read-and-edit), 사용자 결정의 테스트 전용 쓰기.
- 심각도: 높음.
- 반영: trusted-local에서 role별 source와 test_paths 범위 밖 변경의 사후 탐지와 중단으로 완료한다. 사전 강제 성공을 요구하지 않는다.
- 상태: 2026-11-17 결정 반영.

### R46 검사 명령의 종료와 부작용을 완전히 사전 판별할 수 없음

- 대상: 새 검사 거부 결정, 02 검사 후보와 custom 입력, 05 D10.
- 문제: 명령 이름만으로 임의 script의 무한 실행과 파일 수정, 설치 및 네트워크 필요성을 모두 알 수 없다.
- 근거: 프로그램 실행의 성질에 대한 설계 한계. [Python subprocess 보안 설명](https://docs.python.org/3/library/subprocess.html#security-considerations)도 인자 배열과 batch 해석의 한계를 구분한다.
- 심각도: 높음.
- 반영: 후보를 기본으로 하고 custom 명령을 doctor에서 1회 시험하기로 확정했다. 별도 workspace에서 시험하며 완전한 미래 동작 보장으로 표현하지 않는다.
- 상태: 2026-11-17 결정 반영.

### R47 자동 commit의 사용자 identity와 Git 확장 실행 경계

- 대상: 새 사용자 이름 commit 결정, 01-plan commit, 05 D11.
- 문제: author와 committer는 인증과 다르고 hooks 및 filters가 controller 권한으로 실행되거나 리뷰 뒤 tree를 바꿀 수 있다. Git 정규화 때문에 raw byte hash와 Git blob을 단순 비교할 수도 없다. no-verify는 전체 hooks 차단이 아니다.
- 근거: [Git commit](https://git-scm.com/docs/git-commit), [Git hooks](https://git-scm.com/docs/githooks), [Git attributes](https://git-scm.com/docs/gitattributes), git commit -h.
- 심각도: 높음.
- 반영: 평소 hooks를 실행하고 사람 개입 서명은 commit 전에 중단한다. 이미 생성된 commit의 tree 불일치는 committed-unverified로 보존하고 publish를 막는다.
- 상태: 2026-11-17 결정 반영.
- M0 결과: worktree 안 commit에서 원본 `.git/hooks`가 실행되고 `--no-verify`에서도 `post-commit`은 실행됐다. 상속 `GIT_CONFIG_COUNT`, `GIT_CONFIG_PARAMETERS` 같은 명령 범위 설정은 전역 설정 파일을 바꿔도 적용돼, 오케스트레이터가 실행하는 git의 환경 변수도 정리 대상이다. [git-behavior G2](probes/git-behavior.md#g2-worktree-안-커밋에서-hooks-실행)

### R48 브랜치 충돌과 push 시점의 공개 노출

- 대상: 새 branch 및 publish 결정, 01-plan 공개 확인.
- 문제: 고정 branch 이름 충돌을 덮어쓰면 기존 결과를 잃고, push만으로 코드와 이름 및 이메일이 공개된다. Draft PR은 비공개 장치가 아니다.
- 근거: [Git worktree](https://git-scm.com/docs/git-worktree), [Git push](https://git-scm.com/docs/git-push), [GitHub 공개 범위](https://docs.github.com/en/repositories/creating-and-managing-repositories/about-repositories#about-repository-visibility).
- 심각도: 높음.
- 반영: 새 run_id와 branch를 만들고 충돌 시 덮어쓰지 않는다. 최초 push는 원격 ref 부재를 조건으로 하는 생성 전용 lease를 사용하며 기존 ref 강제 갱신은 금지한다. 대상과 공개 범위, identity와 SHA를 보여 주고 확인한다.
- M0 결과: 같은 이름 branch의 `git worktree add -b`는 exit 255로 실패했다. `--force-with-lease=<ref>:` 생성 전용 lease는 첫 push만 성공하고 두 번째는 `[rejected] (stale info)`였다(Linux Git 2.34.1). [git-behavior G1](probes/git-behavior.md#g1-worktree-생성과-정리), [G6](probes/git-behavior.md#g6-push-lease와-gh-pr-create의-push-동작)

### R49 gh 인증과 PR 미리보기의 외부 실행 경계

- 대상: 새 Draft PR 결정, 02 output, 03 PR 인계.
- 문제: gh의 기본 create와 dry-run도 push할 수 있고 publish 인증을 모델 및 check에 넘기면 권한이 새어 나간다.
- 근거: 설치 gh pr create --help, [gh PR 생성](https://cli.github.com/manual/gh_pr_create), [gh 환경 변수](https://cli.github.com/manual/gh_help_environment).
- 심각도: 높음.
- 반영: 미리보기는 로컬 렌더링만 한다. push 확인과 완료 뒤 명시적 repo/head/base/draft와 body-file로 생성한다. 기존 인증만 쓰고 token 조회, 로그인 및 scope 확대를 하지 않는다.
- M0 결과: gh가 없는 환경이라 `gh pr create`를 실행하지 못했다. 공식 문서상 `--dry-run`도 push할 수 있고 `--head`를 주면 push와 fork를 건너뛴다. [git-behavior G6](probes/git-behavior.md#g6-push-lease와-gh-pr-create의-push-동작)

### R50 검사 끄기와 성공 gate 및 공개 표시의 충돌

- 대상: 새 checks.enabled 결정, 기존 모든 검사 성공 및 not-checked 차단 규칙.
- 문제: 모든 검사를 성공해야 한다는 규칙을 유지하면 끄기가 작동하지 않고, 미실행을 성공으로 바꾸면 검증 사실을 왜곡한다.
- 근거: 사용자 결정과 기존 01-plan 및 03 gate의 직접 모순.
- 심각도: 높음.
- 반영: 기본 flow의 not-run-disabled와 completed-unchecked를 분리했다. reviewer의 검토 완료는 유지하고 실행 증거 부재는 별도 기록한다. 결과와 commit 및 push 확인, PR에 검사 미실행을 표시한다. tester flow의 끄기는 거부한다.

### R51 P0부터 P5까지의 등급 경계와 판정 일관성

- 대상: pipeline.block_up_to, 03 severity와 정의.
- 문제: 여섯 등급은 CLI의 공통 표준이 아니고 같은 결함의 등급 차이가 차단 여부를 바꿀 수 있다.
- 근거: 사용자 결정이 등급 수와 차단 범위를 정했지만 상호 일관성 자료는 없다.
- 심각도: 중간.
- 반영: 현재 원문 :17의 P0부터 P5까지 정의를 적용했다. 차단 기준과 취향 제외는 유지하며 이전 임의 영향 및 우회 기준을 사용자 결정으로 유지하지 않는다.
- 상태: 2026-11-17 결정 반영.

### R52 registry 모델 존재와 설치 및 계정 지원의 차이

- 대상: 결정된 모델 8개와 02 provider registry.
- 문제: 전체 ID의 문서 및 catalog 존재는 계정 접근이나 실제 실행을 보장하지 않는다. Fable은 설치된 Claude 버전이 부족하다.
- 근거: Claude 2.1.316, Codex 내장 catalog, [Claude 목록](https://platform.claude.com/docs/en/models/overview), [모델 설정](https://code.claude.com/docs/en/model-config), [Codex Models](https://learn.chatgpt.com/docs/models).
- 심각도: 중간.
- 반영: doctor가 모델별 최소 CLI 버전을 검사하고 미달 agent를 failed-version-check로 처리한다. Fable 최소 2.1.321보다 낮은 설치 2.1.316에서 모델 호출하지 않는다. 이 반영은 D14로 바뀌었다.
- 상태: 2026-11-17 결정 반영.
- M0 결과: Claude 2.1.316에서 `claude-fable-5-2` 호출이 성공했다. 결정된 규칙의 전제와 달라 [D14](05-open-decisions.md#d14-fable과-최소-cli-버전-경고)로 정했다. 최소 버전 미달은 경고로 바꾸고 probe 결과로 판정한다. 2.1.321은 CLI가 이 ID를 인식하는 첫 버전이다. Codex 모델 4개는 0.167.0-alpha.3.2에서 실행됐다. [claude-headless C1](probes/claude-headless.md#c1-전체-모델-id-4개-지정), [codex-exec X1](probes/codex-exec.md#x1-모델-id-4개-지정)

### R53 결정 원문의 누락과 과거 요약 충돌

- 대상: 현재 docs/decisions.md 결정 기록과 이번 사용자 지시.
- 문제: 원본 01에는 setup 일부와 환경 규칙만 있고 새 전체 결정 및 남은 결정 절이 없다. 과거 다중 배정 요약도 이번 정정과 다르다.
- 근거: 실제로 읽은 원본 :5-12와 전체 78줄, 05-common-docs-review C1, 이번 사용자 메시지의 명시 결정.
- 심각도: 중간.
- 반영: 당시 누락 보고는 이력으로 남긴다. 현재 2026-11-17 원문 :19-28에는 기존 8개 결정과 무변경 및 최소 버전 규칙이 있어 최신 source로 반영했다.
- 상태: 2026-11-17 결정 반영.

### R54 publish 부분 성공과 응답 유실의 재개

- 대상: 새 push 후 Draft PR 흐름, 01-plan publish checkpoint.
- 문제: push 성공 뒤 PR 생성 실패 또는 응답 유실을 전체 실패로 표시하면 이미 공개된 사실을 숨기거나 중복 PR을 만들 수 있다.
- 근거: 두 외부 작업의 독립된 성공 상태에서 도출되는 설계 분석. 실제 실패 fixture는 미확인이다.
- 심각도: 중간.
- 반영: local-committed, pushed, draft-created를 나눠 기록한다. 재개 전 remote SHA와 기존 PR을 확인하며 자동 rollback push와 중복 생성은 하지 않는다.

### R55 무변경 성공에 empty commit을 요구한 판단 철회

- 대상: 이전 D03과 R55의 empty commit 기술, 원문 01-overview.md:27.
- 문제: 원문의 “항상 commit”을 무변경까지 확장 해석해 구현 선택을 사용자 결정처럼 기록했다.
- 근거: 당시 원문에 empty commit 결정은 없었으며 2026-11-17 원문은 무변경 성공의 commit과 push 생략을 명시한다.
- 심각도: 낮음.
- 상태: 철회. 발견 당시 분류만 이력에 보존한다.
- 반영: empty commit 규칙을 삭제하고 성공한 Git 결과 tree가 base와 같으면 “변경 없음”으로 종료한다. 경위와 추가 영향은 R66에 기록한다.

## 3차 검토 반영

기준일: 2026-11-17. 원문 결정 기록 :19-28을 모두 읽고 기존 남은 8개를 반영했다. 원문에 없는 기본값은 제안으로 분리했다. R55는 원문 없는 결정을 만들어 낸 판단으로 철회했으며 R66에 경위를 기록한다. R03의 철회도 유지한다.

### 3차 사실 확인

| 항목 | 확인 결과 | 확인하지 않은 범위 |
|---|---|---|
| 원문 | 2026-11-17 D01, D05부터 D11까지, 무변경 및 최소 CLI 규칙을 확인 | 원문 변경 없음 |
| Claude | claude --version은 2.1.316. 공식 model-config의 Fable 최소 2.1.321 재확인 | 모델 probe와 업데이트 없음 |
| Node와 npm | node --version v24.14.0, 실제 npm-cli.js와 npx-cli.js를 node로 --version 실행해 각각 11.9.0 | install과 prepare 및 check는 실행하지 않음 |
| JS 경로 | 현재 node_modules/npm/bin 진입점과 npm bin 선언, npm launcher의 prefix 탐색 확인 | 다른 version manager와 Corepack의 실제 resolver 미확인 |
| 환경 탐색 | 이 PATH에서 nvm, fnm, volta, nodist 명령을 발견하지 못함. corepack.cmd는 발견 | 미설치 증명이나 Corepack 다운로드 시험이 아님 |
| 공식 자료 | uv와 npm 설치 동작, Git hooks 및 signing, cmd와 wrapper 동작 확인 | 준비, 서명과 Git mutation 없음 |

이번 문서 작업에서 doctor의 실제 custom 명령 시험과 prepare, 모델 실행, commit과 push는 수행하지 않았다.

### R56 prepare 네트워크 허용과 검사 차단의 범위

- 대상: 원문 :25, 01-plan prepare, 02 network.
- 문제: 준비 허용을 check와 그 자식에게 상속하거나 AI 서비스 및 Git 공개 통신과 혼동하면 검사 중 다운로드가 발생하거나 필요한 기능 전체가 막힌다.
- 근거: 원문 :25의 단계 구분과 기존 공식 CLI 및 공개 흐름의 동시 요구.
- 심각도: 높음.
- 반영: 프로젝트 의존성 네트워크는 prepare만 allowed, check와 check-probe는 blocked로 분리했다. 공식 AI 및 확인 후 Git 통신은 기능별로 구분하고 실제 적용은 미확인으로 둔다.

### R57 prepare install script와 source 변경의 부작용

- 대상: 원문 :25, 02 prepare와 03 시스템 기록.
- 문제: 등록 설치 명령은 파일 다운로드만 수행하지 않으며 install script가 source와 lock 및 외부 환경에 영향을 줄 수 있다.
- 근거: [npm lifecycle](https://docs.npmjs.com/cli/v11/using-npm/scripts/), [uv lock 및 sync](https://docs.astral.sh/uv/concepts/projects/sync/).
- 심각도: 높음.
- 반영: 정상 script 실행을 일괄 끄는 새 결정을 만들지 않았다. source와 lock 전후 및 의존성 산출물을 나누어 감사하고 변화를 baseline에 묻지 않는다. 악의적 script 방어는 보장하지 않는다.
- M0 결과: `npm ci`가 루트 `preinstall`, `postinstall`, `prepare`를 실행했고 script가 source를 바꾸고 새 파일을 만들었다(exit 0, lock은 그대로). 의존성 패키지의 script와 uv의 build backend 변경은 시험하지 않았다. [prepare-behavior](probes/prepare-behavior.md#install-script가-source를-바꾸는지)

### R58 lock 부재와 자동 생성 및 갱신의 미결정

- 대상: 원문 :25, 새 D12.
- 문제: npm ci에는 lock이 필요하고 uv sync는 lock을 만들거나 갱신할 수 있는데 그 허용 여부는 원문에 없다.
- 근거: [npm ci 조건](https://docs.npmjs.com/cli/v11/commands/npm-ci/), [uv sync](https://docs.astral.sh/uv/concepts/projects/sync/).
- 심각도: 중간.
- 반영: 해결: D12 확정. 기존 lock을 유지하고 부재와 manifest 불일치, run 안 lock 변경에서 중단한다. doctor가 run 밖 lock 생성을 안내한다.
- 상태: 사용자 결정 반영으로 해결.
- M0 결과: `uv sync`는 lock 부재에서 lock을 만들고 불일치에서 lock을 고친 뒤 exit 0이었다. `uv sync --frozen`은 불일치를 알리지 않고 성공했다. `npm ci`는 부재와 불일치에서 `EUSAGE`로 실패했다. [D16](05-open-decisions.md#d16-lock-일치-사전-확인)에 따라 등록 명령 전에 `uv lock --check`로 확인한다. 이 명령은 부재 exit 2, 불일치 exit 1이고 lock을 바꾸지 않았다. [prepare-behavior](probes/prepare-behavior.md#lock-부재와-불일치-때의-동작)

### R59 prepare 실패와 부분 의존성 상태의 재사용

- 대상: 01-plan prepare-failed, 02 prepare 명령 실행.
- 문제: 설치 도중 실패한 환경을 준비 완료로 사용하거나 실패 명령을 다른 설치로 바꾸면 실행 기준이 달라진다.
- 근거: [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/)의 기존 node_modules 제거와 [npm scripts 종료](https://docs.npmjs.com/cli/v11/using-npm/scripts/#exiting).
- 심각도: 중간.
- 반영: 첫 실패와 timeout 및 취소에서 멈추고 부분 상태를 보존한다. planner로 가지 않으며 자동 정리와 재시도 및 명령 대체를 하지 않는다.
- M0 결과: `npm ci`는 루트 `postinstall` 실패(exit 7)에도 `node_modules`를 설치된 채 남겼고, 실행할 때마다 기존 `node_modules`를 지웠다. `uv sync`는 build 실패와 `--locked` 실패에서 빈 `.venv`를 남겼다. 폴더 존재로 준비 완료를 판정할 수 없다. [prepare-behavior](probes/prepare-behavior.md#실패-뒤-부분-환경)

### R60 prepare 로그가 역할과 검사 결과로 혼입

- 대상: 원문 tester :15, 03 source와 prepare 및 check 입력.
- 문제: 설치 로그의 문구를 역할 지시나 검사 성공 증거로 넘기면 의미가 뒤섞이고 tester의 plan과 diff 제한도 깨진다.
- 근거: 원문 tester 입력 제한과 실제 prepare/check 단계의 구분. 악성 문자열 방어는 trusted-local의 보장 대상이 아니다.
- 심각도: 높음.
- 반영: 운영 로그와 검증된 준비 상태를 분리했다. tester에는 전달하지 않고 모델 결과와 시스템 관측 Schema를 구분한다. prepare 성공과 doctor 관측은 실제 run check를 대체하지 못한다.

### R61 trusted-local 보장 범위의 사용자 오해

- 대상: 원문 :20, 01-plan 한계 표시, 05 D06.
- 문제: 사후 탐지와 중단을 악의적 저장소에 대한 사전 차단으로 설명하거나 untrusted의 완료 조건을 계속 강제할 수 있다.
- 근거: 원문 :20과 이번 지시의 test_paths 사후 탐지 완료 조건.
- 심각도: 중간.
- 반영: setup과 doctor, run 시작과 최종 결과에 trusted-local 및 보장 제외를 표시한다. OS 격리와 prompt injection 방어는 이후 검토로 옮겼다.

### R62 평소 hooks의 파일 변경과 검토 상태 불일치

- 대상: 원문 :26, 01-plan hooks 및 commit, 03 인계.
- 문제: pre-commit이 stage를 바꾸거나 post-commit이 source를 바꾸면 gate를 통과한 내용과 실제 결과가 달라진다. post-commit 뒤에는 commit이 이미 존재할 수 있다.
- 근거: [Git hooks](https://git-scm.com/docs/githooks), [post-commit](https://git-scm.com/docs/githooks#_post_commit), [post-checkout](https://git-scm.com/docs/githooks#_post_checkout).
- 심각도: 높음.
- 반영: hooks는 평소 실행한다. expected tree와 raw source를 재확인하고 다르면 기존 결과를 무효화한다. 이미 생긴 commit은 SHA와 committed-unverified를 보존하고 publish를 막으며 reset과 amend하지 않는다.
- M0 결과: pre-commit이 다시 stage하면 `git write-tree`와 `HEAD^{tree}`가 달랐다. stage 밖 변경과 post-commit 변경은 tree가 같고 `git status`에만 나왔다. commit-msg hook은 commit 메시지를 바꿀 수 있었다. 메시지 확인 여부는 문서에 없다. [git-behavior G3](probes/git-behavior.md#g3-hook의-파일-변경과-tree-불일치-탐지)

### R63 npm 진입점과 version manager 경로 탐색

- 대상: 원문 :24, 02 Windows 실행 및 doctor.
- 문제: node 옆 npm-cli.js만 정답으로 가정하면 global prefix와 shim 및 Corepack 설치에서 다른 버전을 실행할 수 있다.
- 근거: 로컬 Node v24.14.0 및 직접 npm/npx JS 11.9.0 확인, [npm launcher](https://github.com/npm/cli/blob/latest/bin/npm.cmd), [Corepack](https://github.com/nodejs/corepack).
- 심각도: 중간.
- 반영: 실제 node와 JS 및 버전을 한 조합으로 고정하고 변경 시 재검증한다. nvm use와 자동 설치를 수행하지 않는다. 다른 관리 도구 환경의 resolver는 미확인이다.
- M0 결과: 이 PC의 기본 Node 설치에서 node 옆 `npm-cli.js`, `npx-cli.js` 직접 실행 버전(11.9.0)이 `npm.cmd`, `npx.cmd`와 같았다. nvm, Volta, fnm, Corepack shim 환경은 PC에 없어 확인 불가다. [windows-process W2](probes/windows-process.md#w2-npm과-npx를-node로-직접-실행할-때-경로-탐색)

### R64 doctor 최초 시험 자체의 파일 변경 부작용

- 대상: 원문 :23, 01-plan doctor, 02 직접 입력 시험.
- 문제: 처음 실행해 무변경을 확인하는데 원본 checkout이나 진행 중 run에서 시험하면 탐지 전에 이미 파일을 바꿀 수 있다.
- 근거: 원문이 실제 시험을 요구하지만 장소는 정하지 않은 설계 누락. [Python subprocess](https://docs.python.org/3/library/subprocess.html#security-considerations).
- 심각도: 높음.
- 반영: 별도 고정 HEAD probe worktree에서 prepare 뒤 동일 조건으로 1회 시험하는 구현안을 제안했다. 원본을 시험 대상으로 쓰지 않는다. 별도 worktree가 모든 시스템 외부 부작용을 막는다는 보장은 하지 않는다.

### R65 사람 개입 서명의 완전 사전 판별 한계

- 대상: 원문 :26, git.interactive_signing.
- 문제: 설정에 signing이 있다는 사실만으로 다음 호출의 pinentry와 agent 상태, 사용자 지정 signing program이 무인인지 완전히 알 수 없다.
- 근거: [Git signing 설정](https://git-scm.com/docs/git-config#Documentation/git-config.txt-gpgprogram).
- 심각도: 중간.
- 반영: 사람 개입 필요 또는 무인 준비 미확인 상태에서는 commit 전에 중단한다. 설정을 끄지 않고 예상 밖 prompt와 timeout도 처리한다. 실제 signing 동작은 미확인이다.
- M0 결과: `git config --show-origin --show-scope --get-regexp`로 서명 설정을 탐지할 수 있었다. 실패하는 서명 프로그램과 입력을 기다리는 서명 프로그램 모두 commit 전에 끝나 HEAD가 움직이지 않았다. 실제 gpg와 ssh agent는 시험하지 않았다. [git-behavior G4](probes/git-behavior.md#g4-사람-개입-서명-설정-탐지)

### R66 empty commit을 사용자 결정으로 기록한 오류

- 대상: 이전 05 D03, 01과 03의 무변경 처리, R55.
- 문제: 원문의 “항상 로컬 브랜치에 commit”을 무변경에도 확장 해석하고 empty commit이라는 구현 선택을 사용자 결정과 강제 규칙으로 올렸다.
- 근거: 이전 D03의 “결정대로 empty commit”과 R55 반영에는 원문 근거가 없었다. 현재 원문 01-overview.md:27은 commit과 push 생략을 명시한다.
- 심각도: 높음.
- 반영: 원문 대조 없이 추론을 결정으로 표시한 오류로 기록한다. R55를 철회하고 D03 및 모든 실행 계약에서 empty commit을 제거했다. gate 성공과 Git 결과 무변경이면 no-changes로 종료하고 commit 및 push와 PR을 실행하지 않는다.

### R67 warn-head source와 실행 설정의 출처 혼합

- 대상: 원문 :22,25, 01-plan 입력 기준, 02 control 설정.
- 문제: 원본의 미커밋 source를 제외하면서 현재 setup 설정을 쓴다는 차이를 정의하지 않으면 모델 source에 원본 변경이 섞이거나 prepare 명령이 재로딩될 수 있다.
- 근거: 원문 warn-head와 모델보다 먼저 실행하는 prepare 결정, 기존 config hash 계약.
- 심각도: 높음.
- 반영: source는 고정 OID workspace만 읽고 control 설정과 명령은 별도 사용자 확인 후 hash로 고정한다. 미커밋 설정의 차이는 표시하되 source와 자동 commit 대상으로 섞지 않는다.

### R68 npx와 wrapper의 검사 중 다운로드 및 내부 shell

- 대상: 원문 :24-25, 02 Windows 실행.
- 문제: node로 npm JS를 호출해도 내부 scripts shell은 남는다. npx와 Corepack 및 Gradle/Maven wrapper가 누락 도구를 검사 중 내려받거나 설치할 수 있다.
- 근거: [npm run](https://docs.npmjs.com/cli/v11/commands/npm-run/), [npm exec](https://docs.npmjs.com/cli/v11/commands/npm-exec/), [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html), [Maven Wrapper](https://maven.apache.org/tools/wrapper/).
- 심각도: 높음.
- 반영: outer .cmd 우회와 shell 완전 제거를 구분했다. 필요한 패키지와 배포본은 prepare에서 확보하고 check에서는 누락을 실패로 처리한다. offline 옵션을 cache 설치까지 막는 보장으로 쓰지 않는다.
- M0 결과: 공백 있는 wrapper 경로를 argv로 `cmd /d /s /c`에 넘기면 실행이 실패하고 `&` 인자가 명령으로 실행됐다. 다른 방식에서도 `%VAR%` 확장과 `^` 제거가 남았다. [D15](05-open-decisions.md#d15-cmd-wrapper-허용-조건)에 따라 공백 없는 경로와 특수문자 없는 인자만 허용한다. [windows-process W3](probes/windows-process.md#w3-cmd-d-s-c-wrapper-인자-처리)

### R69 doctor 1회 관측의 재사용 범위

- 대상: 원문 :23, 02 doctor와 03 check-probe.
- 문제: 한 번 종료하고 파일을 바꾸지 않았다고 이후 바뀐 script와 환경에서도 같다고 인증하면 안 된다. 테스트 실패와 실행조차 못한 경우도 다르다.
- 근거: 단일 실행 관측의 범위에 관한 설계 분석. 실제 probe fixture는 수집하지 않았다.
- 심각도: 중간.
- 반영: 명령과 scripts, 실행 파일 및 버전과 runtime, 설정 및 lock에 결과를 묶고 달라지면 무효화한다. source 관측 범위를 기록하고 매 run check에서 상한 및 감사를 유지한다. 자격 관측과 실제 테스트 결과를 분리한다.

### R70 원문 P0부터 P5까지 정의와 기존 임의 정의 차이

- 대상: 현재 원문 :17, 03 등급 표와 리뷰 예시.
- 문제: 이전 문서의 영향과 우회 중심 세부 기준은 현재 원문 정의와 다르며 완료 조건 실패를 P2로 둔 예시도 맞지 않는다.
- 근거: 원문 :17은 P0 보안 및 손실, P1 주된 기능 및 완료 조건, P2 특정 조건 및 테스트 부재, P3 작은 영향, P4 유지보수, P5 사소한 것으로 정했다.
- 심각도: 낮음.
- 반영: 원문 정의로 표를 바꾸고 완료 조건 미충족 예시를 P1로 고쳤다. 여러 조건의 상향 처리 같은 추가 규칙은 제안으로 표시한다.

### R71 구현 중 의존성 입력 변경과 재준비

- 대상: 원문 :25, 새 D13.
- 문제: 최초 prepare 뒤 manifest와 lock이 바뀌면 설치 환경과 코드가 달라진다. 원문은 이때 같은 run의 재준비와 추가 네트워크 승인을 정하지 않았다.
- 근거: prepare 위치와 check 네트워크 차단, dependency 입력 변화의 설계상 관계.
- 심각도: 중간.
- 반영: 해결: D13 확정. 자동 재준비하지 않는다. 계획에 새 의존성 필요 여부를 표시하고 사람이 먼저 추가 후 재시작하며 계획 밖 manifest 및 lock 변경은 중단한다.
- 상태: 사용자 결정 반영으로 해결.

## 미확인 사실과 확인 방법

기존 확인 과제는 남겨 두되 trusted-local 결정으로 MVP 밖에 둔 사전 격리와 현재 필요한 운영 확인을 구분한다. M0 결과 열은 [docs/probes/](probes/README.md)의 확인 실험 결과다. 실행 환경은 #3, #4, #5가 Windows 11, #6이 Linux VM, #7이 Linux 컨테이너다.

| ID | 미확인 사실 | 확인 방법과 범위 | M0 결과 |
|---|---|---|---|
| U01 | 계정별 모델 제공과 실효 effort, protocol v2 Schema의 실제 CLI 수락 | 선택 agent의 사용량 probe. 최소 버전 미달은 경고 뒤 probe로 판정(D14) | 일부 확인. Claude 모델 4개와 Codex 모델 4개가 실행됐다. Fable은 최소 버전 미달에서도 실행돼 D14로 정했다. 공통 Schema는 Claude haiku와 Codex `gpt-6-astra`에서 수락됐다. 실효 effort는 두 CLI 모두 출력이 없어 미확인 |
| U02 | 한도 오류와 잔량 및 reset 시각, CLI turn과 비용 상한 | 실제 오류 fixture. 추정값을 채우지 않음 | 인증 오류 형태는 확인. 한도 오류와 잔량, turn과 비용 상한은 확인 불가 |
| U03 | native와 WSL2의 취소 및 자식 종료, 경로와 인코딩, 디스크 비용 | runtime별 실제 실행 시험 | native는 확인. 손자 프로세스 종료 방식별 결과, 출력 인코딩이 자식마다 다름(Python cp949, node와 git UTF-8). WSL2와 디스크 비용은 미확인 |
| U04 | prepare 성공과 실패, install script 및 lock 변화, 부분 환경 재개 | 일회용 workspace에서 source와 lock 및 환경 전후 기록 | Linux에서 확인. lock 생성과 수정, 실패 뒤 부분 환경, 루트 lifecycle script의 source 변경. Windows 실행은 미확인 |
| U05 | check 및 check-probe의 실제 네트워크 차단과 파일 감사 | 실제 프로젝트 명령의 별도 probe. 악의적 외부 부작용 전체 방어는 보장 밖 | 차단 방식 후보는 #30에서 확인([check-network-block](probes/check-network-block.md)). 프록시 환경 변수와 offline 설정은 도구별로 듣고 직접 소켓은 못 막음. AppContainer는 관리자 없이 손자까지 막지만 사용자 설치 Python이 시작되지 않음. Firewall은 관리자 필요. 방식은 D17로 남김. 실제 프로젝트 검사와 파일 감사는 미확인 |
| U06 | nvm 등 관리 도구와 Corepack의 npm JS resolver, wrapper quoting과 취소 | 해당 환경에서 직접 경로와 버전 고정 및 fixture 시험 | 기본 Node 설치의 npm JS 진입점은 확인. version manager와 Corepack shim은 확인 불가. wrapper는 D15의 허용 조건으로 정함 |
| U07 | 실제 signing 프로그램과 agent의 무인 상태, hooks와 filters의 실제 변경 | 개인 설정과 실행 시험은 이번에 하지 않음. commit 전 준비 확인 및 tree 비교 필요 | hooks의 실행과 tree, status, 메시지 변경은 확인. 서명은 설정 탐지와 가짜 프로그램 실패만 확인. 실제 signing agent와 filters는 미확인 |
| U08 | 준비 로그 분리와 환경 재현, custom 명령 시험 결과의 재사용 | prepare/check/check-probe record와 role 입력 fixture | 이번 M0에서 시험하지 않음 |
| U09 | 제한 입력 tester 품질과 다양성 효과, P0부터 P5까지의 판정 일관성 | 고정 작업과 사람 판정 실험 | 이번 M0에서 시험하지 않음 |
| U10 | 사용자 Git identity와 gh 인증 및 remote 공개 범위, commit/publish의 성공과 실패 재개 | 읽기 확인과 별도 end-to-end. 이번 작업에서 mutation 없음 | 생성 전용 push lease는 로컬 bare remote에서 확인. gh 인증과 실제 PR 생성, 재개는 미확인 |
| U11 | 재배포 및 서비스화 조건과 선행 운영 사례 전체 | 본인 로컬 범위 밖 조건과 원본 로그가 필요 | 해당 없음 |
| U12 | Codex 실행 파일의 발견 위치와 버전 고정 | doctor가 PATH 밖 설치를 어떻게 찾고 어느 실행 파일을 고정할지 시험 | M0에서 새로 생김. PATH에 `codex`가 없었고 Codex 앱 폴더의 `codex.exe`(0.167.0-alpha.3.2)를 썼다. 기존 기록은 0.169.0-alpha.11.1 |
| U13 | Codex sandbox에서 역할 명령의 작업 폴더 | sandbox 모드별로 상대 경로 명령의 실행 위치 확인 | M0에서 새로 생김. read-only에서 작업 폴더가 `-C`와 달랐고 `CreateProcessWithLogonW failed: 267`이 있었다. workspace-write는 미확인 |
| U14 | 비대화형 실행에 노출되는 사용자 MCP 도구와 skills | Claude의 도구 목록과 Codex의 skills 적용 범위를 출력이나 설정으로 확인 | M0에서 새로 생김. Claude 응답이 MCP 도구를 언급했고 Codex는 `.agents\skills`를 읽었다 |

권한 profile의 사전 경로 차단과 악의적 controller 및 credential 접근 방어는 이번 MVP 완료 조건이 아니라 이후 검토 대상이다.

## 산출물 점검 상태

Python 3.13.15의 tomllib과 json으로 TOML 블록 6개와 JSON 블록 7개를 파싱했다. JSON은 registry 1개, 역할 및 handoff와 시스템 기록 Schema 3개, 역할 결과 예시 3개다. 모든 객체의 additionalProperties=false와 전체 property required, 내부 기록의 nullable exit_code를 포함한 사용 부분집합을 재귀 검사했다. 역할 예시 3개도 Schema 부분집합 검사를 통과했다.

프리셋 3종의 모델 8개와 agent 참조, prepare 및 checks 교체 예시를 검사했다. tester flow의 검사 off 거부와 기본 flow의 off 허용, prepare allowed와 checks blocked, trusted-local 고정, empty commit과 hooks skip 거부, custom doctor-once 강제, 복수 coder 거부 및 Fable 2.1.316의 최소 버전 미달을 문서 조건으로 확인했다. 제품 구현 테스트와 실제 agent probe는 아니다.

상대 링크와 내부 anchor 74개, UTF-8과 BOM 부재, 금지 문자와 R01부터 R71까지 번호 및 집계, 결정 D01부터 D11까지와 신규 D12 및 D13을 점검했다. 오류는 없었다. 원문 5개의 SHA-256은 이번 작업 시작 때와 같다. 산출물 수정은 common-docs의 6개다.

jsonschema 라이브러리가 설치돼 있지 않아 별도 meta-schema 검증은 실행하지 않았다. 이번 작업에서 prepare와 custom check 시험, 모델 호출, 실제 signing과 commit 및 push의 end-to-end 검사도 실행하지 않았다. 새 미확인은 위 목록에 남긴다.
