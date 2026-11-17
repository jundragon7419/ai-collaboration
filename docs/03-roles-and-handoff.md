# 역할과 handoff 계약

기준일: 2026-11-17. protocol v2 개정안. trusted-local과 prepare 및 check 결과의 경계를 반영했으며 실제 CLI 수락은 미확인이다.

## 기본 역할 4개

| role | 책임 | 허용 정책 | 입력 | 출력 kind |
|---|---|---|---|---|
| planner | 요청을 완료 조건과 구현 및 테스트 계약으로 정리 | 소스 읽기 전용, 승인과 명령 변경 불가 | 요청, run의 고정 소스, 등록 검사 ID | plan |
| coder | 승인 범위의 구현과 판정된 코드 수정 | 기본 flow는 승인한 소스와 테스트, tester flow는 test_paths를 제외한 소스만 쓰기 | 요청, 승인 계획, 현재 소스와 diff, 필요한 검사 및 리뷰 지적 | implementation |
| tester | 계획의 기대값에 맞는 테스트 작성과 수정. 직접 실행하지 않음 | test_paths 안에만 쓰기, 기본 tests/. 다른 경로와 제어 기록 변경 금지 | 승인 계획과 최신 누적 diff만 | test-authoring |
| reviewer | 요구 준수와 코드 및 테스트 결함 검토, 검사 실패 원인과 수정 대상 판정 | 읽기 전용, 직접 수정과 강제 통과 불가 | 요청, 승인 계획, 최종 소스와 diff, 현재 검사 결과 또는 검사 미실행 상태 | review |

동일 agent를 여러 역할에 배정해도 호출마다 새 세션과 해당 role의 권한을 적용한다. reviewer가 여럿이면 같은 snapshot을 받고 서로의 출력과 코더 대화를 받지 않는다. planner와 coder는 각각 정확히 한 명이다. tester는 활성 flow에서 한 명이며 reviewer만 여러 명을 지원한다.

tester에는 코더 설명, 대화 기록, 검사 로그와 리뷰어 자유 형식 설명을 전달하지 않는다. 기존 테스트 변경도 누적 diff에 포함한다. 변경되지 않은 fixture와 import 방식을 알 수 없다면 계획의 test_contract를 보완하도록 사람에게 묻는다. 자료가 부족해도 소스 읽기 도구나 추가 문맥을 자동으로 열지 않는다. 입력 제한의 품질 효과는 미확인이다.

허용 정책은 실제 사전 차단의 성공과 다르다. workspace-write는 workspace 단위이며 test_paths만 쓰는 보장이 아니다. 권한 옵션과 도구 제한을 적용하고 승인 범위 밖 변경은 실행 뒤 manifest 검사로 탐지해 중단한다. test_paths 사전 차단은 MVP 필수가 아니다. 악의적 저장소와 prompt injection 방어를 보장하지 않으며 자동 복원하지 않는다. 경로별 사전 강제는 이후 검토 범위다. [Codex 설정](https://learn.chatgpt.com/docs/config-file/config-reference), [Claude 파일 권한](https://code.claude.com/docs/en/permissions#read-and-edit).

## source와 prepare 및 check 입력

source는 시작 시 고정한 HEAD OID에서 만든 run workspace다. 원본의 staged와 unstaged 및 untracked 소스를 읽어 섞지 않는다. 현재 실행 설정과 prepare/check argv 및 역할 prompt는 별도 확인한 control 입력으로 고정하며, workspace의 설정 변경으로 대체하지 않는다.

| 단계 또는 역할 | 전달하는 자료 | 자동 전달하지 않는 자료 |
|---|---|---|
| prepare | 확인한 command와 cwd, runtime, 준비 경로 및 기존 패키지 관리자 인증 경로 | 모델이 제안한 명령과 임의 control 변경 |
| planner | 고정 source와 요청, 등록 check ID, 확인한 준비 완료 상태 | prepare stdout과 stderr, 설치 package 내용 전체 |
| coder | 승인 계획과 run source 및 diff, 필요한 check 실패 및 리뷰 지적, 준비 환경 식별자 | 원본 미커밋 source와 전체 설치 로그 |
| tester | 승인 계획과 최신 누적 diff만 | 코더 설명, prepare 및 check 로그와 reviewer 자유 텍스트 |
| check | 같은 run의 source와 준비 의존성, 고정 command와 blocked 네트워크 | 모델의 검사 성공 주장과 prepare의 네트워크 허용 |
| reviewer | 현재 source와 diff, 승인 계획, 실제 check 기록 또는 검사 미실행, 필요한 준비 상태 식별자 | 준비 로그의 성공 문구를 검사 성공 근거로 사용 |

준비 실패는 모델 흐름을 시작하지 않고 사람에게 진단 자료를 보여 준다. raw 로그는 운영 기록이고 명령이나 역할 prompt로 실행하지 않는다. 로그를 자료로 분리한다는 것이 prompt injection 방어를 보장하는 것은 아니다. .venv와 node_modules 등 준비 산출물을 코드 diff와 commit 대상에서 제외하며 source 및 lock 변경을 환경 baseline에 묻지 않는다.

prepare 결과의 source와 lock 전후 상태, config와 command 및 toolchain hash, 의존성 metadata manifest를 별도로 기록한다. 실행 중 dependency 입력이 달라지면 이전 준비 기록을 그대로 신뢰하지 않고 D13에 따라 중단하고 사람이 의존성 추가 후 재시작하도록 안내한다. doctor 시험 결과도 prepare나 실제 run check의 성공과 구분한다.

## 전달과 제어 기록

모델의 role-result는 비신뢰 자료다. stdout 또는 결과 파일을 오케스트레이터가 직접 수집하고 검증한 후 handoff record를 만든다. run ID, role과 agent, 프로세스 종료 상태와 승인 기록을 모델의 자기 보고로 만들지 않는다. role-result의 changed_paths도 실제 파일 감사의 대체물이 아니다.

오케스트레이터는 요청, 승인 계획과 설정, snapshot과 검사 및 리뷰를 hash로 연결한다. 인증 자료는 모델과 check에 전달하지 않는다. 기록에는 요청 모델과 관측 모델, 요청 effort와 관측 effort, 시간과 관측 사용량을 별도로 남긴다. 관측하지 못한 값은 unknown이다. raw 이벤트와 debug 출력은 기본 영구 보관하지 않는다.

JSON Schema는 구조를 검사하며 문자열 안의 prompt injection을 없애지 못한다. 권한과 CLI 옵션, 명령과 publish 확인은 모델의 자유 텍스트에서 가져오지 않는다. reviewer의 repair_targets는 유한 enum을 검증한 뒤 미리 정한 수정 전이에만 사용한다. 모델이 임의 다음 단계와 실행 명령을 만들 수 없다.

## 공통 role-result JSON Schema

Claude에는 같은 schema를 --json-schema의 JSON 문자열로, Codex에는 --output-schema의 JSON 파일로 전달한다. 모든 객체는 additionalProperties=false이며 모든 property를 required로 둔다. provider 간 공통 수락은 실제 모델 probe 전까지 미확인이다. [Claude 구조화 출력](https://code.claude.com/docs/en/headless#get-structured-output), [Codex 비대화형 실행](https://learn.chatgpt.com/docs/non-interactive-mode), [OpenAI Schema 제한](https://developers.openai.com/api/docs/guides/structured-outputs).

사용하지 않는 payload는 빈 문자열과 배열로 채우고, review의 enum은 not-applicable을 쓴다. kind와 payload의 대응은 로컬 의미 검사로 제한한다.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "kind",
    "status",
    "summary",
    "questions",
    "plan",
    "implementation",
    "testing",
    "review",
    "observations"
  ],
  "properties": {
    "schema_version": {
      "type": "integer",
      "enum": [
        2
      ]
    },
    "kind": {
      "type": "string",
      "enum": [
        "plan",
        "implementation",
        "test-authoring",
        "review",
        "observation"
      ]
    },
    "status": {
      "type": "string",
      "enum": [
        "completed",
        "needs-input",
        "blocked"
      ]
    },
    "summary": {
      "type": "string"
    },
    "questions": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "plan": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "goal",
        "criteria",
        "steps",
        "scope_paths",
        "check_ids",
        "test_contract",
        "new_dependencies_required",
        "dependency_reason"
      ],
      "properties": {
        "goal": {
          "type": "string"
        },
        "criteria": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "id",
              "description"
            ],
            "properties": {
              "id": {
                "type": "string"
              },
              "description": {
                "type": "string"
              }
            }
          }
        },
        "steps": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "scope_paths": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "check_ids": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "test_contract": {
          "type": "string"
        },
        "new_dependencies_required": {
          "type": "boolean"
        },
        "dependency_reason": {
          "type": "string"
        }
      }
    },
    "implementation": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "description",
        "changed_paths",
        "addressed_criteria"
      ],
      "properties": {
        "description": {
          "type": "string"
        },
        "changed_paths": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "addressed_criteria": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
    },
    "review": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "criteria",
        "findings",
        "failure_attribution",
        "repair_targets",
        "execution_assessment"
      ],
      "properties": {
        "criteria": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "criterion_id",
              "assessment",
              "evidence"
            ],
            "properties": {
              "criterion_id": {
                "type": "string"
              },
              "assessment": {
                "type": "string",
                "enum": [
                  "satisfied",
                  "failed",
                  "not-checked",
                  "not-verified"
                ]
              },
              "evidence": {
                "type": "string"
              }
            }
          }
        },
        "findings": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "id",
              "severity",
              "title",
              "path",
              "line",
              "criterion_id",
              "condition",
              "observed",
              "expected",
              "evidence",
              "impact",
              "scope",
              "workaround"
            ],
            "properties": {
              "id": {
                "type": "string"
              },
              "severity": {
                "type": "string",
                "enum": [
                  "P0",
                  "P1",
                  "P2",
                  "P3",
                  "P4",
                  "P5"
                ]
              },
              "title": {
                "type": "string"
              },
              "path": {
                "type": "string"
              },
              "line": {
                "type": "integer"
              },
              "criterion_id": {
                "type": "string"
              },
              "condition": {
                "type": "string"
              },
              "observed": {
                "type": "string"
              },
              "expected": {
                "type": "string"
              },
              "evidence": {
                "type": "string"
              },
              "impact": {
                "type": "string"
              },
              "scope": {
                "type": "string"
              },
              "workaround": {
                "type": "string"
              }
            }
          }
        },
        "failure_attribution": {
          "type": "string",
          "enum": [
            "not-applicable",
            "code",
            "tests",
            "both",
            "environment",
            "unclear"
          ]
        },
        "repair_targets": {
          "type": "array",
          "items": {
            "type": "string",
            "enum": [
              "coder",
              "tester"
            ]
          }
        },
        "execution_assessment": {
          "type": "string",
          "enum": [
            "not-applicable",
            "passed",
            "failed",
            "not-run",
            "environment-error"
          ]
        }
      }
    },
    "observations": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "testing": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "description",
        "changed_paths",
        "covered_criteria"
      ],
      "properties": {
        "description": {
          "type": "string"
        },
        "changed_paths": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "covered_criteria": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
    }
  }
}
```

## 의미 검증과 판정 흐름

- planner는 목표, 고유 완료 조건, 변경 범위와 작업 순서, new_dependencies_required와 dependency_reason을 채운다. 승인 화면에 새 의존성 필요 여부를 표시하고 필요하면 사람이 run 밖에서 의존성을 먼저 추가한 뒤 재시작한다. tester flow에서는 framework, API와 기대값을 test_contract에 명시한다. 검사 on이면 check_ids가 모든 활성 검사 ID와 같아야 하고 off이면 빈 배열이다. 명령은 계획에 넣어 실행하지 않는다.
- 사용하지 않는 plan payload의 new_dependencies_required는 false, dependency_reason은 빈 문자열이다.
- coder가 계획 밖 manifest나 lock을 바꾸면 중단한다. run 안 lock 변경은 계획 여부와 무관하게 D12에 따라 중단한다.
- coder와 tester는 자신이 쓴 종류의 payload만 채운다. tester의 모든 실제 변경 경로가 test_paths에 포함돼야 한다. tester flow의 coder가 그 경로를 수정하면 역할 위반이다. 코드가 이미 맞으면 변경하지 않을 수 있지만 역할 결과는 완료 여부를 명시한다.
- review에는 모든 승인 완료 조건이 중복 없이 있어야 한다. satisfied는 근거가 있는 충족, failed는 관련 finding이 있는 실패, not-checked는 리뷰 미완료다. not-verified는 검토했지만 실행 증거가 없다는 뜻이며 검사 off에서 허용하고 “검사 미실행”을 표시한다. not-checked를 미실행의 대체 상태로 사용하지 않는다.
- execution_assessment는 trusted 검사 기록과 일치해야 한다. 검사 off이면 not-run이다. 실행한 검사가 실패했는데 passed로 쓰면 결과를 거부한다. 모델이 status=completed라고 해도 gate 성공이 아니다.
- 실패 검사에는 failure_attribution을 code, tests, both, environment, unclear 중 하나로 쓴다. 정상 검사 또는 미실행이면 not-applicable이다. code는 coder, tests는 tester, both는 두 role을 repair_targets에 지정한다. tester가 없는 flow는 테스트 수정도 coder가 맡는다. 환경 문제와 불명확한 원인은 자동 수정 대신 사람에게 넘긴다.
- 정상 검사와 검사 미실행에서도 차단 지적의 수정이 필요하면 repair_targets에 해당 역할을 지정한다. failure_attribution은 검사 실패 원인 필드이므로 이 경우 not-applicable을 유지한다. 수정 대상과 검사 실패 원인을 같은 필드로 합치지 않는다.
- 복수 리뷰어의 원인이나 수정 대상이 다르면 사람에게 넘긴다. 같은 지적의 등급이 차단 경계를 가르면 높은 등급을 잠정 적용하고 사람의 근거 있는 판정을 받는다. 투표로 낮추지 않는다.
- finding은 재현 조건, 실제 관찰과 기대값, 근거, 영향과 범위, 우회 방법을 포함한다. 우회가 없으면 없다고 적는다. 없는 증거를 추정해 채우지 않는다.
- path는 현재 snapshot의 상대 경로, line은 실제 1 이상의 줄 번호다. 삭제 파일은 base에서 확인한다. 전역 문제는 path가 빈 문자열이며 line=0이다. criterion_id는 승인된 ID 또는 관련 조건이 없을 때 빈 문자열이다.
- status=needs-input에는 질문이, blocked에는 중단 이유가 있어야 한다. 완료 결과의 필수 내용이 비어 있으면 형식상 valid여도 다음 단계로 가지 않는다. 결과는 1 MiB 상한을 적용한다는 제안을 유지하며 조용히 잘라서 수락하지 않는다.

최초 coder-tester-check-review 실행은 회차 0이다. reviewer의 판정으로 수정 묶음을 시작할 때 공유 revision_round를 1 올린다. coder 수정이면 tester flow에서 tester를 다시 호출한다. tester만 수정하면 coder를 호출하지 않는다. both도 한 회차이고 재검사와 모든 리뷰는 그 회차에 포함한다. role 전환과 checkpoint 재개로 counter를 초기화하지 않는다. prepare와 doctor 시험은 이 수정 회차의 코드 수정으로 세지 않고 각각 실행 기록을 가진다. plan과 config를 바꾸려면 새 승인이 필요하다.

검사 실패도 reviewer에게 보내며, tester가 assertion을 약화하거나 실패 테스트를 삭제해서 성공하게 만들지 않았는지 함께 검토한다. plan과 diff만으로 tester가 같은 실패를 반복하거나 기대값이 불명확하면 사람에게 넘긴다. tester의 입력 제한을 숨겨서 넓히지 않는다.

## P0부터 P5까지의 등급

원문 01-overview.md:17의 정의를 따른다. 이전 문서의 별도 영향 및 우회 중심 정의를 사용자 기준처럼 유지하지 않는다. 이 제품의 분류이며 CLI나 업계 공통 표준은 아니다. 취향 차이는 어느 등급에도 넣지 않는다.

| 등급 | 사용자 정의 | 적용 설명 |
|---|---|---|
| P0 | 보안 경계 위반, 데이터 손실, 비밀 유출 | 관측 조건과 근거를 제시. 범위가 좁다는 이유만으로 낮추지 않음 |
| P1 | 주된 기능 실패, 완료 조건 미충족 | 승인 완료 조건 실패는 P1 기준과 대조 |
| P2 | 특정 조건에서 기능 실패, 바뀐 동작에 테스트 없음 | 테스트 부재를 취향으로 분류하지 않음 |
| P3 | 사용자 영향이 작은 결함 | 영향이 작다는 근거와 재현 조건 제시 |
| P4 | 유지보수 문제 | 구체적인 오류 유발과 수정 비용 근거가 필요. 코드 모양 선호는 제외 |
| P5 | 사소한 것 | 관측 가능한 작은 문제만 포함. 이름과 문체 취향은 제외 |

여러 기준에 해당하면 더 높은 등급을 적용한다는 구현안을 제안한다. 차단 경계를 가르는 reviewer 불일치는 기존처럼 사람에게 넘긴다. P0부터 P5까지의 실제 일관성은 미측정이다. block_up_to=P2이면 P0, P1, P2를 차단한다. 실제 check 실패와 리뷰 미완료를 등급으로 낮춰 통과시키지 않는다.

## 결과 예시

아래는 형식 설명용 가상 예시이며 이 저장소에서 실행한 결과가 아니다.

계획:

```json
{
  "schema_version": 2,
  "kind": "plan",
  "status": "completed",
  "summary": "빈 입력 처리와 테스트 범위를 계획했다.",
  "questions": [],
  "plan": {
    "goal": "빈 입력에서 정의한 오류를 반환한다.",
    "criteria": [
      {
        "id": "AC1",
        "description": "빈 입력의 기대 오류를 검증한다."
      }
    ],
    "steps": [
      "입력 검증을 구현한다.",
      "계획과 diff로 테스트를 작성한다."
    ],
    "scope_paths": [
      "src/parser.py",
      "tests/test_parser.py"
    ],
    "check_ids": [
      "tests"
    ],
    "test_contract": "pytest를 사용한다. parse(빈 문자열)는 ValueError를 발생시킨다. 테스트는 tests/test_parser.py에 작성한다.",
    "new_dependencies_required": false,
    "dependency_reason": "기존 의존성으로 처리한다."
  },
  "implementation": {
    "description": "",
    "changed_paths": [],
    "addressed_criteria": []
  },
  "testing": {
    "description": "",
    "changed_paths": [],
    "covered_criteria": []
  },
  "review": {
    "criteria": [],
    "findings": [],
    "failure_attribution": "not-applicable",
    "repair_targets": [],
    "execution_assessment": "not-applicable"
  },
  "observations": []
}
```

테스터:

```json
{
  "schema_version": 2,
  "kind": "test-authoring",
  "status": "completed",
  "summary": "계획의 빈 입력 기대값을 검증하는 테스트를 작성했다.",
  "questions": [],
  "plan": {
    "goal": "",
    "criteria": [],
    "steps": [],
    "scope_paths": [],
    "check_ids": [],
    "test_contract": "",
    "new_dependencies_required": false,
    "dependency_reason": ""
  },
  "implementation": {
    "description": "",
    "changed_paths": [],
    "addressed_criteria": []
  },
  "testing": {
    "description": "빈 입력의 ValueError를 검증한다. 실행하지 않았다.",
    "changed_paths": [
      "tests/test_parser.py"
    ],
    "covered_criteria": [
      "AC1"
    ]
  },
  "review": {
    "criteria": [],
    "findings": [],
    "failure_attribution": "not-applicable",
    "repair_targets": [],
    "execution_assessment": "not-applicable"
  },
  "observations": []
}
```

검사 실패 판정:

```json
{
  "schema_version": 2,
  "kind": "review",
  "status": "completed",
  "summary": "검사 실패는 구현이 계획의 기대 오류를 반환하지 않기 때문이다.",
  "questions": [],
  "plan": {
    "goal": "",
    "criteria": [],
    "steps": [],
    "scope_paths": [],
    "check_ids": [],
    "test_contract": "",
    "new_dependencies_required": false,
    "dependency_reason": ""
  },
  "implementation": {
    "description": "",
    "changed_paths": [],
    "addressed_criteria": []
  },
  "testing": {
    "description": "",
    "changed_paths": [],
    "covered_criteria": []
  },
  "review": {
    "criteria": [
      {
        "criterion_id": "AC1",
        "assessment": "failed",
        "evidence": "검사에서 IndexError가 관측됐으며 계획은 ValueError를 요구한다."
      }
    ],
    "findings": [
      {
        "id": "F1",
        "severity": "P1",
        "title": "빈 입력에서 기대 오류 대신 IndexError 발생",
        "path": "src/parser.py",
        "line": 12,
        "criterion_id": "AC1",
        "condition": "빈 문자열로 parse를 호출할 때",
        "observed": "IndexError가 발생한다.",
        "expected": "ValueError가 발생한다.",
        "evidence": "입력 검증 없이 첫 문자에 접근하며 검사 결과와 일치한다.",
        "impact": "지원하는 빈 입력의 오류 계약 실패",
        "scope": "빈 입력 처리",
        "workaround": "호출자가 빈 입력을 먼저 거부해야 한다."
      }
    ],
    "failure_attribution": "code",
    "repair_targets": [
      "coder"
    ],
    "execution_assessment": "failed"
  },
  "observations": []
}
```

## handoff record JSON Schema

다음은 모델 출력이 아니라 오케스트레이터가 작성하는 metadata다. result 파일과 record는 쓰기 역할의 수정 대상이 아니다. 보장 수준은 trusted-local이며 악의적 변조의 사전 차단을 보장하지 않는다. hash를 같은 가변 파일 옆에 두었다는 이유로 악의적 위조를 방어한다고 표시하지 않는다.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "protocol_version",
    "run_id",
    "invocation_id",
    "stage_id",
    "role",
    "agent_id",
    "attempt",
    "base_commit",
    "request_sha256",
    "snapshot_sha256",
    "plan_sha256",
    "config_sha256",
    "result_path",
    "result_sha256",
    "revision_round",
    "prepare_record_sha256",
    "dependency_manifest_sha256"
  ],
  "properties": {
    "protocol_version": {
      "type": "integer",
      "enum": [
        2
      ]
    },
    "run_id": {
      "type": "string"
    },
    "invocation_id": {
      "type": "string"
    },
    "stage_id": {
      "type": "string"
    },
    "role": {
      "type": "string"
    },
    "agent_id": {
      "type": "string"
    },
    "attempt": {
      "type": "integer"
    },
    "base_commit": {
      "type": "string"
    },
    "request_sha256": {
      "type": "string"
    },
    "snapshot_sha256": {
      "type": "string"
    },
    "plan_sha256": {
      "type": "string"
    },
    "config_sha256": {
      "type": "string"
    },
    "result_path": {
      "type": "string"
    },
    "result_sha256": {
      "type": "string"
    },
    "revision_round": {
      "type": "integer"
    },
    "prepare_record_sha256": {
      "type": "string"
    },
    "dependency_manifest_sha256": {
      "type": "string"
    }
  }
}
```

ID와 attempt, revision_round는 현재 run과 호출에 맞아야 한다. attempt는 1 이상이고 revision_round는 0 이상이며 설정 상한을 넘을 수 없다. digest는 소문자 64자리 SHA-256이고 승인 전 plan_sha256만 빈 문자열을 허용한다. base_commit은 실제 저장소 object ID이며 SHA-1 길이로 고정하지 않는다. result_path는 run 제어 영역의 상대 경로이고 링크 탈출과 절대 경로, stream 이름을 거부한다.

CLI 결과는 프로세스 트리가 끝난 뒤 오케스트레이터가 복사해 고정한다. Claude는 종료 상태와 envelope 및 structured_output, Codex는 종료 상태와 JSONL 이벤트 및 새 -o 결과 파일을 함께 확인한다. 부분 출력과 과거 파일, JSON 앞뒤의 설명을 잘라 만든 결과는 수락하지 않는다. Schema와 의미 검사 실패는 통과가 아니다.

## snapshot과 검사 기록

tracked 파일과 승인된 새 파일의 경로, Git mode와 실제 byte, 삭제 상태를 정렬한 manifest로 SHA-256을 계산한다. CRLF와 LF를 임의 통일하지 않는다. 다른 untracked와 ignored 파일은 경로, 종류, 크기와 수정 시각을 감사한다. 의존성의 매 단계 전체 내용 hash는 기본으로 계산하지 않는다. metadata 감사가 악의적 변경 탐지와 동일하다는 보장은 하지 않는다.

Git index에는 attributes와 core.autocrlf에 따라 줄바꿈 등이 변환될 수 있으므로 raw snapshot hash와 Git blob hash를 직접 같다고 비교하지 않는다. 확인한 attributes 및 변환 정책과 expected_tree_oid를 commit 기록에 따로 둔다. source snapshot이 그대로이고 최종 tree가 승인한 대응 결과와 맞아야 한다. hooks와 filters는 평소대로 실행하지만 결과의 tree와 source가 검토한 상태와 다르면 중단하고 이미 생긴 commit은 committed-unverified로 기록한다. 자동 reset과 amend를 하지 않는다. [Git attributes](https://git-scm.com/docs/gitattributes).

구현(`src/aicollab/audit/`)은 다음과 같다. 경로 목록은 `git ls-files -z`처럼 NUL 구분 출력으로만 받는다. ignore되지 않은 untracked 파일은 승인 여부와 무관하게 모두 내용 hash를 계산하고, 승인 범위 밖이면 역할 감사에서 위반으로 판정한다. ignored 폴더는 폴더 한 항목의 metadata만 기록하고 안을 읽지 않는다. 작업 공간 안에 다른 Git 저장소가 생기면 안을 읽지 않고 위반으로 판정한다. 전후 비교는 경로마다 raw byte 변경과 Git tree 변경을 따로 남긴다. run worktree는 `<run_root>/<run_id>/worktree`, 감사 기록과 위반 증거는 `<run_root>/<run_id>/audit/<순번>-<역할>/`에 둔다. run_root는 [02-config-spec](02-config-spec.md)의 `project.run_root`이며 원본 checkout과 공유 Git 관리 경로 밖 절대 경로다. 원본 저장소 안에는 run 기록을 만들지 않는다. run_root가 상대 경로이거나 원본 작업 트리 안, 공유 Git 관리 경로(`git rev-parse --git-common-dir`) 안이면 worktree를 만들기 전에 거부한다. 경로는 실제 경로로 풀어 비교하고 Windows에서는 대소문자를 구분하지 않는다. `project.run_root`의 기본값 계산은 설정 읽기 구현에서 하고, 작업 공간 모듈은 run_root를 필수 인자로 받는다. 위반이 있으면 위반 파일의 byte 사본과 실행 전후 tree의 patch를 함께 남기고 작업 공간은 되돌리지 않는다.

검사 scratch는 소스와 겹치지 않아야 한다. source와 test 파일, lock 및 설정 파일이 check에서 바뀌면 중단한다. source digest를 계산하는 동안 파일이 달라지면 고정 후 다시 수집한다. Git 관리 경로와 제어 기록은 별도 감사 대상이다. 악의적 접근의 사전 차단을 완료 보장으로 쓰지 않는다.

prepare/check/check-probe는 별도 stage 기록이다. prepare 성공과 check-probe의 유한 종료 관측을 run check의 성공으로 사용할 수 없다.

| 검사 기록 | 타입과 의미 |
|---|---|
| check_id, run_id, snapshot_sha256, plan_sha256, config_sha256 | string. 실행과 코드 상태를 묶는 값 |
| argv와 cwd | string array와 string. 실제 명령과 실행 위치 |
| status | succeeded, failed, timed-out, cancelled, not-run-disabled, not-run-error |
| exit_code | integer 또는 null. 실제 관측한 경우만 integer |
| duration_ms | 0 이상의 integer |
| stdout_path와 stderr_path | run 안의 수집 자료 참조. 필요한 부분만 reviewer에게 전달 |

검사 off에서 not-run-disabled를 생성한다. 이 상태는 기본 flow의 qualified 완료를 허용하지만 검사 성공 횟수에 넣지 않는다. tester flow에서 생성되면 설정 또는 실행 오류다. 리뷰어에게 전달할 검사 결과도 비신뢰 문자열을 포함하므로 실행 명령으로 평가하지 않는다.

## prepare와 check 기록 Schema

다음은 오케스트레이터 내부 기록이며 role-result가 아니다. 모델이 생성하지 않고 두 CLI의 출력 Schema로 보내지도 않는다. prepare는 allowed, check와 check-probe는 blocked를 요구한다. stage 간 기록을 서로 대체하면 의미 검증 오류다. 실제 종료 코드를 관측하지 못했으면 null이다.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "protocol_version",
    "stage",
    "run_id",
    "command_id",
    "status",
    "eligibility",
    "argv",
    "cwd",
    "network",
    "toolchain_sha256",
    "config_sha256",
    "command_sha256",
    "base_commit",
    "source_before_sha256",
    "source_after_sha256",
    "dependency_manifest_sha256",
    "exit_code",
    "duration_ms",
    "file_changes",
    "stdout_path",
    "stderr_path"
  ],
  "properties": {
    "protocol_version": {
      "type": "integer",
      "enum": [
        2
      ]
    },
    "stage": {
      "type": "string",
      "enum": [
        "prepare",
        "check",
        "check-probe"
      ]
    },
    "run_id": {
      "type": "string"
    },
    "command_id": {
      "type": "string"
    },
    "status": {
      "type": "string",
      "enum": [
        "succeeded",
        "failed",
        "timed-out",
        "cancelled",
        "not-run-disabled",
        "not-run-error"
      ]
    },
    "eligibility": {
      "type": "string",
      "enum": [
        "not-applicable",
        "passed",
        "failed"
      ]
    },
    "argv": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "cwd": {
      "type": "string"
    },
    "network": {
      "type": "string",
      "enum": [
        "allowed",
        "blocked"
      ]
    },
    "toolchain_sha256": {
      "type": "string"
    },
    "config_sha256": {
      "type": "string"
    },
    "command_sha256": {
      "type": "string"
    },
    "base_commit": {
      "type": "string"
    },
    "source_before_sha256": {
      "type": "string"
    },
    "source_after_sha256": {
      "type": "string"
    },
    "dependency_manifest_sha256": {
      "type": "string"
    },
    "exit_code": {
      "type": [
        "integer",
        "null"
      ]
    },
    "duration_ms": {
      "type": "integer"
    },
    "file_changes": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "stdout_path": {
      "type": "string"
    },
    "stderr_path": {
      "type": "string"
    }
  }
}
```

check-probe의 eligibility=passed는 시간 안에 실제 검사 코드가 실행됐고 금지된 파일 변경이 없었다는 해당 조건의 관측이다. status=failed와 exit_code가 테스트 실패를 나타내더라도 동작 자격 관측과 구분할 수 있다. 실행 파일 누락, 의존성 오류와 초기화 실패를 자격 확인 성공으로 처리하지 않는다. 미래 실행의 안전 인증이나 run check 통과 증거는 아니다.

prepare가 실패하면 부분 의존성과 로그를 보존하고 모델 handoff record를 만들지 않는다. prepare 로그 경로는 운영자 진단용이며 tester 입력을 늘리는 참조로 사용하지 않는다. source와 lock 변화를 숨기지 않고 D12와 D13에 따라 lock 부재와 불일치, run 안 lock 변경 및 계획 밖 manifest 변경은 중단한다.

## commit과 Draft PR 인계

역할 출력은 commit SHA와 공개 승인을 만들어 낼 수 없다. gate 이후 승인된 Git 결과 tree가 base와 같으면 no-changes와 “변경 없음”으로 종료한다. commit과 push 및 Draft PR을 실행하지 않고 서명도 요청하지 않는다. 검사 off이면 무변경 결과에도 검사 미실행을 표시한다. 변경 있는 경우에만 사용자 identity와 서명 준비를 확인하고 평소 hooks로 commit한다. empty commit은 만들지 않으며 실패와 중단을 무변경 성공으로 바꾸지 않는다.

Draft PR 본문은 아래 항목을 trusted 실행 기록과 검증한 요약으로 채워 로컬에서 보여 준다. 모델 원문을 바로 공개하거나 raw 대화, 로컬 절대 경로와 인증 자료를 붙이지 않는다.

```markdown
## 변경 내용
승인된 목적과 범위, 구현 결과

## 검사
실제 명령과 종료 상태
꺼져 있으면 검사 미실행

## 리뷰
차단 기준과 남은 P0부터 P5까지의 지적

## 미확인 사항
실행 증거가 없는 부분과 알려진 한계
```

공개 확인은 repo와 공개 범위, remote와 branch, commit SHA, author와 committer의 이름 및 이메일, 검사 상태와 PR의 base 및 제목과 본문에 묶는다. 자동 이슈 닫기, reviewer 요청, label 변경과 merge는 포함하지 않는다. push와 PR은 성공 상태를 나누어 기록하고 응답 유실 때 기존 remote와 PR부터 확인한다.

## 새 역할과 쓰기 역할 확장

tester는 첫 번째 추가 쓰기 역할이다. “새 역할은 읽기 전용만 가능”이라는 기존 제한을 폐기한다. 새 쓰기 역할도 허용할 수 있으나 prompt 파일 하나로 권한과 실행 제어까지 자동 확장하지 않는다.

1. role ID와 책임, 최소 입력과 결과 kind를 role registry에 등록한다. 기존 Schema에 의미가 없으면 protocol 버전과 validator를 함께 변경한다.
2. 쓰기 root와 금지 경로, 기존 역할과의 파일 소유 관계를 정한다. tester와 coder처럼 범위가 겹치지 않게 하고 현재 MVP는 사후 감사와 중단 기준을 적용하고 사전 강제 성공처럼 표시하지 않는다.
3. 고정 flow에 들어갈 위치와 실패 판정자, 공유 수정 회차 소비, 검사와 리뷰 무효화 조건을 구현한다. 새 역할이 자체 승인이나 publish를 수행하지 못한다.
4. doctor의 권한 및 구조화 출력 시험을 추가하고 trusted-local의 권한 옵션과 도구 제한, 사후 변경 탐지 및 중단 조건을 충족한다. 설정과 prompt 변경은 사용자 확인 대상이다.
5. 해당 role을 CLI 배정 명령과 flow에 등록한다. kind와 의미가 미등록인 역할은 실행하지 않는다. 읽기 전용 observer를 추가할 때도 같은 입력 및 제어 계약을 적용한다.

역할 위반과 provenance 오류, 한도와 인증 실패, 필요한 정보 부족은 중단하고 부분 상태를 보존한다. 자동 restore/reset/clean과 fallback을 하지 않는다. 판정 기각은 사람이 finding ID와 snapshot, 이유를 별도 기록하며 이후 코드 상태에서는 다시 리뷰한다.
