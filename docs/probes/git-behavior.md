# Git 동작 확인 결과

이슈 #6의 확인 결과다. 대상은 worktree 생성과 정리, worktree 안 커밋의 hooks 실행, hook의 파일 변경과 tree 불일치 탐지, 사람 개입 서명 설정 탐지, 변경 없음 판정, push와 `gh pr create`의 push 동작이다.

## 실행 환경

| 항목 | 값 |
|---|---|
| 실행일 | 2026-11-17 |
| OS | Ubuntu 22.04.5 LTS (사용자 PC의 Linux VM, kernel 6.8.0) |
| Git | `git version 2.34.1` |
| Python | 3.10.12 |
| locale | `LANG=C.UTF-8` |
| gh | 없음 |
| 실행 명령 | `python3 scripts/probes/git_behavior.py --out <출력 폴더>` |

실험 저장소는 임시 디렉터리에 새로 만들었다. 실험용 Git 명령은 `GIT_`로 시작하는 상속 환경 변수를 모두 빼고, `GIT_CONFIG_GLOBAL`(임시 파일), `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`만 넣어 실행했다. `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`, `GIT_CONFIG_VALUE_*`, `GIT_CONFIG_PARAMETERS`는 명령 범위 설정이라 전역 설정 파일을 바꿔도 적용된다. 이 변수로 `core.hooksPath`를 넘기면 정리 전 스크립트에서는 외부 hook이 실험 저장소 commit마다 실행됐다. 정리한 변수는 이름만 `results.json`의 `inherited_git_env_removed`에 남긴다. 실험 저장소의 hooks 경로가 `.git/hooks`가 아니거나 준비 명령(init, add, commit, config, worktree add 등)이 실패하면 스크립트는 exit 1로 끝난다.

사용자 저장소와 전역 설정은 바꾸지 않았다. 사용자 서명 설정은 키 이름과 범위만 읽었다.

이번 실행 환경에는 `GIT_CONFIG_PARAMETERS`가 있었다. 정리 전 스크립트로 한 첫 실행과 정리 뒤 실행의 관찰은 commit SHA와 소요 시간을 빼면 G1부터 G6까지 같았다.

Windows에서는 실행하지 않았다. 기존 기록의 Windows Git은 `2.53.0.windows.2`([04-review C11](../04-review.md#명령-실행-기록))로 이번 실행 환경과 버전이 다르다. Windows의 hooks 실행(sh.exe), 경로 표기, 서명 프로그램 호출은 미확인이다. 같은 스크립트를 Windows에서 실행하면 같은 형식의 `results.json`이 나온다.

관찰 원본은 [fixtures/git-behavior/linux-git-2.34.1.json](fixtures/git-behavior/linux-git-2.34.1.json)에 있다. 임시 경로는 `<TMP>`로 바꿨다.

## 결과 요약

| ID | 항목 | 결론 |
|---|---|---|
| G1 | worktree 생성과 정리 | 확인됨 |
| G2 | worktree 안 커밋에서 hooks 실행 | 확인됨 |
| G3 | hook의 파일 변경과 tree 불일치 탐지 | 확인됨. commit-msg의 메시지 변경은 문서에 없는 사항 |
| G4 | 사람 개입 서명 설정 탐지 | 설정 탐지는 확인됨. 실제 서명 프로그램의 사람 개입 판별은 확인 불가 |
| G5 | 변경 없음 판정 | 확인됨 |
| G6 | push lease와 `gh pr create` | push lease는 확인됨. `gh pr create`는 실행 확인 불가, 공식 문서만 확인 |

## G1 worktree 생성과 정리

명령:

```shell
git worktree add -b aicollab/run-1 <wt> HEAD
git worktree list --porcelain
git worktree add -b aicollab/run-1 <wt2> HEAD   # 같은 branch 이름
git worktree remove <wt>                        # untracked 파일이 있는 상태
git worktree remove --force <wt>
git worktree prune -v
```

관찰:

- `worktree add -b`는 exit 0이다. `list --porcelain`은 `worktree <경로>`, `HEAD <SHA>`, `branch refs/heads/<이름>` 줄을 빈 줄로 구분해 출력한다.
- 이미 있는 branch 이름으로 `-b`를 주면 exit 255, `fatal: A branch named 'aicollab/run-1' already exists.`로 실패하고 기존 branch를 덮어쓰지 않는다.
- untracked 파일이 있는 worktree의 `remove`는 exit 128, `contains modified or untracked files, use --force to delete it`로 실패한다. `--force`를 주면 지워진다.
- worktree를 지워도 branch는 남는다.
- worktree 폴더를 Git 밖에서 지우면 `list --porcelain`에 `prunable gitdir file points to non-existent location` 줄이 붙고, `prune -v`가 `Removing worktrees/<이름>`을 출력하며 기록을 정리한다.

결론: 확인됨. 새 run_id branch가 이미 있으면 `-b`가 실패하므로 [01-plan 공개](../01-plan.md#공개)의 "branch 충돌을 덮어쓰지 않는다"와 맞는다. run worktree 정리에서 untracked 파일이 있으면 `remove`가 실패하므로 정리 단계는 이 실패를 처리해야 한다. 자동 `--force` 사용 여부는 문서에 정해져 있지 않다.

## G2 worktree 안 커밋에서 hooks 실행

명령: 원본 저장소의 `.git/hooks`에 `post-checkout`, `pre-commit`, `commit-msg`, `post-commit`을 두고, `git worktree add` 뒤 worktree 안에서 `git commit`과 `git commit --no-verify`를 실행했다.

관찰:

- `git worktree add`에서 `post-checkout`이 실행된다. 인자는 `0000000000000000000000000000000000000000 <HEAD SHA> 1`이고, 이때 `GIT_DIR`은 비어 있다.
- worktree 안 commit에서 `pre-commit`, `commit-msg`, `post-commit`이 순서대로 실행된다. 작업 디렉터리는 worktree이고 `GIT_DIR`은 `<원본>/.git/worktrees/<이름>`이다.
- worktree에서 `git rev-parse --git-path hooks`는 `<원본>/.git/hooks`를 가리킨다. worktree는 원본의 hooks를 공유한다.
- `--no-verify`로 commit하면 `pre-commit`과 `commit-msg`는 실행되지 않고 `post-commit`은 실행된다.

결론: 확인됨. [01-plan hooks](../01-plan.md#hooks-commit과-변경-없음)의 "worktree 생성 hooks"는 `post-checkout`으로 실제로 발생한다. [R47](../04-review.md#r47-자동-commit의-사용자-identity와-git-확장-실행-경계)의 "no-verify는 전체 hooks 차단이 아니다"와 맞는다.

## G3 hook의 파일 변경과 tree 불일치 탐지

방법: stage 뒤 `git write-tree`로 예상 tree를 얻고, commit 뒤 `git rev-parse HEAD^{tree}`와 비교했다. 작업 파일 변경은 `git status --porcelain`으로 확인했다.

| 경우 | commit exit | 예상 tree와 HEAD tree | commit 뒤 `status --porcelain` |
|---|---|---|---|
| pre-commit이 파일을 고치고 `git add` | 0 | 다름 | 비어 있음 |
| pre-commit이 작업 파일만 고침 | 0 | 같음 | `M src.txt` |
| post-commit이 작업 파일을 고침 | 0 | 같음 | `M src.txt` |
| pre-commit이 exit 3 | 1 | commit 없음, HEAD 그대로 | 해당 없음 |

- pre-commit 실패의 stderr에는 hook이 쓴 내용(`blocked by hook`)만 나오고 Git 자체 메시지는 없었다. 실패 원인 판정은 exit code와 HEAD 비교로 해야 한다.
- commit-msg hook은 메시지 파일을 고칠 수 있다. `-m original`로 commit했는데 최종 메시지는 `original` 뒤에 `Signed-off-by: hook` 줄이 붙었다.

결론: 확인됨. stage를 바꾸는 경우는 tree 비교로만 드러나고, stage 밖 변경과 post-commit 변경은 tree가 같아 status나 raw source 비교로만 드러난다. 두 검사가 모두 필요하다는 [01-plan hooks](../01-plan.md#hooks-commit과-변경-없음)의 "commit 후 실제 tree와 source를 다시 확인"과 맞는다. 세 경우 모두 commit은 이미 생성됐으므로 committed-unverified 기록 대상이다.

문서에 없는 사항: commit-msg hook이 commit 메시지를 바꿀 수 있다. 현재 문서는 tree와 source 재확인만 다룬다. 메시지 변경을 확인할지는 #8에서 정한다.

## G4 사람 개입 서명 설정 탐지

명령:

```shell
git config --show-origin --show-scope --get-regexp '^(commit|tag)\.gpgsign$|^gpg\.|^user\.signingkey$'
git config --type=bool --get commit.gpgsign
```

관찰:

- 탐지 명령은 `local	file:.git/config	commit.gpgsign true`처럼 범위, 출처 파일, 키, 값을 한 줄씩 출력한다. `--type=bool`은 `true`를 돌려준다. 해당 키가 하나도 없으면 exit 1이다.
- 실행 환경의 사용자 설정에는 서명 관련 키가 없었다(exit 1).
- `commit.gpgsign=true`와 exit 1로 끝나는 `gpg.program`: commit exit 128, `error: gpg failed to sign the data`, `fatal: failed to write commit object`. HEAD는 그대로다.
- 입력을 기다리는 `gpg.program`(stdin을 읽고 대기): 5초 시간 상한에서 git을 종료했다. commit은 생기지 않았고 `index.lock`도 남지 않았다. 서명 프로그램 자식 프로세스가 남았는지는 확인하지 않았다.
- `gpg.format=ssh`인데 `user.signingkey`가 없음: commit exit 128, `fatal: either user.signingkey or gpg.ssh.defaultKeyCommand needs to be configured`.

결론: 설정 탐지는 확인됨. 실패와 대기 모두 commit 전에 끝나 HEAD가 움직이지 않았다. 실제 gpg-agent, pinentry, ssh-agent, 사용자 지정 서명 프로그램이 사람 입력을 요구하는지는 확인 불가다. 개인 서명 설정으로 시험하지 않았다([04-review U07](../04-review.md#미확인-사실과-확인-방법)). 대기하는 서명 프로그램은 시간 상한으로만 끊을 수 있어서, git 종료 뒤 자식 프로세스 정리는 #5의 프로세스 트리 종료 결과와 함께 봐야 한다.

## G5 변경 없음 판정

방법: `.gitattributes`에 `* text=auto eol=lf`, `.gitignore`에 `node_modules/`, `.venv/`가 있는 저장소에서 `git add -A` 뒤 `git write-tree`를 base commit의 tree와 비교했다.

| 경우 | write-tree가 base tree와 같음 | `git diff --cached --quiet HEAD` exit | add 뒤 `status --porcelain` |
|---|---|---|---|
| 아무것도 안 바꿈 | 같음 | 0 | 비어 있음 |
| 바꿨다가 되돌림 | 같음 | 0 | 비어 있음 |
| ignored 의존성 폴더 생성 | 같음 | 0 | 비어 있음 |
| LF 파일을 CRLF로 다시 씀 | 같음 | 0 | 비어 있음 |

- 변경이 없는 상태에서 `git commit -m`은 exit 1이고 stdout에 `nothing to commit, working tree clean`을 출력한다.
- CRLF로 다시 쓴 경우 raw byte는 달라졌고, `git add` 전 `status --porcelain`은 `M src.txt`를 출력했다. `git add` 뒤에는 정규화로 tree가 base와 같아지고 status도 비었다.

결론: 확인됨. `git write-tree`와 base tree 비교로 변경 없음을 판정할 수 있고, ignored 의존성은 판정에 영향을 주지 않는다. [01-plan hooks](../01-plan.md#hooks-commit과-변경-없음)의 raw source snapshot과 expected_tree_oid 구분이 필요한 사례를 확인했다. stage 전 status만 보면 줄바꿈 정규화 때문에 변경이 있다고 잘못 판정할 수 있다. 변경 없음에서 `git commit`을 실행하면 exit 1이므로, 판정 뒤 commit을 호출하지 않는 순서가 맞다.

## G6 push lease와 `gh pr create`의 push 동작

push 명령(로컬 bare remote):

```shell
git push --porcelain --force-with-lease=refs/heads/aicollab/run-6: origin HEAD:refs/heads/aicollab/run-6
```

관찰:

- remote에 ref가 없을 때: exit 0, `*	HEAD:refs/heads/aicollab/run-6	[new branch]`.
- 새 commit을 같은 명령으로 다시 push: exit 1, `!	HEAD:refs/heads/aicollab/run-6	[rejected] (stale info)`, stderr `error: failed to push some refs to '<remote>'`. remote ref는 첫 push 그대로다.
- `git push --dry-run`은 exit 0이고 remote에 ref를 만들지 않았다.

`gh pr create`: 실행 환경에 gh가 없어 실행하지 않았다. 공식 문서([gh pr create](https://cli.github.com/manual/gh_pr_create))에 따르면 현재 branch가 remote에 다 push되지 않았으면 어디로 push할지 묻는 prompt가 나오고 fork도 선택지로 나온다. `--head`를 주면 fork와 push 동작을 건너뛴다. `--dry-run`은 PR을 만들지 않고 내용을 출력하지만 git 변경을 push할 수 있다고 적혀 있다. 권한이 없는 저장소에서는 fork를 자동으로 만들 수 있다.

결론: 생성 전용 lease(`--force-with-lease=<ref>:`)는 확인됨. [01-plan 공개](../01-plan.md#공개)의 "최초 새 ref는 부재 조건을 둔 생성 전용 lease" 구현안대로 동작한다. `gh pr create`의 push 동작은 공식 문서상 [R49](../04-review.md#r49-gh-인증과-pr-미리보기의-외부-실행-경계) 내용과 맞지만 실행 확인 불가다. Windows에서 gh가 있는 환경으로 스크립트를 다시 실행하면 `gh --version`과 `gh pr create --help`의 push 관련 줄을 기록한다. 실제 PR 생성 시험은 하지 않는다.

## 남은 미확인

- Windows Git 2.53에서 같은 결과가 나오는지
- 실제 서명 프로그램과 agent의 사람 개입 여부
- 시간 상한으로 git을 끊었을 때 서명 프로그램 자식 프로세스가 남는지
- 설치된 gh 버전의 `gh pr create` 실제 push 동작
