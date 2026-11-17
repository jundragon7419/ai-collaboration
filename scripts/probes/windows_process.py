"""이슈 #5 Windows 프로세스와 명령 실행 확인 실험.

모델을 호출하지 않는다. Windows에서만 의미가 있다.
1. 시간 상한 뒤 자식 프로세스까지 종료되는지 (kill, taskkill /T, Job Object, CTRL_BREAK)
2. npm과 npx를 node로 직접 실행할 때 경로 탐색 (global prefix, nvm, Corepack)
3. cmd.exe /d /s /c wrapper의 인자 처리 (공백, 한글, 따옴표, 특수문자)
4. 출력 인코딩 (code page, Python, node, cmd, git)

실행: python scripts/probes/windows_process.py [--out 디렉터리]
결과: 기본 local-data/probes/windows-process/<시각>/results.json
표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import locale
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

IS_WINDOWS = os.name == "nt"

# 자식이 손자를 띄우고, 손자는 heartbeat 파일을 계속 갱신한다.
CHILD = r"""
import subprocess, sys, time
hb = sys.argv[1]
code = "import sys,time\nwhile True:\n    open(sys.argv[1],'w').write(str(time.time()))\n    time.sleep(0.2)\n"
p = subprocess.Popen([sys.executable, "-c", code, hb])
open(hb + ".pid", "w").write(str(p.pid))
while True:
    time.sleep(1)
"""


def heartbeat_alive(hb: Path, wait: float = 1.5) -> bool:
    """heartbeat 파일이 wait초 동안 갱신되면 손자가 살아 있다."""
    if not hb.exists():
        return False
    first = hb.stat().st_mtime
    time.sleep(wait)
    return hb.stat().st_mtime != first


def pid_alive(pid: int) -> bool:
    if IS_WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, errors="replace")
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_pid(pid: int) -> None:
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def start_tree(tmp: Path, name: str, creationflags: int = 0) -> tuple[subprocess.Popen[bytes], Path]:
    hb = tmp / f"{name}.hb"
    script = tmp / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(script), str(hb)], creationflags=creationflags)
    for _ in range(50):
        if hb.exists() and Path(str(hb) + ".pid").exists():
            break
        time.sleep(0.1)
    return proc, hb


def grandchild_pid(hb: Path) -> int | None:
    try:
        return int(Path(str(hb) + ".pid").read_text())
    except (OSError, ValueError):
        return None


def cleanup_tree(proc: subprocess.Popen[bytes] | None, hb: Path) -> None:
    """시험이 중간에 실패해도 자식과 손자 프로세스를 남기지 않는다."""
    if proc is not None and proc.poll() is None:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    gpid = grandchild_pid(hb)
    if gpid and pid_alive(gpid):
        kill_pid(gpid)


def probe_tree_kill(tmp: Path) -> dict[str, Any]:
    results: dict[str, Any] = {}

    # A. subprocess timeout 뒤 Popen.kill()만 호출
    proc, hb = start_tree(tmp, "a")
    try:
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        results["popen_kill_only"] = {"child_exit": proc.returncode, "grandchild_alive_after": heartbeat_alive(hb)}
    finally:
        cleanup_tree(proc, hb)

    # B. subprocess.run(timeout=)의 기본 동작
    hb_b = tmp / "b.hb"
    script = tmp / "child.py"
    try:
        try:
            subprocess.run([sys.executable, str(script), str(hb_b)], timeout=1.5)
            b_timeout = False
        except subprocess.TimeoutExpired:
            b_timeout = True
        results["subprocess_run_timeout"] = {"timeout_raised": b_timeout, "grandchild_alive_after": heartbeat_alive(hb_b)}
    finally:
        cleanup_tree(None, hb_b)

    if not IS_WINDOWS:
        results["note"] = "Windows가 아니어서 taskkill, Job Object, CTRL_BREAK 시험을 건너뜀"
        return results

    # C. taskkill /T /F
    proc, hb = start_tree(tmp, "c")
    try:
        r = subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, text=True, errors="replace")
        proc.wait(timeout=10)
        results["taskkill_tree"] = {
            "taskkill_exit": r.returncode, "stdout": r.stdout.strip()[:500], "grandchild_alive_after": heartbeat_alive(hb),
        }
    finally:
        cleanup_tree(proc, hb)

    # D. Job Object (KILL_ON_JOB_CLOSE)에 넣고 TerminateJobObject
    results["job_object"] = probe_job_object(tmp)

    # E. CREATE_NEW_PROCESS_GROUP + CTRL_BREAK_EVENT
    proc, hb = start_tree(tmp, "e", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    try:
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            proc.wait(timeout=5)
            e_exit: Any = proc.returncode
        except Exception as exc:  # noqa: BLE001
            e_exit = repr(exc)
        results["ctrl_break_group"] = {"child_exit": e_exit, "grandchild_alive_after": heartbeat_alive(hb)}
    finally:
        cleanup_tree(proc, hb)
    return results


def probe_job_object(tmp: Path) -> dict[str, Any]:
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    class BASIC(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("R", "W", "O", "RB", "WB", "OB")]

    class EXT(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    result: dict[str, Any] = {
        "note": "Popen 직후 job에 넣었다. 그 사이에 손자가 생기면 job 밖에 남을 수 있다",
    }
    hb = tmp / "d.hb"
    script = tmp / "child.py"
    job = None
    handle = None
    proc: subprocess.Popen[bytes] | None = None
    try:
        job = k32.CreateJobObjectW(None, None)
        if not job:
            result["error"] = f"CreateJobObjectW 실패: {ctypes.get_last_error()}"
            return result
        info = EXT()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        result["set_info_ok"] = bool(k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)))
        # 표준 Popen은 suspended로 만들 수 없어서 시작 직후 job에 넣는다.
        proc = subprocess.Popen([sys.executable, str(script), str(hb)])
        handle = k32.OpenProcess(0x0001 | 0x0100 | 0x1000, False, proc.pid)  # TERMINATE | SET_QUOTA | QUERY_LIMITED
        if not handle:
            result["error"] = f"OpenProcess 실패: {ctypes.get_last_error()}"
            return result
        result["assign_ok"] = bool(k32.AssignProcessToJobObject(job, handle))
        if not result["assign_ok"]:
            result["error"] = f"AssignProcessToJobObject 실패: {ctypes.get_last_error()}"
            return result
        for _ in range(50):
            if hb.exists():
                break
            time.sleep(0.1)
        result["terminate_ok"] = bool(k32.TerminateJobObject(job, 1))
        proc.wait(timeout=10)
        result["child_exit"] = proc.returncode
        result["grandchild_alive_after"] = heartbeat_alive(hb)
        return result
    finally:
        # 할당이나 종료가 실패해 job 밖에 남은 프로세스도 정리한다.
        cleanup_tree(proc, hb)
        if handle:
            k32.CloseHandle(handle)
        if job:
            k32.CloseHandle(job)


def run(argv: list[str], **kw: Any) -> dict[str, Any]:
    try:
        p = subprocess.run(argv, capture_output=True, timeout=60, **kw)
        return {"exit_code": p.returncode, "stdout_bytes": p.stdout, "stderr_bytes": p.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exit_code": None, "error": repr(exc), "stdout_bytes": b"", "stderr_bytes": b""}


def text(b: bytes) -> str:
    for enc in ("utf-8", "cp949"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def anonymize(s: str) -> str:
    for base, label in ((str(Path.home()), "<HOME>"),):
        s = s.replace(base, label).replace(base.replace("\\", "/"), label)
    user = os.environ.get("USERNAME") or os.environ.get("USER")
    if user and len(user) > 2:
        s = s.replace(user, "<USER>")
    return s


def probe_npm_paths() -> dict[str, Any]:
    res: dict[str, Any] = {}
    which = {name: shutil.which(name) for name in ("node", "npm", "npx", "corepack", "nvm", "volta", "fnm")}
    res["which"] = {k: anonymize(v) if v else None for k, v in which.items()}
    if IS_WINDOWS:
        w = run(["where", "npm"])
        res["where_npm"] = anonymize(text(w["stdout_bytes"])).splitlines()
        w = run(["where", "node"])
        res["where_node"] = anonymize(text(w["stdout_bytes"])).splitlines()
    res["env"] = {k: anonymize(os.environ[k]) for k in ("NVM_HOME", "NVM_SYMLINK", "VOLTA_HOME", "FNM_DIR", "COREPACK_HOME", "COREPACK_ENABLE_STRICT", "npm_config_prefix") if k in os.environ}
    node = which["node"]
    if not node:
        res["error"] = "node 없음"
        return res
    node_path = Path(node).resolve()
    res["node_resolved"] = anonymize(str(node_path))
    res["node_version"] = text(run([str(node_path), "--version"])["stdout_bytes"]).strip()
    candidates = {
        "next_to_node": node_path.parent / "node_modules" / "npm" / "bin",
    }
    npm_cmd = which["npm"]
    if npm_cmd:
        npm_dir = Path(npm_cmd).resolve().parent
        candidates["next_to_npm_cmd"] = npm_dir / "node_modules" / "npm" / "bin"
        try:
            head = Path(npm_cmd).read_text(encoding="utf-8", errors="replace")[:2000]
            res["npm_shim_mentions_corepack"] = "corepack" in head.lower()
            res["npm_shim_first_lines"] = anonymize(head).splitlines()[:12]
        except OSError as exc:
            res["npm_shim_read_error"] = repr(exc)
    prefix = run([npm_cmd, "prefix", "-g"]) if npm_cmd else None
    if prefix and prefix["exit_code"] == 0:
        gp = Path(text(prefix["stdout_bytes"]).strip())
        res["npm_prefix_g"] = anonymize(str(gp))
        candidates["global_prefix"] = gp / "node_modules" / "npm" / "bin"
    found = {}
    for label, d in candidates.items():
        entry: dict[str, Any] = {"dir": anonymize(str(d))}
        for js in ("npm-cli.js", "npx-cli.js"):
            f = d / js
            entry[js] = f.exists()
            if f.exists():
                r = run([str(node_path), str(f), "--version"])
                entry[js + "_version"] = text(r["stdout_bytes"]).strip()
                entry[js + "_exit"] = r["exit_code"]
        found[label] = entry
    res["js_entry_candidates"] = found
    if npm_cmd:
        r = run([npm_cmd, "--version"])
        res["npm_cmd_version"] = text(r["stdout_bytes"]).strip()
    if which["npx"]:
        r = run([which["npx"], "--version"])
        res["npx_cmd_version"] = text(r["stdout_bytes"]).strip()
    if which["corepack"]:
        r = run([which["corepack"], "--version"])
        res["corepack_version"] = text(r["stdout_bytes"]).strip()
    return res


ARG_CASES = [
    "plain",
    "with space",
    "한글 인자",
    'quote"inside',
    "trailing\\",
    "a&echo INJECTED_AMP",
    "a|echo INJECTED_PIPE",
    "%PATHEXT%",
    "caret^x",
    "(paren)",
    "!bang!",
    "",
]


# wrapper.cmd 안에 경로를 쓰지 않고 환경 변수로 넘긴다. 파일은 ASCII로만 쓰므로
# cmd의 code page(65001, 949)와 ANSI 인코딩이 달라도 내용이 깨지지 않는다.
WRAPPER_ENV: dict[str, str] = {}


def _wrapper_case(arg: str, argv: list[str] | None = None, cmdline: str | None = None) -> dict[str, Any]:
    """argv면 subprocess의 기본 변환(list2cmdline)을, cmdline이면 그 문자열을 그대로 CreateProcess에 넘긴다."""
    if cmdline is not None:
        try:
            p = subprocess.run(cmdline, capture_output=True, timeout=60, env=WRAPPER_ENV)
            r = {"exit_code": p.returncode, "stdout_bytes": p.stdout, "stderr_bytes": p.stderr}
        except (OSError, subprocess.TimeoutExpired) as exc:
            r = {"exit_code": None, "error": repr(exc), "stdout_bytes": b"", "stderr_bytes": b""}
        line = cmdline
    else:
        assert argv is not None
        r = run(argv, env=WRAPPER_ENV)
        line = subprocess.list2cmdline(argv)
    stdout = text(r["stdout_bytes"]).strip()
    try:
        received = json.loads(stdout.splitlines()[0]) if stdout else None
    except ValueError:
        received = None
    return {
        "sent": arg,
        "command_line": anonymize(line),
        "exit_code": r["exit_code"],
        "received": received,
        "same": received == [arg] if received is not None else False,
        "injected": "INJECTED" in stdout.replace(arg, ""),
        "stdout": anonymize(stdout)[:400],
        "stderr": anonymize(text(r["stderr_bytes"]))[:400],
    }


def probe_cmd_wrapper(tmp: Path) -> dict[str, Any]:
    if not IS_WINDOWS:
        return {"skipped": "Windows 아님"}
    dumper = tmp / "dump_args.py"
    dumper.write_text("import sys, json\nprint(json.dumps(sys.argv[1:], ensure_ascii=True))\n", encoding="utf-8")
    # 받은 인자를 그대로 Python에 넘긴다. gradlew.bat, mvnw.cmd의 "%*" 전달과 같은 방식이다.
    WRAPPER_ENV.clear()
    WRAPPER_ENV.update(os.environ, PROBE_PY=sys.executable, PROBE_DUMPER=str(dumper))
    body = b'@echo off\r\n"%PROBE_PY%" "%PROBE_DUMPER%" %*\r\n'
    spaced_dir = tmp / "dir with space 한글"
    spaced_dir.mkdir()
    spaced = spaced_dir / "wrapper.cmd"
    spaced.write_bytes(body)
    plain_dir = tmp / "plain"
    plain_dir.mkdir()
    plain = plain_dir / "wrapper.cmd"
    plain.write_bytes(body)

    variants: dict[str, Any] = {
        # A. argv 배열을 subprocess 기본 변환에 맡김. 경로에 공백이 있으면 /s가 맨 앞과 맨 끝 따옴표를 지운다.
        "argv_spaced_path": lambda a: _wrapper_case(a, argv=["cmd.exe", "/d", "/s", "/c", str(spaced), a]),
        # B. 같은 argv, 공백 없는 wrapper 경로
        "argv_plain_path": lambda a: _wrapper_case(a, argv=["cmd.exe", "/d", "/s", "/c", str(plain), a]),
        # C. /s가 지울 바깥 따옴표를 한 겹 더 씌운 명령 줄을 직접 만든다.
        "outer_quoted_spaced_path": lambda a: _wrapper_case(
            a, cmdline=f'cmd.exe /d /s /c ""{spaced}" {subprocess.list2cmdline([a])}"'
        ),
    }
    out: dict[str, Any] = {}
    for name, fn in variants.items():
        out[name] = [fn(arg) for arg in ARG_CASES]
    # D. .cmd를 cmd 없이 Popen에 argv로 넘김. Python이 내부적으로 cmd.exe를 거친다.
    out["direct_cmd_popen"] = [_wrapper_case(arg, argv=[str(spaced), arg]) for arg in ARG_CASES]
    out["summary"] = {
        name: {
            "same": sum(1 for c in cases if c["same"]),
            "total": len(cases),
            "injected": [c["sent"] for c in cases if c["injected"]],
            "different": [c["sent"] for c in cases if not c["same"]],
        }
        for name, cases in out.items()
    }
    return out


def probe_encoding(tmp: Path) -> dict[str, Any]:
    res: dict[str, Any] = {
        "locale_preferred": locale.getpreferredencoding(False),
        "sys_stdout_encoding": sys.stdout.encoding,
        "filesystem_encoding": sys.getfilesystemencoding(),
        "python_utf8_mode": sys.flags.utf8_mode,
        "env": {k: os.environ[k] for k in ("PYTHONIOENCODING", "PYTHONUTF8", "LANG") if k in os.environ},
    }
    sample = "한글 출력 확인"
    cases: dict[str, list[str]] = {
        "python_child_default": [sys.executable, "-c", f"print({sample!r})"],
        "node_console_log": [shutil.which("node") or "node", "-e", f"console.log({json.dumps(sample)})"],
    }
    if IS_WINDOWS:
        cases["cmd_chcp"] = ["cmd.exe", "/d", "/c", "chcp"]
        cases["cmd_echo"] = ["cmd.exe", "/d", "/c", "echo " + sample]
        cases["cmd_dir_korean_name"] = ["cmd.exe", "/d", "/c", "dir", "/b", str(tmp)]
    (tmp / "한글파일.txt").write_text("x", encoding="utf-8")
    env_utf8 = dict(os.environ, PYTHONIOENCODING="utf-8")
    cases_env = {"python_child_pythonioencoding_utf8": ([sys.executable, "-c", f"print({sample!r})"], env_utf8)}
    out = {}
    for name, argv in cases.items():
        r = run(argv)
        b = r["stdout_bytes"]
        out[name] = {"exit_code": r["exit_code"], "hex_head": b[:80].hex(), "utf8_ok": _decodes(b, "utf-8"),
                     "cp949_ok": _decodes(b, "cp949"), "as_text": anonymize(text(b)).strip()[:300]}
    for name, (argv, env) in cases_env.items():
        r = run(argv, env=env)
        b = r["stdout_bytes"]
        out[name] = {"exit_code": r["exit_code"], "hex_head": b[:80].hex(), "utf8_ok": _decodes(b, "utf-8"),
                     "cp949_ok": _decodes(b, "cp949"), "as_text": text(b).strip()[:300]}
    git = shutil.which("git")
    if git:
        repo = tmp / "enc-repo"
        repo.mkdir()
        # 상속 GIT_* (GIT_DIR, GIT_CONFIG_COUNT 등)가 남으면 다른 저장소를 건드리거나 외부 설정이 적용된다.
        genv = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        genv.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(tmp / "g.cfg"))
        (tmp / "g.cfg").write_text("[user]\n\tname = Probe\n\temail = p@example.invalid\n", encoding="utf-8")
        for argv, cwd in (([git, "init", "-q", str(repo)], tmp), ):
            if run(argv, cwd=cwd, env=genv)["exit_code"] != 0:
                raise RuntimeError("git init 실패")
        (repo / "한글.txt").write_text("x", encoding="utf-8")
        for argv in ([git, "add", "-A"], [git, "commit", "-q", "-m", "한글 커밋 메시지"]):
            if run(argv, cwd=repo, env=genv)["exit_code"] != 0:
                raise RuntimeError(f"{argv[1]} 실패")
        for name, argv in {
            "git_log_message": [git, "log", "-1", "--format=%s"],
            "git_status_quotepath_default": [git, "status", "--porcelain", "--untracked-files=all"],
            "git_ls_files_quotepath_default": [git, "ls-files"],
            "git_ls_files_z": [git, "ls-files", "-z"],
        }.items():
            r = run(argv, cwd=repo, env=genv)
            b = r["stdout_bytes"]
            out[name] = {"exit_code": r["exit_code"], "hex_head": b[:80].hex(), "utf8_ok": _decodes(b, "utf-8"),
                         "as_text": text(b).strip()[:300]}
    res["cases"] = out
    return res


def _decodes(b: bytes, enc: str) -> bool:
    try:
        b.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out or Path("local-data") / "probes" / "windows-process" / stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="aicollab-winproc-"))
    env_info = {
        "probe": "windows-process",
        "issue": 5,
        "started_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "is_windows": IS_WINDOWS,
    }
    checks: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for key, title, fn in (
        ("W1", "시간 상한 뒤 자식 프로세스까지 종료", lambda: probe_tree_kill(tmp)),
        ("W2", "npm과 npx를 node로 직접 실행할 때 경로 탐색", probe_npm_paths),
        ("W3", "cmd /d /s /c wrapper 인자 처리", lambda: probe_cmd_wrapper(tmp)),
        ("W4", "출력 인코딩", lambda: probe_encoding(tmp)),
    ):
        try:
            checks[key] = {"title": title, "observed": fn()}
        except Exception as exc:  # noqa: BLE001
            errors[key] = repr(exc)
    data = {"environment": env_info, "checks": checks, "script_errors": errors}
    (out_dir / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"결과: {out_dir / 'results.json'}")
    if errors:
        print(f"스크립트 오류: {errors}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
