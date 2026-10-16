"""Start tintja when a Cursor, Claude, or ChatGPT window is open.

This runs at Windows sign-in. A minimized window still counts as open.
tintja itself quits after the windows are closed, and this starts it again
the next time one opens.
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
TINT = HERE / "tint.py"
SHELLS = HERE / "shells.json"
MUTEX = "Local\\tintja"
SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GW_OWNER = 4
DWMWA_CLOAKED = 14

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = ctypes.c_bool
user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.GetWindow.restype = ctypes.c_void_p
user32.IsIconic.argtypes = [ctypes.c_void_p]
user32.IsIconic.restype = ctypes.c_bool
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.IsWindowVisible.restype = ctypes.c_bool
user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = ctypes.c_uint32
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = ctypes.c_bool
user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_ssize_t]
user32.EnumWindows.restype = ctypes.c_bool
dwmapi.DwmGetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_int


def process_path(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = ctypes.c_uint32(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        kernel32.QueryFullProcessImageNameW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)
        ]
        kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value
    finally:
        kernel32.CloseHandle(handle)


def watched_apps() -> dict[str, tuple[str, ...]]:
    apps = {
        "cursor.exe": (),
        "claude.exe": ("claude-code",),
        "chatgpt.exe": (),
    }
    try:
        if not SHELLS.exists() or SHELLS.stat().st_size > 65_536:
            return apps
        raw = json.loads(SHELLS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return apps
    parsed: dict[str, tuple[str, ...]] = {}
    for entry in (raw.get("apps") or [])[:32]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("process", "")).strip().lower()
        if not name or len(name) > 64:
            continue
        skips = entry.get("skip_if_path_contains") or []
        parsed[name] = tuple(str(skip).lower()[:80] for skip in list(skips)[:8])
    return parsed or apps


def shell_window_open() -> bool:
    apps = watched_apps()
    found = False

    def visit(hwnd, _lparam):
        nonlocal found
        if found or user32.GetWindow(hwnd, GW_OWNER):
            return True
        cloaked = ctypes.c_int()
        if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0:
            if cloaked.value:
                return True
        iconic = bool(user32.IsIconic(hwnd))
        if not iconic and not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        path = process_path(pid.value).lower().replace("/", "\\")
        name = path.rsplit("\\", 1)[-1]
        skips = apps.get(name)
        if skips is None or any(skip in path for skip in skips):
            return True
        if not iconic:
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            if rect.right - rect.left < 480 or rect.bottom - rect.top < 320:
                return True
        found = True
        return True

    callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_ssize_t)(visit)
    user32.EnumWindows(ctypes.cast(callback, ctypes.c_void_p), 0)
    return found


def tint_is_running() -> bool:
    kernel32.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    handle = kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def pythonw() -> str:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate if candidate.exists() else Path(sys.executable))


def start_tint() -> None:
    proc = subprocess.Popen(
        [pythonw(), str(TINT)],
        cwd=str(HERE),
        close_fds=True,
    )
    # Drop our handle to the child. tintja keeps running on its own.
    if getattr(proc, "_handle", None):
        kernel32.CloseHandle(proc._handle)
        proc._handle = None


def main() -> None:
    while True:
        if shell_window_open() and not tint_is_running():
            start_tint()
            time.sleep(2)
        time.sleep(2)


if __name__ == "__main__":
    main()
