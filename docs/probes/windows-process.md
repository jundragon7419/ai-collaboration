# Windows 프로세스와 명령 실행 확인 결과

이슈 #5의 확인 결과다. 대상은 시간 상한 뒤 자식 프로세스까지 종료, npm과 npx를 node로 직접 실행할 때의 경로 탐색, `cmd /d /s /c` wrapper의 인자 처리, 출력 인코딩이다. 모델은 호출하지 않았다.

## 실행 환경

| 항목 | 값 |
|---|---|
| 실행일 | 2026-11-17 |
| OS | Windows 11 (10.0.26200), 사용자 PC |
| Python | 3.13.15, locale 기본 인코딩 `cp949`, UTF-8 mode 꺼짐 |
| Node | v24.14.0 (`C:\Program Files\nodejs\node.exe`) |
| npm, npx | 11.9.0 |
| Corepack | 0.34.6 |
| Git | `2.53.0.windows.2` |
| 실행 명령 | `python scripts/probes/windows_process.py --out <출력 폴더>` |
| 실행 방법 | 탐색기에서 실행한 `.cmd`가 `chcp 65001` 뒤 스크립트를 실행. 콘솔 code page 65001 |

같은 스크립트를 두 번 실행했다. 첫 실행에서 wrapper 인자 처리(W3)가 경로의 공백 때문에 전부 실패해, 비교 방식을 추가한 스크립트로 다시 실행했다. W1, W2, W4는 두 실행의 결과가 같았다. 이 문서와 fixture는 두 번째 실행 결과다.

관찰 원본은 [fixtures/windows-process/windows-11-python-3.13.15.json](fixtures/windows-process/windows-11-python-3.13.15.json)에 있다. 홈 경로는 `<HOME>`, 사용자 이름은 `<USER>`로 바꿨다.

## 결과 요약

| ID | 항목 | 결론 |
|---|---|---|
| W1 | 시간 상한 뒤 자식 프로세스까지 종료 | 확인됨. `Popen.kill()`과 `subprocess.run(timeout=)`은 손자를 남김 |
| W2 | npm과 npx를 node로 직접 실행할 때 경로 탐색 | 이 PC의 기본 설치는 확인됨. nvm, Volta, fnm, Corepack shim 환경은 확인 불가 |
| W3 | `cmd /d /s /c` wrapper 인자 처리 | 다름. 공백 있는 wrapper 경로를 argv로 넘기면 실행되지 않고 명령 주입이 생김 |
| W4 | 출력 인코딩 | 확인됨. 자식 프로세스마다 인코딩이 다름 |

## W1 시간 상한 뒤 자식 프로세스까지 종료

방법: 자식 Python이 손자 Python을 띄우고, 손자는 0.2초마다 heartbeat 파일을 갱신한다. 종료 방법별로 자식을 끝낸 뒤 1.5초 동안 heartbeat가 갱신되면 손자가 살아 있다고 본다.

| 종료 방법 | 자식 exit | 손자 생존 |
|---|---|---|
| `Popen.wait(timeout)` 뒤 `Popen.kill()` | 1 | 살아 있음 |
| `subprocess.run(timeout=1.5)` | `TimeoutExpired` | 살아 있음 |
| `taskkill /T /F /PID <자식>` | 기록 안 함 | 종료됨 |
| Job Object(`KILL_ON_JOB_CLOSE`)에 넣고 `TerminateJobObject` | 1 | 종료됨 |
| `CREATE_NEW_PROCESS_GROUP`으로 시작, `CTRL_BREAK_EVENT` | 3221225786 (0xC000013A) | 종료됨 |

- `taskkill /T`의 stdout은 `SUCCESS: The process with PID ... (child process of PID ...) has been terminated.`를 프로세스마다 한 줄씩 출력했다.
- Job Object는 `Popen` 직후 자식을 job에 넣었다. 그 사이에 자식이 손자를 만들면 손자는 job 밖에 남을 수 있다. 이번 실행에서는 손자가 job 안에 들어갔다. 이 틈을 없애려면 suspended 상태로 만든 뒤 job에 넣어야 하지만 표준 `Popen`으로는 하지 않았다.
- `CTRL_BREAK_EVENT`는 자식이 신호를 처리하지 않을 때 그룹 전체가 끝났다. 신호를 무시하는 프로그램에서의 동작은 확인하지 않았다.

결론: 확인됨. Python 표준 timeout과 `kill()`만으로는 [R27](../04-review.md#r27-windows-timeout과-ctrlc의-자식-프로세스-처리-누락)이 지적한 대로 손자 프로세스가 남는다. `taskkill /T`, Job Object, 프로세스 그룹과 CTRL_BREAK는 이번 구성에서 손자까지 끝냈다. 어느 방식을 쓸지는 문서에 정해져 있지 않다.

## W2 npm과 npx를 node로 직접 실행할 때 경로 탐색

관찰:

- PATH의 `node`는 `C:\Program Files\nodejs\node.exe`, `npm`과 `npx`는 같은 폴더의 `npm.CMD`, `npx.CMD`다. `where npm`은 확장자 없는 `npm`과 `npm.cmd`를 모두 출력했다.
- `npm.cmd`는 npm이 만든 launcher로, 자기 폴더의 `node.exe`와 `node_modules\npm\bin\npm-cli.js`를 쓴다. Corepack을 언급하지 않는다.
- node 옆 `node_modules\npm\bin`의 `npm-cli.js`와 `npx-cli.js`를 `node.exe`로 직접 실행하면 둘 다 exit 0, 버전 11.9.0이다. `npm.cmd --version`, `npx.cmd --version`과 같다.
- `npm prefix -g`는 `<HOME>\AppData\Roaming\npm`이고, 그 아래에는 `npm-cli.js`가 없다. 전역 prefix에 npm을 따로 설치하지 않은 상태다.
- `nvm`, `volta`, `fnm`은 PATH에 없고 관련 환경 변수(`NVM_HOME`, `NVM_SYMLINK`, `VOLTA_HOME`, `FNM_DIR`, `COREPACK_HOME`)도 없다. `corepack`은 0.34.6이 있지만 npm을 shim으로 바꾸지 않았다.

결론: 이 PC의 기본 Node 설치에서는 "node 옆 `npm-cli.js`" 조합이 `npm.cmd`와 같은 버전을 실행한다. [02-config-spec Windows 실행과 wrapper](../02-config-spec.md#windows-실행과-wrapper)의 현재 PC 기록(Node v24.14.0, npm 11.9.0)과 같다. nvm, Volta, fnm, Corepack shim이 있는 환경의 resolver는 이 PC에 해당 도구가 없어 확인 불가다([R63](../04-review.md#r63-npm-진입점과-version-manager-경로-탐색)).

## W3 `cmd /d /s /c` wrapper 인자 처리

방법: 받은 인자를 `%*`로 Python에 넘겨 JSON으로 출력하는 `wrapper.cmd`를 만들었다. gradlew.bat, mvnw.cmd가 인자를 넘기는 방식과 같다. wrapper는 `dir with space 한글` 폴더와 `plain` 폴더 두 곳에 두었다. 인자 12개를 네 방식으로 넘기고, 받은 인자가 보낸 인자와 같은지와 `INJECTED`가 출력됐는지 기록했다.

| 방식 | 명령 줄 | 같음 | 명령 주입 |
|---|---|---|---|
| A | argv `["cmd.exe","/d","/s","/c",<공백 있는 경로>,arg]`를 `subprocess` 기본 변환으로 | 0/12 | `a&echo INJECTED_AMP` |
| B | argv `["cmd.exe","/d","/s","/c",<공백 없는 경로>,arg]` | 10/12 | 없음 |
| C | 문자열 `cmd.exe /d /s /c ""<공백 있는 경로>" <인자>"` 직접 구성 | 10/12 | 없음 |
| D | argv `[<공백 있는 경로>, arg]`로 `.cmd`를 직접 실행 | 10/12 | 없음 |

A의 관찰:

- 12개 모두 wrapper가 실행되지 않았다. stderr는 `'<HOME>\AppData\Local\Temp\...\dir' is not recognized as an internal or external command`다. `/s`가 명령 줄의 첫 따옴표와 마지막 따옴표를 지워, 경로가 공백에서 잘렸다.
- 그 상태에서 `a&echo INJECTED_AMP`는 exit 0이고 stdout이 `INJECTED_AMP`였다. 인자를 감싼 따옴표가 짝이 어긋나 `&` 뒤가 별도 명령으로 실행됐다.
- `a|echo INJECTED_PIPE`는 exit 255로 끝났고 주입 출력은 없었다.

B, C, D의 공통 관찰:

- 공백, 한글, 큰따옴표, 끝의 역슬래시, `&`, `|`, 괄호, `!`, 빈 문자열은 그대로 전달됐다.
- `%PATHEXT%`는 세 방식 모두 환경 변수 값(`.COM;.EXE;.BAT;...`)으로 바뀌어 전달됐다. 따옴표 안에서도 cmd가 `%변수%`를 확장한다.
- `caret^x`는 세 방식 모두 `caretx`로 전달됐다. 따옴표 없이 넘어간 `^`는 cmd의 escape 문자로 처리된다.
- `!bang!`은 그대로 전달됐다. delayed expansion이 기본으로 꺼져 있기 때문이다.

결론: 문서와 다름. [02-config-spec Windows 실행과 wrapper](../02-config-spec.md#windows-실행과-wrapper)는 "고정 경로와 고정 인자로 cmd.exe /d /s /c 실행을 허용"하고 공백과 특수문자 처리를 doctor 시험 대상으로 두었다. 실제로는 argv 배열을 그대로 `subprocess`에 넘기면 wrapper 경로에 공백이 있을 때 실행 자체가 실패하고 인자 주입까지 생긴다. 바깥 따옴표를 한 겹 더 씌운 명령 줄을 직접 만들거나 `.cmd`를 argv로 직접 실행하면 실행은 되지만, `%변수%` 확장과 `^` 제거는 어느 방식으로도 막지 못했다. "외부 명령은 argv 배열로 실행한다"는 [AGENTS.md](../../AGENTS.md) 규칙만으로는 cmd wrapper의 인자를 그대로 전달한다고 보장할 수 없다. wrapper 호출 방식과 `%`, `^`가 들어간 인자를 어떻게 다룰지는 #8에서 정한다.

## W4 출력 인코딩

한글 문자열 `한글 출력 확인`을 출력하게 하고 stdout byte를 기록했다. 실행 콘솔의 code page는 65001이었다.

| 출력 | 인코딩 | 비고 |
|---|---|---|
| Python 자식, 기본 | cp949 (`c7d1b1db...`) | 부모와 같은 locale 기본값. UTF-8로 해석 불가 |
| Python 자식, `PYTHONIOENCODING=utf-8` | UTF-8 | |
| `node -e console.log` | UTF-8 | |
| `cmd /c echo` | UTF-8 | `chcp` 출력이 `Active code page: 65001` |
| `cmd /c dir /b`의 한글 파일 이름 | UTF-8 | |
| `git log -1 --format=%s`의 한글 메시지 | UTF-8 | |
| `git ls-files`의 한글 경로 | ASCII 8진 escape | `"\355\225\234\352\270\200.txt"`. `core.quotePath` 기본값 |
| `git ls-files -z`의 한글 경로 | UTF-8, NUL 구분 | |

결론: 확인됨. 같은 실행 안에서도 자식 프로세스마다 인코딩이 달랐다. Python 자식은 locale 기본값인 cp949로 출력했고 node와 git은 UTF-8이었다. 출력 해석을 한 인코딩으로 고정하면 일부가 깨진다. git 경로는 `-z`를 써야 escape 없이 받을 수 있다. 콘솔 code page가 기본값(949)일 때 cmd 출력은 이번에 확인하지 않았다.

## 문서와 다른 점, 문서에 없는 점

- 공백 있는 wrapper 경로를 argv로 `cmd /d /s /c`에 넘기면 실행이 실패하고 `&` 인자가 명령으로 실행된다.
- cmd wrapper를 거치면 `%변수%`가 확장되고 `^`가 사라진다. 바깥 따옴표를 씌워도 같다.
- Python 표준 timeout과 `kill()`은 손자 프로세스를 남긴다. 문서에 트리 종료 방식이 정해져 있지 않다.
- 자식 프로세스 출력 인코딩이 도구마다 다르다.

이 내용을 기획 문서와 결정에 반영할지는 #8에서 정한다.

## 남은 미확인

- nvm, Volta, fnm, Corepack shim 환경의 npm 진입점
- 콘솔 code page 949에서의 cmd 출력
- 신호를 무시하는 프로그램에서 CTRL_BREAK 동작, suspended 생성 뒤 Job Object 할당
- WSL2 runtime의 같은 항목
