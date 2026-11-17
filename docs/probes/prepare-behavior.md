# prepare 동작 확인 결과

이슈 #7의 확인 결과다. 대상은 새 worktree에서 `uv sync`와 `npm ci` 실행, lock 변경 탐지, lock 부재와 manifest 불일치 때의 동작, 실패 뒤 부분 환경, install script의 source 변경이다.

## 실행 환경

| 항목 | 값 |
|---|---|
| 실행일 | 2026-11-17 |
| OS | Linux 컨테이너(glibc 2.39, kernel 6.18). 사용자 PC가 아닌 클라우드 작업 공간 |
| Git | `git version 2.43.0` |
| uv | `uv 0.11.32` |
| Python | 3.13.18 (uv가 찾은 interpreter도 같음) |
| Node | `v22.23.4` |
| npm | `10.9.9` |
| 네트워크 | PyPI와 npm registry 접근 가능 |
| 실행 명령 | `python3 scripts/probes/prepare_behavior.py --out <출력 폴더>` |

실험 저장소는 임시 디렉터리에 새로 만들었고, 경우마다 `git worktree add --detach`로 새 worktree를 만들어 명령을 한 번씩 실행했다. source와 lock 비교는 `.git`, `.venv`, `node_modules`, `__pycache__`를 뺀 파일의 sha256 전후 비교다. 의존성 산출물은 폴더 존재와 파일 수만 기록했다.

Windows에서는 실행하지 않았다. 기존 기록의 Windows 환경은 Node v24.14.0, npm 11.9.0([02-config-spec Windows 실행과 wrapper](../02-config-spec.md#windows-실행과-wrapper))으로 이번 환경과 버전이 다르다. npm lifecycle script가 Windows에서 `cmd.exe`로 실행되는 점, `.venv\Scripts` 배치, 경로 길이 제한은 미확인이다. 같은 스크립트를 Windows에서 실행하면 같은 형식의 `results.json`이 나온다.

관찰 원본은 [fixtures/prepare-behavior/linux-uv-0.11.32-npm-10.9.9.json](fixtures/prepare-behavior/linux-uv-0.11.32-npm-10.9.9.json)에 있다. 임시 경로는 `<TMP>`, npm debug log 경로는 `<NPM_LOG>`로 바꿨다.

## 결과 요약

| ID | 경우 | 명령 | exit | source와 lock 변화 | 의존성 산출물 |
|---|---|---|---|---|---|
| U1 | lock 있음 | `uv sync` | 0 | 없음 | `.venv` 생성, six 설치 |
| U1b | 같은 worktree에서 다시 실행 | `uv sync` | 0 | 없음 | 그대로 |
| U2 | lock 없음 | `uv sync` | 0 | `uv.lock` 새로 생김 | `.venv` 생성 |
| U2b | lock 없음 | `uv sync --locked` | 2 | 없음 | `.venv` 생성(패키지 없음) |
| U3 | manifest에 의존성 추가, lock 그대로 | `uv sync` | 0 | `uv.lock` 수정 | `.venv` 생성, 새 의존성 포함 설치 |
| U3b | 같은 불일치 | `uv sync --locked` | 1 | 없음 | `.venv` 생성(패키지 없음) |
| U3c | 같은 불일치 | `uv sync --frozen` | 0 | 없음 | 예전 lock 기준으로 six만 설치 |
| U4 | build가 실패하는 의존성 포함 | `uv sync` | 1 | 없음 | `.venv` 생성, six 미설치 |
| U5 | 없는 패키지 | `uv sync` | 1 | 없음 | `.venv` 생성(패키지 없음) |
| N1 | lock 있음 | `npm ci` | 0 | 없음 | `node_modules` 생성 |
| N1b | 기존 `node_modules`에 표시 파일이 있음 | `npm ci` | 0 | 없음 | 표시 파일 삭제됨 |
| N2 | lock 없음 | `npm ci` | 1 | 없음 | 생성 안 됨 |
| N3 | manifest에 의존성 추가, lock 그대로 | `npm ci` | 1 | 없음 | 생성 안 됨 |
| N4 | 루트 `preinstall`, `postinstall`, `prepare` script가 파일을 고침 | `npm ci` | 0 | `src.txt` 수정, `generated.txt` 추가 | `node_modules` 생성 |
| N5 | 루트 `postinstall`이 exit 7 | `npm ci` | 7 | 없음 | `node_modules` 생성, 의존성 설치된 채 남음 |
| N6 | lock의 tarball URL이 404 | `npm ci` | 1 | 없음 | 생성 안 됨 |

## 새 worktree에서 uv sync와 npm ci

- 명령: lock을 commit한 저장소에서 새 worktree를 만들고 `uv sync`, `npm ci`를 실행했다.
- 관찰: 둘 다 exit 0이고 source와 lock은 바뀌지 않았다. `git status --porcelain --ignored`에는 `!! .venv/`, `!! node_modules/`만 나온다. 같은 worktree에서 `uv sync`를 다시 실행해도 변화가 없었다.
- `npm ci`는 기존 `node_modules`를 지우고 다시 설치한다. 미리 넣어 둔 `node_modules/probe-marker.txt`가 사라졌다.
- 결론: 확인됨. lock이 있고 manifest와 맞으면 두 명령 모두 source와 lock을 바꾸지 않고 ignored 산출물만 만든다. 의존성 산출물을 환경 manifest로 분리하는 [01-plan prepare](../01-plan.md#실행-순서와-prepare) 설계와 맞는다.

## lock 변경 여부 탐지

- 관찰: `uv sync`는 lock이 없으면 `uv.lock`을 만들고(U2), manifest와 lock이 다르면 `uv.lock`을 고친 뒤(U3) 둘 다 exit 0으로 끝난다. 전후 sha256 비교로 두 경우 모두 탐지됐다.
- `npm ci`는 이번 경우에서 lock을 바꾸지 않았다.
- 결론: 확인됨. `uv sync` 성공 exit만으로는 lock 변경을 알 수 없고 전후 비교가 필요하다. [D12](../05-open-decisions.md#d12-기존-lock-유지)의 "run 안 lock 변경에서 중단"은 전후 비교로 구현할 수 있다.

## lock 부재와 불일치 때의 동작

| 명령 | lock 없음 | manifest와 lock 불일치 |
|---|---|---|
| `uv sync` | lock 생성, exit 0 | lock 수정, exit 0 |
| `uv sync --locked` | exit 2, `Unable to find lockfile at uv.lock, but --locked was provided` | exit 1, `The lockfile at uv.lock needs to be updated, but --locked was provided` |
| `uv sync --frozen` | 시험 안 함 | exit 0, 오류 없이 예전 lock 기준으로 설치 |
| `npm ci` | exit 1, `npm error code EUSAGE`, lock이 있어야 한다는 메시지 | exit 1, `npm error code EUSAGE`, `Missing: is-odd@3.0.1 from lock file` |

- `uv sync --locked`는 lock 검사에 실패해도 `.venv`를 먼저 만든다(U2b, U3b).
- `uv sync --frozen`은 manifest에 새로 넣은 `idna`를 설치하지 않고 성공했다. 불일치를 알리지 않는다.
- 결론: 확인됨. `npm ci`는 부재와 불일치에서 스스로 실패한다. `uv sync`는 등록 명령 그대로 실행하면 부재와 불일치를 lock 변경으로 처리하고 성공한다. 따라서 D12의 중단은 오케스트레이터의 lock 전후 비교로만 걸린다. [02-config-spec prepare](../02-config-spec.md#prepare)는 등록 명령에 `--locked`를 몰래 붙이지 않는다고 정했다. 사용자가 `--frozen`을 등록하면 불일치가 성공으로 끝나므로 doctor의 manifest와 lock 일치 확인이 따로 필요하다. 이 처리는 문서에 없다.

## 실패 뒤 부분 환경

- U4: `uv lock`은 정적 metadata로 성공했고, `uv sync`가 build 단계에서 exit 1로 실패했다. stderr에 `Call to setuptools.build_meta.build_wheel failed`와 build backend 출력이 나온다. `.venv`는 남았고 함께 받을 six는 설치되지 않았다.
- U5: 해결 실패(`No solution found when resolving dependencies`)로 exit 1이다. `.venv`는 빈 상태로 남았다.
- N5: 루트 `postinstall`이 exit 7로 실패하면 `npm ci`도 exit 7이다. stderr에 `npm error command failed`와 실패한 script 명령이 나온다. `node_modules/is-number`는 설치된 채 남았다.
- N2, N3, N6: 설치 전 단계에서 실패해 `node_modules`가 생기지 않았다.
- 결론: 확인됨. 두 도구 모두 실패 뒤 의존성 폴더가 남을 수 있다. 특히 N5는 의존성이 다 설치된 것처럼 보이는 `node_modules`가 남는다. 폴더 존재로 준비 완료를 판정하면 안 되고, [R59](../04-review.md#r59-prepare-실패와-부분-의존성-상태의-재사용)대로 prepare-failed 기록으로 판정해야 한다. uv는 이번 경우 패키지를 하나도 설치하지 않았지만, 모든 실패에서 설치 전 상태를 유지하는지는 확인하지 않았다.

## install script가 source를 바꾸는지

- 명령: 루트 `package.json`에 `preinstall`, `postinstall`, `prepare` script를 두고 `npm ci`를 실행했다. 각 script는 `src.txt`에 줄을 붙이고, `postinstall`은 `generated.txt`도 만든다.
- 관찰: exit 0으로 끝났다. `src.txt`는 `source`, `preinstall`, `postinstall`, `prepare` 순서로 줄이 붙었고 `generated.txt`가 새로 생겼다. `git status`는 `M src.txt`, `?? generated.txt`를 출력했다. lock은 그대로다.
- uv: 이번 프로젝트는 `[tool.uv] package = false`라 프로젝트 자체를 build하지 않았다. 프로젝트를 package로 설치할 때 build backend가 source를 바꾸는 경우는 시험하지 않았다.
- 결론: 확인됨. `npm ci`는 루트 lifecycle script를 실행하고 그 script는 source를 바꿀 수 있다. 성공 exit와 별개로 source 전후 비교가 필요하다는 [R57](../04-review.md#r57-prepare-install-script와-source-변경의-부작용)과 맞는다.

## 문서와 다른 점, 문서에 없는 점

- `uv sync --frozen`은 manifest와 lock 불일치를 성공으로 처리한다. 등록 명령이 `--frozen`이면 lock 전후 비교로는 탐지되지 않는다(lock이 바뀌지 않음).
- `uv sync --locked`는 실패해도 `.venv`를 만든다. 실패 뒤 의존성 폴더 존재는 준비 상태의 근거가 아니다.
- `npm ci`는 실행할 때마다 기존 `node_modules`를 지운다. 재개 시 이전 부분 환경이 사라진다.

이 내용을 기획 문서와 결정에 반영할지는 #8에서 정한다.

## 남은 미확인

- Windows의 uv와 npm 11에서 같은 결과가 나오는지, lifecycle script의 `cmd.exe` 실행
- 프로젝트를 package로 설치하는 `uv sync`에서 build backend의 source 변경
- 의존성 패키지(루트가 아닌)의 install script가 source를 바꾸는 경우
- 네트워크 차단 상태의 prepare 실패 형태
