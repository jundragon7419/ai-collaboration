# Claude Code 비대화형 호출 확인 결과

이슈 #3의 확인 결과다. 대상은 전체 모델 ID 4개 지정, `--tools`로 쓰기 도구와 Bash를 뺐을 때의 실제 차단, `--json-schema` 출력과 공통 Schema 수락, 한도와 인증 오류 출력 형태, `--effort` 값이다.

## 실행 환경

| 항목 | 값 |
|---|---|
| 실행일 | 2026-11-17 |
| OS | Windows 11 (10.0.26200), 사용자 PC |
| Claude Code | `2.1.316 (Claude Code)`, 사용자 로컬 bin의 `claude.exe` |
| Python | 3.13.15 |
| 실행 명령 | `python scripts/probes/claude_headless.py --out <출력 폴더>` (저장소 루트에서 실행) |

모든 호출은 `claude -p --output-format json --no-session-persistence`에 prompt를 stdin으로 넘겼다. 작업 폴더는 임시 디렉터리다. 상속 `GIT_*` 환경 변수는 빼고 실행했다. 인증 파일과 토큰은 읽지 않았다. 호출 1회 비용은 `total_cost_usd` 기준 haiku로 약 0.0025 USD였다.

관찰 원본은 [fixtures/claude-headless/](fixtures/claude-headless/)에 있다. `windows-claude-2.1.316.json`이 전체 요약이고, 나머지 파일은 사례별 stdout JSON과 stderr다. 임시 경로는 `<TMP>`, 홈 경로는 `<HOME>`, session_id와 uuid는 `<UUID>`, tool_use_id는 `toolu_<ID>`로 바꿨다.

## 결과 요약

| ID | 항목 | 결론 |
|---|---|---|
| C1 | 전체 모델 ID 4개 지정 | Opus, Sonnet, Haiku는 확인됨. Fable은 문서와 다름 |
| C2 | `--tools`로 쓰기 도구와 Bash 제외 | 확인됨. 사용자 MCP 도구 노출은 미확인 |
| C3 | `--json-schema` 출력과 Schema 수락 | 확인됨. 확장 키워드의 강제 여부는 미확인 |
| C4 | 한도와 인증 오류 출력 형태 | 인증 오류와 모델 오류는 확인됨. 한도 오류는 확인 불가 |
| C5 | `--effort` 값 | 값 이름은 확인됨. 알 수 없는 값을 거부하지 않음. 실효값은 미확인 |

## 공통 출력 형태

stdout은 JSON 객체 한 개다. 주요 필드는 `type`(`result`), `subtype`, `is_error`, `result`, `structured_output`(Schema를 줬을 때), `permission_denials`, `modelUsage`, `total_cost_usd`, `num_turns`, `stop_reason`, `terminal_reason`, `api_error_status`, `session_id`다.

- 오류에서도 `subtype`은 `success`였다. 성공과 실패는 exit code와 `is_error`, `terminal_reason`으로 구분해야 한다.
- 실제 사용 모델은 `modelUsage`의 키로 나온다. 4개 모델 모두 지정한 ID가 그대로 키로 나왔다.

## C1 전체 모델 ID 4개 지정

명령: `claude -p --output-format json --no-session-persistence --model <ID>`, prompt `Reply with exactly: OK`

| 모델 ID | 문서의 최소 CLI | 설치 버전 충족 | exit | `is_error` | `modelUsage` 키 | stderr |
|---|---|---|---|---|---|---|
| `claude-opus-5-5` | 2.1.280 | 예 | 0 | false | `claude-opus-5-5` | 없음 |
| `claude-fable-5-2` | 2.1.321 | 아니오 | 0 | false | `claude-fable-5-2` | `[claude-code:unrecognized_model] {"model":"claude-fable-5-2","query_source":"sdk"}` |
| `claude-sonnet-5-5` | 2.1.284 | 예 | 0 | false | `claude-sonnet-5-5` | 없음 |
| `claude-haiku-5-5` | 2.1.293 | 예 | 0 | false | `claude-haiku-5-5` | 없음 |
| `claude-probe-nonexistent-0` | 해당 없음 | 해당 없음 | 1 | true | 없음 | `[claude-code:unrecognized_model] {...}` |

결론:

- Opus, Sonnet, Haiku: 확인됨. 전체 ID로 호출되고 그 모델이 쓰였다.
- Fable: 문서와 다름. [02-config-spec provider registry](../02-config-spec.md#provider-registry와-최소-버전)는 설치 2.1.316이 최소 2.1.321에 못 미쳐 "agent probe 실패"로 적었다. 실제로는 같은 2.1.316에서 호출이 성공했고, `modelUsage`에도 `claude-fable-5-2`가 나왔다. CLI는 이 ID를 모르는 모델로 보고 stderr에 `unrecognized_model` 표시를 남긴 채 그대로 요청했다. 문서의 최소 버전(2.1.321)이 무엇을 보장하는지, doctor가 최소 버전 미달이면 호출하지 않는 규칙을 유지할지는 #8에서 정한다. 이번 결과로 규칙을 바꾸지 않는다.
- `unrecognized_model`은 없는 모델에도, 실행되는 Fable에도 똑같이 나온다. 이 표시만으로 모델 사용 가능 여부를 판정할 수 없다.

## C2 `--tools`로 쓰기 도구와 Bash 제외

방법: prompt로 작업 폴더에 파일을 만들라고 하고, 만들 수 없으면 `CANNOT`이라고 답하게 했다. 모델은 haiku를 썼다. 파일 존재 여부는 스크립트가 직접 확인했다.

| 경우 | 옵션 | exit | 파일 생성 | `permission_denials` | 응답 |
|---|---|---|---|---|---|
| 읽기 도구만 | `--tools Read,Glob,Grep` | 0 | 안 됨 | 없음 | `CANNOT` |
| Write 노출, 허용 안 함 | `--tools Read,Glob,Grep,Write` | 0 | 안 됨 | `Write` 1건 | `CANNOT` |
| Bash 노출, 허용 안 함 | `--tools Read,Bash` | 0 | 안 됨 | `Bash` 1건 | 승인이 필요해 막혔다는 설명 |
| 대조군 | `--tools Read,Write --allowedTools Write` | 0 | 됨 | 없음 | 파일을 만들었다는 설명 |

결론: 확인됨. `-p` 실행에서 `--tools`에 없는 도구는 모델이 쓰지 못했고, `--tools`에 있어도 `--allowedTools`로 미리 허용하지 않은 Write와 Bash는 `permission_denials`에 기록되며 거부됐다. 대조군으로 같은 조건에서 허용하면 파일이 만들어지는 것도 확인했다. 거부돼도 exit 0, `is_error` false이므로 거부 여부는 `permission_denials`와 사후 파일 감사로 확인해야 한다. [R04](../04-review.md#r04-도구-제한을-읽기-전용-보장으로-취급)대로 이 결과를 읽기 전용 보장으로 일반화하지 않는다.

미확인: Bash 경우의 응답에서 모델이 Drive와 Docs 같은 MCP 도구를 언급했다. 사용자 설정의 MCP 서버가 `--tools`와 별개로 노출됐을 수 있다. 도움말의 `--tools` 설명은 "built-in set"이라고 적고 있다. 실제 노출된 도구 목록은 이번 출력 형식에 없어 확인하지 못했다. [R05](../04-review.md#r05-비대화형-시작-과정의-hooks와-자동-설정-실행-누락)와 함께 다시 확인해야 한다.

## C3 `--json-schema` 출력과 Schema 수락

| 경우 | Schema | exit | `structured_output` | 로컬 부분집합 검사 |
|---|---|---|---|---|
| 공통 role-result | [03-roles-and-handoff](../03-roles-and-handoff.md#공통-role-result-json-schema)의 Schema 원문 | 0 | 있음 | 오류 0건 |
| 확장 키워드 | `pattern`, `minLength`, `maxLength`, `format: email`, `type: ["string","null"]` 포함 | 0 | `{"code":"ABC","email":"probe@example.com","note":null}` | 해당 없음 |

- 공통 Schema는 그대로 수락됐다. `structured_output`은 Schema의 최상위 필드 10개를 모두 담은 객체였고, 스크립트의 부분집합 검사(type, enum, required, additionalProperties, properties, items)를 통과했다.
- 이때 `result`에는 같은 내용이 JSON 문자열로 들어 있었다. `num_turns`는 2, `stop_reason`은 `tool_use`였다. 구조화 출력은 `result` 문자열이 아니라 `structured_output` 필드에서 읽어야 한다.
- 확장 키워드 Schema도 거부되지 않았다. 출력이 조건을 만족했지만, CLI가 `pattern`과 `format`을 실제로 검사하는지는 위반을 유도하지 않아 미확인이다.

결론: 확인됨. [R13](../04-review.md#r13-두-cli의-구조화-출력-수락-절차가-불충분)의 Claude 쪽 수락은 이 Schema와 haiku 조합에서 확인했다. 다른 모델과 Codex와의 공통 수락은 #4 결과와 함께 본다.

## C4 한도와 인증 오류 출력 형태

| 경우 | 방법 | exit | `is_error` | `subtype` | `terminal_reason` | `api_error_status` | `result` |
|---|---|---|---|---|---|---|---|
| 인증 없음 | `CLAUDE_CONFIG_DIR`을 빈 임시 폴더로, 인증 환경 변수 제거 | 1 | true | `success` | `api_error` | null | `Not logged in · Please run /login` |
| 없는 모델 | `--model claude-probe-nonexistent-0` | 1 | true | `success` | `api_error` | 404 | `There's an issue with the selected model (...)` |

- 두 경우 모두 stdout은 JSON 한 개로 나왔고 stderr로 실패 원인을 알 수는 없었다(없는 모델은 `unrecognized_model` 표시만 있음).
- 인증 없음과 없는 모델은 `api_error_status`(null과 404)와 `result` 문장으로만 구분됐다. 판정에 문장을 쓰지 않는다는 [AGENTS.md](../../AGENTS.md) 규칙을 지키려면 `api_error_status`와 exit code를 우선 써야 한다. 인증 없음을 구분하는 구조화 필드는 이번 출력에 없었다.
- 한도 오류: 확인 불가. 일부러 한도를 소진하지 않았고 실행 중 발생하지 않았다.

## C5 `--effort` 값

도움말의 값 목록은 `low, medium, high, xhigh, max`다. haiku로 각각 호출했다.

| 값 | exit | `is_error` | stderr |
|---|---|---|---|
| `low`, `medium`, `high`, `xhigh`, `max` | 0 | false | 없음 |
| `bogus-effort` | 0 | false | `Warning: Unknown --effort value 'bogus-effort' — ignoring it and using the default effort. Valid values: low, medium, high, xhigh, max.` |

결론: 값 이름은 확인됨. 알 수 없는 값은 거부하지 않고 경고만 남긴 뒤 기본 effort로 실행한다. 설정 검증은 오케스트레이터가 해야 한다. 출력 JSON에는 실제 적용된 effort를 알려 주는 필드가 없어서, 모델별 실효값(예: haiku의 `xhigh`, `max`)은 미확인이다. [02-config-spec](../02-config-spec.md#provider와-agent)의 "실효값 미확인은 unknown"과 맞는다.

## 문서와 다른 점, 문서에 없는 점

- Fable 5.2가 문서의 최소 버전보다 낮은 CLI 2.1.316에서 호출에 성공했다.
- 오류에서도 `subtype`이 `success`다.
- `--effort`의 알 수 없는 값이 exit 0으로 무시된다.
- `--tools`와 별개로 사용자 MCP 도구가 노출됐을 가능성이 있다.

이 내용을 기획 문서와 결정에 반영할지는 #8에서 정한다.

## 남은 미확인

- 한도 오류의 출력 형태
- 비대화형 실행에 노출되는 MCP 도구 목록
- `--json-schema`의 `pattern`, `format` 위반 처리
- 모델별 실효 effort
- Opus, Sonnet, Fable의 `--json-schema` 수락(이번에는 haiku만 시험)
