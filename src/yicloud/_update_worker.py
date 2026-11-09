"""Copied to a private temp directory before handoff. Standard library only.

Never imports the package being replaced. POSIX exec releases all old imports;
Windows waits for the Python process and its console launcher before touching files.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

VERIFY = """
import json, sys
from importlib.metadata import version
from pathlib import Path
from yicloud.skill_install import sync_existing
plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert Path(sys.prefix).resolve() == Path(plan["prefix"]).resolve(), "Environment changed"
assert version("yicloud-skill") == plan["version"], "Installed version differs from release"
rows = sync_existing(plan["paths"])
print(json.dumps({"version": version("yicloud-skill"), "skills": rows}))
"""


def wait_windows(pid):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, 60000) != 0:
                raise RuntimeError("Original CLI did not exit within 60 seconds")
        finally:
            kernel.CloseHandle(handle)
    elif ctypes.get_last_error() != 87:  # ERROR_INVALID_PARAMETER means it already exited.
        raise RuntimeError("Cannot wait for the original CLI to exit safely")


def windows_launcher_pid(pid):
    """Identify the distlib launcher while it is still alive; never wait on a shell."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise OSError("Cannot identify the parent launcher safely")
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
            raise OSError("Cannot identify the parent launcher safely")
        return pid if Path(buffer.value).name.lower() == "yicloud.exe" else None
    finally:
        kernel.CloseHandle(handle)


def run(plan, plan_path):
    if plan.get("wait_pid"):
        wait_windows(plan["wait_pid"])
        if plan.get("launcher_pid"):
            wait_windows(plan["launcher_pid"])
    # Save installer diagnostics separately. They can include private index URLs;
    # never copy them into normal CLI output or JSON error envelopes.
    log = plan_path.parent / "installer.log"
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(plan["command"], stdout=stream, stderr=stream, timeout=1800)
    if result.returncode:
        raise RuntimeError(
            f"Package installer failed (exit {result.returncode}); inspect private log: {log}. CLI/Skill update did not complete. Repair using the original environment's installer."
        )
    version_check = subprocess.run(
        [plan["python"], "-I", "-m", "yicloud", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if version_check.returncode:
        raise RuntimeError(
            "Updated CLI entry point failed; package may have changed. Repair the current environment."
        )
    verified = subprocess.run(
        [plan["python"], "-I", "-c", VERIFY, str(plan_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    if verified.returncode:
        # Skill error messages contain paths but no authentication state.
        raise RuntimeError(
            "Package installation finished, but version/Skill verification failed. "
            "Local edits were preserved. Run yicloud skill status and resolve conflicts. "
            "Details: " + verified.stderr[-4000:]
        )
    return json.loads(verified.stdout)


def main(plan_path):
    plan_path = Path(plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    try:
        result = {"ok": True, "data": dict(run(plan, plan_path), state="updated")}
        code = 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e:
        result = {
            "ok": False,
            "error": {
                "kind": "update",
                "message": str(e),
                "manual_command": plan.get("manual_command"),
            },
        }
        code = 1
    finally:
        Path(plan["lock"]).unlink(missing_ok=True)
    temporary = plan_path.parent / "result.tmp"
    temporary.write_text(json.dumps(result), encoding="utf-8")
    os.replace(temporary, plan_path.parent / "result.json")
    if plan["json"]:
        print(json.dumps(result), file=sys.stdout if code == 0 else sys.stderr)
    elif code:
        print("Error: " + result["error"]["message"], file=sys.stderr)
        if plan.get("manual_command"):
            print("Repair command: " + plan["manual_command"], file=sys.stderr)
    else:
        print(f"Updated yicloud to {result['data']['version']}; existing Skills verified.")
    if code == 0 and not plan.get("wait_pid"):
        shutil.rmtree(plan_path.parent)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
