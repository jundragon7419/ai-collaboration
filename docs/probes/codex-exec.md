# Codex exec 호출 확인 결과

이슈 #4의 확인 결과다. 대상은 native Windows sandbox의 read-only와 workspace-write 실제 차단, `-a never`, `--output-schema` 엄격 규칙, `-o`, `--json` 이벤트, 모델 ID 4개와 effort 값 이름, `--ephemeral`이다.

## 실행 환경

| 항목 | 값 |
|---|---|
| 실행일 | 2026-11-17 |
| OS | Windows 11 (10.0.26200), 사용자 PC |
| Codex CLI | `codex-cli 0.167.0-alpha.3.2` |
| 실행 파일 | Codex 앱이 풀어 둔 `%LOCALAPPDATA%\OpenAI\Codex\bin\<hash>\codex.exe` |
| Python | 3.13.15 |
| 실행 명령 | `python scripts/probes/codex_exec.py --codex <codex.exe 경로> --out <출력 폴더>` (저장소 루트에서 실행) |

- `codex`는 PATH에 없었다. PowerShell의 `Get-Command codex`도 찾지 못했다. Codex 앱 패키지 안 `C:\Program Files\WindowsApps\OpenAI.Codex_<버전>\app\resources\codex.exe`도 있었지만 `--version` 출력이 비어 있어 쓰지 않았다.
- 기존 기록의 Codex CLI는 `0.169.0-alpha.11.1`([04-review C05](../04-review.md#명령-실행-기록))이었다. 이번에 쓴 실행 파일과 버전이 다르다. 어느 경로에서 실행했는지에 따라 버전이 달라질 수 있다.

모든 호출의 기본 형태는 다음과 같다. prompt는 stdin으로 넘겼다. 작업 폴더는 임시 디렉터리다. 상속 `GIT_*` 환경 변수는 빼고 실행했다. 인증 파일은 읽지 않았다.

```shell
codex -a never --sandbox <mode> exec --skip-git-repo-check -C <작업 폴더> --ephemeral -m <모델> --json -o <파일> -
```

관찰 원본은 [fixtures/codex-exec/](fixtures/codex-exec/)에 있다. `windows-codex-0.167.0-alpha.3.2.json`이 전체 요약이고, 나머지 파일은 사례별 JSONL 이벤트와 stderr다. 홈 경로는 `<HOME>`, 사용자 이름은 `<USER>`, 임시 폴더 이름은 `<RAND>`, thread_id는 `<UUID>`, request id와 cf-ray는 `<ID>`, `<RAY>`로 바꿨다.

## 결과 요약

| ID | 항목 | 결론 |
|---|---|---|
| X1 | 모델 ID 4개 지정 | 확인됨. 실제 사용 모델은 출력에 없어 미확인 |
| X2 | sandbox read-only와 workspace-write, `-a never` | 쓰기 차단은 확인됨. read-only에서 명령 작업 폴더가 `-C`와 달랐음 |
| X3 | `--output-schema` 엄격 규칙과 `-o` | 확인됨 |
| X4 | `--json` 이벤트 | 확인됨. 명령 출력의 한글이 깨짐 |
| X5 | effort 값 이름 | 확인됨. 모델별로 지원 값이 다름 |
| X6 | `--ephemeral` | 확인됨 |
| X7 | 인증 오류 출력 형태 | 확인됨. 한도 오류는 확인 불가 |

## 공통 출력 형태

- stdout은 `--json`일 때 한 줄에 JSON 이벤트 한 개다. JSON이 아닌 stdout 줄은 없었다.
- 이벤트 `type`은 `thread.started`(`thread_id`), `turn.started`, `item.started`, `item.completed`(`item`), `turn.completed`(`usage`), `error`(`message`), `turn.failed`(`error.message`)가 나왔다.
- `item.type`은 `agent_message`(`text`)와 `command_execution`(`command`, `aggregated_output`, `exit_code`, `status`)이 나왔다.
- 성공한 turn은 exit 0이고 마지막 이벤트가 `turn.completed`다. 실패한 turn은 exit 1이고 마지막 이벤트가 `turn.failed`다.
- `-o` 파일에는 마지막 `agent_message`의 `text`가 그대로 들어간다. 실패한 turn에서는 파일이 만들어지지 않았다.
- 모든 호출의 stderr에 `failed to load skill <HOME>\.agents\skills\claude-md-conventions\SKILL.md: missing YAML frontmatter delimited by ---`가 있었다. `codex exec`가 사용자 홈의 skills를 읽는다는 뜻이다. 이 오류는 실행 결과에 영향을 주지 않았다.

## X1 모델 ID 4개 지정

명령: 기본 형태에 `--sandbox read-only -m <ID>`, prompt `Reply with exactly: OK`

| 모델 ID | exit | 마지막 이벤트 | `-o` 내용 |
|---|---|---|---|
| `gpt-6-astra` | 0 | `turn.completed` | `OK` |
| `gpt-6.1-sol` | 0 | `turn.completed` | `OK` |
| `gpt-6.1-terra` | 0 | `turn.completed` | `OK` |
| `gpt-6-luna` | 0 | `turn.completed` | `OK` |
| `gpt-probe-nonexistent-0` | 1 | `turn.failed` | 없음 |

- 없는 모델은 `error` 이벤트와 `turn.failed`에 `The 'gpt-probe-nonexistent-0' model is not supported when using Codex with a ChatGPT account.`가 나왔다.
- 이벤트에는 실제 사용된 모델 이름이 나오지 않는다. 없는 ID는 거부되므로 지정한 ID로 요청한 것은 맞지만, 서버가 그 모델로 응답했는지는 출력으로 확인할 수 없다.

결론: 확인됨. registry의 Codex 모델 4개가 이 계정과 CLI 버전에서 실행됐다. [02-config-spec provider registry](../02-config-spec.md#provider-registry와-최소-버전)의 Codex 최소 CLI 버전은 계속 미확인이다. 이번 결과는 0.167.0-alpha.3.2에서 실행된다는 것만 보여 준다.

## X2 sandbox read-only와 workspace-write, `-a never`

방법: prompt로 작업 폴더 안 파일과 작업 폴더 밖 파일을 셸 명령으로 만들게 했다. 바깥 대상은 임시 폴더가 아닌 결과 폴더(`<결과 폴더>`)에 두었다. 임시 폴더는 쓰기 허용 경로에 들어갈 수 있어서다. 파일 존재 여부는 스크립트가 직접 확인했다.

| sandbox | exit | 작업 폴더 안 | 작업 폴더 밖 | 걸린 시간 |
|---|---|---|---|---|
| `read-only` | 0 | 안 만들어짐 | 안 만들어짐 | 50.1초 |
| `workspace-write` | 0 | 만들어짐 | 안 만들어짐 | 39.8초 |

- read-only의 명령은 PowerShell `Set-Content`가 `UnauthorizedAccessException`(접근 거부)으로 실패했다. workspace-write의 밖 경로도 같은 이유로 실패했다. 모델이 요청한 명령 자체는 실행됐고 OS 접근 제어에서 막혔다.
- `-a never`에서 승인 대기로 멈춘 호출은 없었다. 실패한 명령은 `command_execution`의 `exit_code`가 1로 기록되고 turn은 계속 진행됐다. 거부돼도 exit 0이므로 차단 여부는 사후 파일 감사로 확인해야 한다.
- read-only에서 처음 두 명령은 `exit_code` -1, `aggregated_output`이 `Failed to create unified exec process: CreateProcessWithLogonW failed: 267`이었다. stderr에도 같은 오류가 기록됐다. Windows 오류 267은 디렉터리 이름이 잘못됐다는 뜻이다. 모델이 다시 시도한 명령은 실행됐다.
- read-only로 실행한 X4에서, 경로 없이 실행한 `Get-ChildItem -File -Force -Name`은 작업 폴더가 아니라 `C:\` 루트의 파일(`hiberfil.sys`, `pagefile.sys` 등)을 나열했다. 이 경우 명령 작업 폴더가 `-C`로 준 폴더와 달랐다. workspace-write에서는 모델이 절대 경로만 써서 작업 폴더를 확인하지 못했다.

결론: 쓰기 차단은 확인됨. [R06](../04-review.md#r06-windows의-두-provider가-같은-sandbox를-제공한다는-전제)이 확인 대상으로 둔 native Windows sandbox가 이번 경우에서 작업 폴더 밖 쓰기를 막았다. read-only sandbox에서 명령 작업 폴더가 `-C`와 다르게 잡힌 점은 문서에 없는 사항이다. 상대 경로를 쓰는 역할 명령은 다른 폴더에서 실행될 수 있다.

## X3 `--output-schema` 엄격 규칙과 `-o`

| 경우 | Schema | exit | 결과 |
|---|---|---|---|
| 공통 role-result | [03-roles-and-handoff](../03-roles-and-handoff.md#공통-role-result-json-schema)의 Schema 원문 | 0 | `-o`에 JSON 저장. 로컬 부분집합 검사 오류 0건 |
| required 누락 | `properties`에 `extra`가 있는데 `required`에 없음 | 1 | `turn.failed`. 파일 없음 |
| 확장 키워드 | `pattern`, `minLength`, `maxLength`, `format: email`, `type: ["string","null"]` | 0 | `{"code":"ABC","email":"probe@example.com","note":null}` |

- required 누락의 오류는 API 응답이 그대로 나왔다: `Invalid schema for response_format 'codex_output_schema': 'schema.required' is required to include every key in properties. Missing 'extra'.`, `"code":"invalid_json_schema"`, `"status":400`. 모델 응답 전에 거부됐다.
- 확장 키워드 Schema는 거부되지 않았다. 출력이 조건을 만족했지만 서버가 `pattern`, `format`을 실제로 강제하는지는 위반을 유도하지 않아 미확인이다.

결론: 확인됨. 모든 property를 required로 두는 공통 Schema 규칙은 Codex 쪽에서 필수다. 공통 role-result Schema는 Claude(#3)와 Codex 양쪽에서 수락됐다. [R13](../04-review.md#r13-두-cli의-구조화-출력-수락-절차가-불충분), [R14](../04-review.md#r14-공통-schema-제한과-지원-모델-범위를-단정할-수-없음)의 공통 수락은 이 Schema와 `gpt-6-astra`, Claude haiku 조합에서 확인했다.

## X4 `--json` 이벤트

prompt `List the files in the current directory, then reply DONE.`의 이벤트 순서는 `thread.started`, `turn.started`, `item.completed`(agent_message), 명령 3개의 `item.started`와 `item.completed`(command_execution), `item.completed`(agent_message), `turn.completed`였다.

- `command_execution.command`는 `"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" -Command '...'` 형태였다. 명령은 PowerShell로 실행됐다.
- `turn.completed.usage`는 `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`를 담았다. 비용 필드는 없었다.
- X2의 `aggregated_output`에서 PowerShell의 한국어 오류 메시지가 대체 문자(U+FFFD)로 깨져 있었다. 명령 출력 인코딩(cp949)이 UTF-8 이벤트로 옮겨질 때 손실된 것으로 보인다. 원래 문자는 복구할 수 없다.

결론: 확인됨. 단계 판정에 쓸 수 있는 구조화 필드는 이벤트 `type`, `command_execution.exit_code`, `turn.failed.error.message`다. 명령 출력 문자열은 한글이 손실될 수 있어 판정 근거로 쓰기 어렵다.

## X5 effort 값 이름

모델 `gpt-6-astra`에 `-c model_reasoning_effort="<값>"`을 주었다.

| 값 | exit | 결과 |
|---|---|---|
| `low`, `medium`, `high`, `xhigh` | 0 | `turn.completed` |
| `minimal` | 1 | `Unsupported value: 'minimal' is not supported with the 'gpt-6-astra' model. Supported values are: 'low', 'medium', 'high', 'xhigh', and 'max'.` |
| `bogus-effort` | 1 | `Invalid value: 'bogus-effort'. Supported values are: 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', and 'max'.` |

- 오류는 모두 `turn.failed`로 끝나고 `"status":400`, `"type":"invalid_request_error"`가 함께 나왔다. CLI가 아니라 API가 값을 검사했다.
- API의 전체 값 목록은 `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`다. `gpt-6-astra`가 지원하는 값은 `low`, `medium`, `high`, `xhigh`, `max`다. `max`와 `none`은 이번에 직접 호출하지 않았다.
- 다른 모델 3개의 effort 지원 값은 시험하지 않았다.

결론: 확인됨. `xhigh`는 유효한 값 이름이다. Claude의 `--effort`(#3)는 알 수 없는 값을 무시하고 진행했지만 Codex는 호출을 실패시켰다. 모델마다 지원 값이 다르므로 effort 검증은 모델 단위로 해야 한다. 실효값은 이벤트에 나오지 않아 미확인이다.

## X6 `--ephemeral`

방법: `CODEX_HOME`(기본 `<HOME>\.codex`) 아래 `sessions` 폴더의 파일 수를 호출 전후로 셌다. 파일 내용은 읽지 않았다.

| 옵션 | 전 | 후 |
|---|---|---|
| `--ephemeral` | 18 | 18 |
| 없음 | 18 | 19 |

결론: 확인됨. `--ephemeral`이면 세션 파일이 늘지 않았다. 같은 시간에 다른 Codex 세션을 쓰지 않았다는 전제의 관찰이다.

## X7 인증 오류 출력 형태

방법: `CODEX_HOME`을 빈 임시 폴더로 바꾸고 `OPENAI_API_KEY`, `CODEX_API_KEY`, `OPENAI_BASE_URL`을 뺐다.

- exit 1, 16.8초. 이벤트는 `error`가 10개, 마지막이 `turn.failed`였다.
- `error.message`는 `Reconnecting... 2/5 (unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: wss://api.openai.com/v1/responses, ...)`처럼 재연결 시도를 하나씩 기록했다. WebSocket(`wss://`) 재시도 `2/5`부터 `5/5`까지 4개, HTTPS 재시도 `1/5`부터 `5/5`까지 5개, 마지막 실패 1개다.
- `turn.failed.error.message`는 `unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: https://api.openai.com/v1/responses, ...`다.
- stderr에 `WARNING: proceeding, even though we could not create PATH aliases: Refusing to create helper binaries under temporary dir`가 있었다. `CODEX_HOME`이 임시 폴더라서 나온 경고다.
- 한도 오류: 확인 불가. 일부러 한도를 소진하지 않았고 실행 중 발생하지 않았다.

결론: 확인됨. 인증 없음은 즉시 실패하지 않고 재시도한 뒤 실패한다. 실패 원인은 `turn.failed.error.message`의 401 문자열로만 알 수 있다. 구조화된 오류 코드 필드는 없었다.

## 문서와 다른 점, 문서에 없는 점

- PATH에 `codex`가 없었다. 실행 파일은 Codex 앱 폴더에 있었고, 위치에 따라 버전이 달랐다(기존 기록 0.169.0-alpha.11.1, 이번 0.167.0-alpha.3.2).
- read-only sandbox에서 명령 작업 폴더가 `-C`와 달랐고, 처음 명령이 `CreateProcessWithLogonW failed: 267`로 실패했다.
- `codex exec`가 사용자 홈의 skills를 읽는다.
- 명령 출력의 한글이 이벤트에서 손실된다.
- effort 지원 값이 모델마다 다르고, 지원하지 않는 값은 호출 실패다.
- 인증 오류는 재시도 뒤 실패하며 구조화된 오류 코드가 없다.

이 내용을 기획 문서와 결정에 반영할지는 #8에서 정한다.

## 남은 미확인

- 한도 오류의 출력 형태
- workspace-write에서 명령 작업 폴더
- `--output-schema`의 `pattern`, `format` 위반 처리
- `gpt-6-astra` 밖 모델의 effort 지원 값, `max`와 `none` 호출
- 실제 사용 모델과 실효 effort
- Codex 최소 CLI 버전
