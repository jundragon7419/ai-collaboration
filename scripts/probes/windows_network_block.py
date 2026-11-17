"""이슈 #30 check 네트워크 차단 방법 확인 실험.

관리자 권한 없이 쓸 수 있는 후보를 같은 도구 집합으로 시험한다.
1. baseline: 아무 차단 없음
2. proxy_env: HTTP_PROXY, HTTPS_PROXY, ALL_PROXY를 닫힌 로컬 포트로 지정
3. proxy_env_node: 2와 같고 NODE_USE_ENV_PROXY=1 추가
4. offline_flags: npm, pip, uv의 offline 설정
5. appcontainer: capability 없는 AppContainer에서 실행 (대조군으로 internetClient capability)
Windows Firewall은 규칙을 만들지 않고 관리자 여부와 profile 상태만 읽는다.

모델을 호출하지 않는다. 사용자 설정, 방화벽, 파일 ACL은 임시 폴더 밖에서 바꾸지 않는다.
AppContainer profile은 시험 뒤 지운다.

실행: python scripts/probes/windows_network_block.py [--out 디렉터리]
결과: 기본 local-data/probes/windows-network-block/<시각>/results.json
표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

IS_WINDOWS = os.name == "nt"
URL_PYPI = "https://pypi.org/simple/six/"
URL_NPM = "https://registry.npmjs.org/is-number"
HOST, PORT = "pypi.org", 443
DEAD_PROXY = "http://127.0.0.1:9"
TIMEOUT = 40


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        for enc in ("utf-8", "cp949"):
            try:
                return value.decode(enc)
            except UnicodeDecodeError:
                continue
        return value.decode("utf-8", errors="replace")
    return str(value)


def anonymize(text: str) -> str:
    home = str(Path.home())
    for v in (home, home.replace("\\", "/")):
        text = text.replace(v, "<HOME>")
    user = os.environ.get("USERNAME") or os.environ.get("USER")
    if user and len(user) > 2:
        text = text.replace(user, "<USER>")
    return text


def base_env() -> dict[str, str]:
    """상속 GIT_*와 기존 프록시, offline 설정을 뺀 환경. 각 후보를 이 위에 얹는다."""
    # 이름에 PROXY가 들어간 변수는 모두 뺀다(npm_config_noproxy, GLOBAL_AGENT_* 등도 접속 경로를 바꾼다).
    drop = {"PIP_NO_INDEX", "UV_OFFLINE", "NPM_CONFIG_OFFLINE", "NPM_CONFIG_PREFER_OFFLINE", "PIP_INDEX_URL",
            "UV_INDEX_URL", "UV_DEFAULT_INDEX", "NPM_CONFIG_REGISTRY"}
    env = {}
    for k, v in os.environ.items():
        up = k.upper()
        if up.startswith("GIT_") or "PROXY" in up or up in drop:
            continue
        env[k] = v
    return env


def variant_env(name: str, tmp: Path) -> dict[str, str]:
    env = base_env()
    # 캐시가 응답하지 않도록 후보마다 빈 캐시 폴더를 쓴다.
    env["npm_config_cache"] = str(tmp / "cache" / name / "npm")
    env["PIP_NO_CACHE_DIR"] = "1"
    env["UV_CACHE_DIR"] = str(tmp / "cache" / name / "uv")
    env["npm_config_update_notifier"] = "false"
    env["npm_config_fund"] = "false"
    env["npm_config_audit"] = "false"
    if name in ("proxy_env", "proxy_env_node"):
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env[k] = DEAD_PROXY
        env["NO_PROXY"] = ""
        env["no_proxy"] = ""
        env["npm_config_proxy"] = DEAD_PROXY
        env["npm_config_https_proxy"] = DEAD_PROXY
    if name == "proxy_env_node":
        env["NODE_USE_ENV_PROXY"] = "1"
    if name == "offline_flags":
        env["npm_config_offline"] = "true"
        env["PIP_NO_INDEX"] = "1"
        env["UV_OFFLINE"] = "1"
    return env


def tool_cases(tmp: Path) -> dict[str, list[str] | None]:
    py = sys.executable
    node = shutil.which("node")
    npm = shutil.which("npm")
    uv = shutil.which("uv")
    git = shutil.which("git")
    curl = shutil.which("curl.exe") or shutil.which("curl")
    dl = tmp / "pip-dl"
    return {
        "python_urllib": [py, "-c", f"import urllib.request;print(urllib.request.urlopen({URL_PYPI!r}, timeout=15).status)"],
        "python_raw_socket": [py, "-c", f"import socket;s=socket.create_connection(({HOST!r},{PORT}),15);print('connected');s.close()"],
        "node_fetch": [node, "-e", f"fetch({URL_NPM!r}).then(r=>console.log(r.status)).catch(e=>{{console.error(String(e.cause&&e.cause.code||e.message));process.exit(2)}})"] if node else None,
        "node_https": [node, "-e", f"require('https').get({URL_NPM!r},r=>{{console.log(r.statusCode);r.resume()}}).on('error',e=>{{console.error(e.code||e.message);process.exit(2)}})"] if node else None,
        "curl": [curl, "-sS", "-m", "15", "-o", os.devnull, "-w", "%{http_code}", URL_PYPI] if curl else None,
        "pip_download": [py, "-m", "pip", "download", "six==1.16.0", "--no-deps", "-d", str(dl), "--disable-pip-version-check", "--timeout", "10", "--retries", "0"],
        "npm_view": [npm, "view", "is-number", "version", "--fetch-retries", "0", "--fetch-timeout", "15000"] if npm else None,
        "uv_pip_dry_run": [uv, "pip", "install", "--dry-run", "--python", py, "six==1.16.0", "--no-cache"] if uv else None,
        "git_ls_remote": [git, "ls-remote", "https://github.com/git/git.git", "HEAD"] if git else None,
    }


def run_case(argv: list[str], env: dict[str, str], cwd: Path) -> dict[str, Any]:
    start = time.monotonic()
    try:
        p = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, timeout=TIMEOUT)
        res: dict[str, Any] = {"exit_code": p.returncode, "timed_out": False,
                               "stdout": anonymize(_as_text(p.stdout)).strip()[-400:],
                               "stderr": anonymize(_as_text(p.stderr)).strip()[-600:]}
    except subprocess.TimeoutExpired as exc:
        res = {"exit_code": None, "timed_out": True,
               "stdout": anonymize(_as_text(exc.stdout)).strip()[-400:],
               "stderr": anonymize(_as_text(exc.stderr)).strip()[-600:]}
    except OSError as exc:
        res = {"exit_code": None, "timed_out": False, "stdout": "", "stderr": repr(exc)}
    res["seconds"] = round(time.monotonic() - start, 2)
    res["reached_network"] = res["exit_code"] == 0
    return res


def probe_env_variants(tmp: Path) -> dict[str, Any]:
    cases = tool_cases(tmp)
    out: dict[str, Any] = {"targets": {"pypi": URL_PYPI, "npm": URL_NPM, "socket": f"{HOST}:{PORT}"}}
    for variant in ("baseline", "proxy_env", "proxy_env_node", "offline_flags"):
        env = variant_env(variant, tmp)
        results = {}
        for name, argv in cases.items():
            if argv is None:
                results[name] = {"skipped": "도구 없음"}
                continue
            shutil.rmtree(tmp / "pip-dl", ignore_errors=True)
            results[name] = run_case(argv, env, tmp)
        out[variant] = results
    out["summary"] = {
        v: {k: (r.get("reached_network") if "skipped" not in r else "없음") for k, r in out[v].items()}
        for v in ("baseline", "proxy_env", "proxy_env_node", "offline_flags")
    }
    return out


# ---- AppContainer ----

def probe_appcontainer(tmp: Path) -> dict[str, Any]:
    from ctypes import wintypes

    userenv = ctypes.WinDLL("userenv")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    adv = ctypes.WinDLL("advapi32", use_last_error=True)

    PSID = ctypes.c_void_p

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", PSID), ("Attributes", wintypes.DWORD)]

    class SECURITY_CAPABILITIES(ctypes.Structure):
        _fields_ = [("AppContainerSid", PSID), ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
                    ("CapabilityCount", wintypes.DWORD), ("Reserved", wintypes.DWORD)]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                    ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                    ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                    ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD), ("lpReserved2", ctypes.c_void_p),
                    ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                    ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

    userenv.CreateAppContainerProfile.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                                  ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(PSID)]
    userenv.CreateAppContainerProfile.restype = ctypes.c_long
    userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(PSID)]
    userenv.DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long
    userenv.DeleteAppContainerProfile.argtypes = [wintypes.LPCWSTR]
    userenv.DeleteAppContainerProfile.restype = ctypes.c_long
    adv.ConvertSidToStringSidW.argtypes = [PSID, ctypes.POINTER(wintypes.LPWSTR)]
    adv.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(PSID)]
    adv.FreeSid.argtypes = [PSID]
    k32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)]
    k32.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p,
                                              ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    k32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    k32.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL,
                                   wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_void_p,
                                   ctypes.POINTER(PROCESS_INFORMATION)]
    k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.LocalFree.argtypes = [ctypes.c_void_p]

    PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
    EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    CREATE_NO_WINDOW = 0x08000000
    SE_GROUP_ENABLED = 0x4
    HR_ALREADY_EXISTS = ctypes.c_long(0x800700B7).value

    name = f"aicollab.probe.netblock.{os.getpid()}"
    result: dict[str, Any] = {"profile_name": "aicollab.probe.netblock.<pid>"}
    sid = PSID()
    hr = userenv.CreateAppContainerProfile(name, "aicollab probe", "network block probe", None, 0, ctypes.byref(sid))
    result["create_profile_hresult"] = hex(hr & 0xFFFFFFFF)
    if hr == HR_ALREADY_EXISTS:
        hr = userenv.DeriveAppContainerSidFromAppContainerName(name, ctypes.byref(sid))
    if hr != 0 or not sid:
        result["error"] = "AppContainer profile을 만들지 못함"
        return result
    sid_str = wintypes.LPWSTR()
    adv.ConvertSidToStringSidW(sid, ctypes.byref(sid_str))
    sid_text = sid_str.value or ""
    k32.LocalFree(sid_str)

    work = tmp / "ac-work"
    work.mkdir()
    (work / "readme.txt").write_text("probe file\n", encoding="utf-8")
    # 임시 작업 폴더에만 AppContainer SID 접근을 허용한다.
    grant = subprocess.run(["icacls", str(work), "/grant", f"*{sid_text}:(OI)(CI)F", "/T"], capture_output=True)
    result["icacls_grant_exit"] = grant.returncode

    net_cap_sid = PSID()
    adv.ConvertStringSidToSidW("S-1-15-3-1", ctypes.byref(net_cap_sid))  # internetClient

    def run_in_container(cmdline: str, with_internet: bool, label: str) -> dict[str, Any]:
        out_file = work / f"{label}.txt"
        caps = (SID_AND_ATTRIBUTES * 1)()
        sc = SECURITY_CAPABILITIES()
        sc.AppContainerSid = sid
        if with_internet:
            caps[0].Sid = net_cap_sid
            caps[0].Attributes = SE_GROUP_ENABLED
            sc.Capabilities = ctypes.cast(caps, ctypes.POINTER(SID_AND_ATTRIBUTES))
            sc.CapabilityCount = 1
        size = ctypes.c_size_t(0)
        k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        attr = ctypes.create_string_buffer(size.value)
        if not k32.InitializeProcThreadAttributeList(attr, 1, 0, ctypes.byref(size)):
            return {"error": f"InitializeProcThreadAttributeList 실패 {ctypes.get_last_error()}"}
        try:
            if not k32.UpdateProcThreadAttribute(attr, 0, PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                                                 ctypes.byref(sc), ctypes.sizeof(sc), None, None):
                return {"error": f"UpdateProcThreadAttribute 실패 {ctypes.get_last_error()}"}
            si = STARTUPINFOEXW()
            si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
            si.lpAttributeList = ctypes.cast(attr, ctypes.c_void_p)
            pi = PROCESS_INFORMATION()
            full = f'cmd.exe /d /c "{cmdline} > "{out_file}" 2>&1"'
            buf = ctypes.create_unicode_buffer(full)
            ok = k32.CreateProcessW(None, buf, None, None, False, EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW,
                                    None, str(work), ctypes.byref(si), ctypes.byref(pi))
            if not ok:
                return {"error": f"CreateProcessW 실패 {ctypes.get_last_error()}"}
            waited = k32.WaitForSingleObject(pi.hProcess, TIMEOUT * 1000)
            timed_out = waited != 0
            if timed_out:
                k32.TerminateProcess(pi.hProcess, 1)
                k32.WaitForSingleObject(pi.hProcess, 5000)
            code = wintypes.DWORD()
            k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
            k32.CloseHandle(pi.hThread)
            k32.CloseHandle(pi.hProcess)
        finally:
            k32.DeleteProcThreadAttributeList(attr)
        text = ""
        if out_file.exists():
            text = _as_text(out_file.read_bytes())
        return {"command": anonymize(cmdline), "internet_capability": with_internet, "exit_code": code.value,
                "timed_out": timed_out, "output": anonymize(text).strip()[-500:]}

    curl = r"C:\Windows\System32\curl.exe"
    cases: dict[str, tuple[str, bool]] = {
        "read_granted_file": ("type readme.txt", False),
        "write_granted_dir": ("echo written> written.txt && type written.txt", False),
        "curl_no_capability": (f'"{curl}" -sS -m 15 -o NUL -w "%{{http_code}}" {URL_PYPI}', False),
        # 손자 프로세스: cmd 안에서 다시 cmd를 띄워 curl을 실행한다.
        "curl_grandchild_no_capability": (f'cmd.exe /d /c ""{curl}" -sS -m 15 -o NUL -w "%{{http_code}}" {URL_PYPI}"', False),
        "curl_with_internet_client": (f'"{curl}" -sS -m 15 -o NUL -w "%{{http_code}}" {URL_PYPI}', True),
        "python_start_no_capability": (f'"{sys.executable}" -c "print(1)"', False),
        # 허용하지 않은 사용자 홈 읽기. 폴더 이름을 남기지 않도록 개수만 센다.
        "read_user_home_no_grant": (f'dir "{Path.home()}" /b | find /c /v ""', False),
    }
    results = {}
    try:
        for label, (cmd, net) in cases.items():
            results[label] = run_in_container(cmd, net, label)
    finally:
        adv.FreeSid(net_cap_sid)
        adv.FreeSid(sid)
        result["delete_profile_hresult"] = hex(userenv.DeleteAppContainerProfile(name) & 0xFFFFFFFF)
    result["cases"] = results
    return result


def probe_firewall() -> dict[str, Any]:
    res: dict[str, Any] = {}
    try:
        res["is_admin"] = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as exc:  # noqa: BLE001
        res["is_admin_error"] = repr(exc)
    p = subprocess.run(["netsh", "advfirewall", "show", "currentprofile", "state"], capture_output=True)
    res["show_currentprofile_exit"] = p.returncode
    res["show_currentprofile"] = anonymize(_as_text(p.stdout)).strip()[:400]
    res["note"] = "규칙 추가는 시험하지 않았다. 시스템 설정을 바꾸기 때문이다."
    return res


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--only", default="env,appcontainer,firewall")
    args = parser.parse_args()
    only = set(args.only.split(","))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out or Path("local-data") / "probes" / "windows-network-block" / stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="aicollab-netblock-"))

    def version(argv: list[str]) -> str:
        exe = shutil.which(argv[0])
        if not exe:
            return "없음"
        try:
            p = subprocess.run([exe, *argv[1:]], capture_output=True, timeout=30)
            return _as_text(p.stdout or p.stderr).strip().splitlines()[0]
        except (OSError, subprocess.TimeoutExpired, IndexError):
            return "확인 실패"

    env_info = {
        "probe": "windows-network-block",
        "issue": 30,
        "started_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "node": version(["node", "--version"]),
        "npm": version(["npm", "--version"]),
        "uv": version(["uv", "--version"]),
        "git": version(["git", "--version"]),
        "curl": version(["curl.exe", "--version"]) if IS_WINDOWS else version(["curl", "--version"]),
        "inherited_proxy_env_names": sorted(k for k in os.environ if "PROXY" in k.upper()),
    }
    checks: dict[str, Any] = {}
    errors: dict[str, str] = {}
    steps = [("N1", "env", "프록시 환경 변수와 offline 설정", lambda: probe_env_variants(tmp))]
    if IS_WINDOWS:
        steps += [("N2", "appcontainer", "AppContainer", lambda: probe_appcontainer(tmp)),
                  ("N3", "firewall", "Windows Firewall 상태와 권한", probe_firewall)]
    for key, flag, title, fn in steps:
        if flag not in only:
            continue
        try:
            checks[key] = {"title": title, "observed": fn()}
        except Exception as exc:  # noqa: BLE001
            errors[key] = repr(exc)
    data = {"environment": env_info, "checks": checks, "script_errors": errors}
    (out_dir / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run(["icacls", str(tmp / "ac-work"), "/reset", "/T"], capture_output=True) if IS_WINDOWS and (tmp / "ac-work").exists() else None
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"결과: {out_dir / 'results.json'}")
    if errors:
        print(f"스크립트 오류: {errors}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
