# 검사 단계 네트워크 차단 확인 결과

이슈 #30의 확인 결과다. 검사(check)와 check-probe 단계에서 프로젝트 명령과 그 자식의 네트워크를 Windows에서 관리자 권한 없이 막을 수 있는지 확인했다. 후보는 프록시 환경 변수, 패키지 관리자의 offline 설정, AppContainer, Windows Firewall이다. 모델은 호출하지 않았다.

## 실행 환경

| 항목 | 값 |
|---|---|
| 실행일 | 2026-11-17 |
| OS | Windows 11 (10.0.26200), 사용자 PC, 일반 사용자 권한(관리자 아님) |
| Python | 3.13.15 (`<HOME>\AppData\Local\Programs\Python\Python313`) |
| Node, npm | v24.14.0, 11.9.0 |
| uv | 0.12.23 |
| curl | 8.22.0 (`C:\Windows\System32\curl.exe`, Schannel) |
| Git | `2.53.0.windows.2` |
| 실행 명령 | `python scripts/probes/windows_network_block.py --out <출력 폴더>` |
| 실행 방법 | 탐색기에서 실행한 `.cmd`가 `chcp 65001` 뒤 스크립트를 실행 |

실행 전 환경에 상속된 프록시 변수는 없었다. 스크립트는 상속된 `GIT_*`, 이름에 `PROXY`가 들어간 변수, 패키지 관리자의 offline과 index 변수를 지우고 시작한다. npm cache는 후보마다 따로 둬서 앞 후보의 cache가 다음 후보의 결과를 바꾸지 않게 했다. pip와 uv는 cache를 끄고 실행했다.

관찰 원본은 [fixtures/windows-network-block/windows-11-python-3.13.15.json](fixtures/windows-network-block/windows-11-python-3.13.15.json)에 있다. 홈 경로는 `<HOME>`, AppContainer profile 이름의 PID는 `<pid>`로 바꿨다.

## 결과 요약

| ID | 항목 | 결론 |
|---|---|---|
| N1 | 프록시 환경 변수와 offline 설정 | 확인됨. 도구마다 따르는 설정이 다르고, 어느 조합도 직접 소켓 연결은 막지 못함 |
| N2 | AppContainer | 확인됨. 관리자 없이 profile을 만들었고 capability 없는 프로세스와 손자의 네트워크가 막힘. 권한을 주지 않은 폴더의 실행 파일과 파일은 접근 거부 |
| N3 | Windows Firewall | 확인 불가. 규칙 추가에 관리자 권한이 필요하고 이 PC는 일반 사용자 권한. 규칙은 만들지 않음 |

## N1 프록시 환경 변수와 offline 설정

방법: 도구 9개가 같은 대상에 접속한다. 대상은 `https://pypi.org/simple/six/`, `https://registry.npmjs.org/is-number`, `pypi.org:443`(직접 소켓), Git은 `https://github.com/git/git.git`이다. 후보별 설정은 다음과 같다.

- baseline: 설정 없음.
- proxy_env: `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`(대소문자 모두)를 닫힌 로컬 포트 `http://127.0.0.1:9`로 지정하고 `NO_PROXY`는 비움. npm용 `npm_config_proxy`, `npm_config_https_proxy`도 같은 주소로 지정.
- proxy_env_node: proxy_env에 `NODE_USE_ENV_PROXY=1`을 더함.
- offline_flags: `npm_config_offline=true`, `PIP_NO_INDEX=1`, `UV_OFFLINE=1`.

값은 네트워크에 닿았는지다. 닿음은 HTTP 200, 소켓 연결 성공, 패키지 정보 수신을 뜻한다.

| 도구 | baseline | proxy_env | proxy_env_node | offline_flags |
|---|---|---|---|---|
| Python urllib | 닿음 | 막힘 (WinError 10061) | 막힘 | 닿음 |
| Python 직접 소켓 | 닿음 | 닿음 | 닿음 | 닿음 |
| Node `fetch` | 닿음 | 닿음 | 막힘 (ECONNREFUSED) | 닿음 |
| Node `https` | 닿음 | 닿음 | 막힘 (ECONNREFUSED) | 닿음 |
| curl | 닿음 | 막힘 (exit 7) | 막힘 | 닿음 |
| `pip download` | 닿음 | 막힘 | 막힘 | 막힘 (index 없음) |
| `npm view` | 닿음 | 막힘 (ECONNREFUSED) | 막힘 | 막힘 (ENOTCACHED) |
| `uv pip install --dry-run --no-cache` | 닿음 | 막힘 (재시도 3회, 약 16초) | 막힘 | 막힘 (cache에 없음) |
| `git ls-remote` | 닿음 | 막힘 (exit 128) | 막힘 | 닿음 |

- Node 24는 `NODE_USE_ENV_PROXY=1`이 없으면 프록시 환경 변수를 무시했다. 이 설정이 있으면 `fetch`와 `https` 모두 프록시로 갔다.
- 직접 소켓은 네 후보 모두에서 연결됐다. 프록시 환경 변수는 각 프로그램이 스스로 따르는 약속이라 소켓을 직접 여는 코드는 영향을 받지 않는다.
- offline 설정은 해당 패키지 관리자 세 개만 막았다. 같은 프로세스 안의 일반 HTTP와 Git은 그대로 닿았다.
- uv는 막힐 때 재시도 때문에 13초에서 16초가 걸렸다. 다른 도구는 4초 안에 실패했다.

결론: 확인됨. 프록시 환경 변수(`NODE_USE_ENV_PROXY=1` 포함)는 이번 도구 중 표준 HTTP 경로를 쓰는 것은 모두 막았고 직접 소켓은 막지 못했다. offline 설정은 패키지 관리자에만 듣는다. 두 방법 모두 관리자 권한이 필요 없지만 프로그램이 설정을 따를 때만 효과가 있다.

## N2 AppContainer

방법: `CreateAppContainerProfile`로 이 실행 전용 profile을 만들고, 임시 작업 폴더에만 `icacls /grant *<SID>:(OI)(CI)F`로 권한을 줬다. 그 profile로 `cmd.exe /d /c`를 시작해 아래 명령을 실행했다. 끝난 뒤 `DeleteAppContainerProfile`로 profile을 지웠다. profile 생성(`0x0`), 권한 부여(exit 0), 삭제(`0x0`)가 모두 관리자 권한 없이 성공했다.

| 경우 | capability | exit | 출력 |
|---|---|---|---|
| 권한 준 폴더의 파일 읽기 | 없음 | 0 | `probe file` |
| 권한 준 폴더에 파일 쓰기 | 없음 | 0 | `written` |
| curl로 pypi.org 접속 | 없음 | 6 | `Could not resolve host: pypi.org` |
| `cmd.exe`가 다시 띄운 curl(손자)로 접속 | 없음 | 6 | `Could not resolve host: pypi.org` |
| curl로 pypi.org 접속 | `internetClient` | 0 | `200` |
| 사용자 설치 Python 시작 (`<HOME>\AppData\Local\Programs\...\python.exe`) | 없음 | 1 | `액세스가 거부되었습니다.` |
| 권한 주지 않은 `<HOME>` 목록 읽기 | 없음 | 1 | 항목 0개 |

- capability가 없으면 이름 해석 단계에서 실패했다. `internetClient`를 준 대조군은 같은 명령이 200을 받았으므로 실패 원인은 capability 유무다.
- 손자 프로세스도 같은 AppContainer 토큰을 물려받아 막혔다.
- `C:\Windows\System32`의 curl과 `cmd.exe`는 실행됐다. 사용자 홈 아래에 설치된 Python은 실행 파일에 접근하지 못해 시작조차 되지 않았다. 권한을 주지 않은 홈 폴더도 읽지 못했다.
- 직접 소켓, Node, uv, pip, Git을 AppContainer 안에서 실행하는 시험은 하지 않았다. 사용자 설치 실행 파일이 시작되지 않는다는 점이 먼저 드러났기 때문이다.

결론: 확인됨. AppContainer는 관리자 권한 없이 만들 수 있고, capability가 없으면 직접 실행한 프로세스와 손자 모두 네트워크에 닿지 못한다. 프로그램이 설정을 따르는지와 무관하게 OS가 막는다. 대신 프로젝트 검사를 실제로 돌리려면 workspace뿐 아니라 Python, Node 같은 toolchain, 의존성 환경(`.venv`, `node_modules`), cache 폴더에 AppContainer SID의 읽기와 실행 권한을 줘야 한다. 어느 폴더까지 권한을 줘야 실제 검사가 통과하는지, 권한 부여가 사용자 폴더 ACL을 바꾸는 부작용을 어떻게 되돌릴지는 확인하지 않았다.

## N3 Windows Firewall

관찰:

- `IsUserAnAdmin`은 false였다.
- `netsh advfirewall show currentprofile state`는 성공했고 현재 profile은 Public, 상태는 ON이었다.
- 규칙 추가는 시스템 설정을 바꾸므로 시험하지 않았다.

결론: 확인 불가. 프로그램별 outbound 차단 규칙은 관리자 권한이 필요하다. D02의 일반 사용자 실행 전제에서는 쓸 수 없으므로 후보에서 뺀다. 관리자 권한으로 한 번 규칙을 만들어 두는 방식은 이번에 다루지 않았다.

## 기획에 주는 영향

- [02-config-spec](../02-config-spec.md)의 `checks.network: blocked`는 지금 문서로는 어떤 방식으로 막는지 정해져 있지 않다. 관리자 없이 가능한 방식은 프록시와 offline 설정(협조형), AppContainer(OS 강제) 두 가지다.
- 협조형은 직접 소켓과 설정을 무시하는 프로그램을 막지 못한다. D06(trusted-local)은 AI의 실수를 막는 수준을 요구하므로 이것으로 충분한지는 결정이 필요하다.
- AppContainer는 강제력이 있지만 toolchain과 의존성 폴더 권한 부여가 선행돼야 하고, 그 범위는 미확인이다.
- 이 선택은 [05-open-decisions D17](../05-open-decisions.md#d17-검사-단계-네트워크-차단-방식)로 남겼다.
