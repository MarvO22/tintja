"""Agent session state for tintja.

Claude Code and Cursor hooks run this file. It writes one small JSON file per
session into status/ saying which shelled app hosts the session, whether the
agent is working, and how full the session's context is. tintja reads those
files to draw the working dot and the usage fill on the taskbar icons.

The host app is found by walking up the parent processes until one matches
an app in shells.json, so a session in Cursor's terminal lights Cursor and a
session in the Claude app lights Claude.

The ChatGPT app here is OpenAI's Codex app, which needs no hooks: tintja
follows the session logs it already writes under ~/.codex/sessions.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATUS_DIR = HERE / "status"
SHELLS = HERE / "shells.json"

# Context window used for the usage fill. shells.json can override it with a
# top-level "context_window".
CONTEXT_WINDOW = 1_000_000
# A busy session that has gone this long without a hook is treated as done.
# Pressing Esc mid-turn fires no Stop hook.
BUSY_STALE = 20 * 60
# Sessions untouched for this long are forgotten.
FORGET_AFTER = 24 * 60 * 60

BUSY_EVENTS = {"UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure"}
DONE_EVENTS = {"Stop", "StopFailure", "Notification"}
END_EVENTS = {"SessionEnd"}
# Cursor's hook names. Its transcripts carry no token counts, so no usage.
CURSOR_BUSY = {"beforeSubmitPrompt", "postToolUse", "postToolUseFailure"}
CURSOR_DONE = {"stop"}
CURSOR_END = {"sessionEnd"}

CODEX_SESSIONS = Path.home() / ".codex" / "sessions"
CODEX_APP = "chatgpt.exe"

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def _shell_config() -> dict:
    try:
        if SHELLS.exists() and SHELLS.stat().st_size <= 65_536:
            return json.loads(SHELLS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _watched(raw: dict) -> dict[str, tuple[str, ...]]:
    apps: dict[str, tuple[str, ...]] = {}
    for entry in (raw.get("apps") or [])[:32]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("process", "")).strip().lower()
        if name:
            skips = entry.get("skip_if_path_contains") or []
            apps[name] = tuple(str(skip).lower()[:80] for skip in list(skips)[:8])
    return apps or {"cursor.exe": (), "claude.exe": ("claude-code",), "chatgpt.exe": ()}


def context_window() -> int:
    value = _shell_config().get("context_window")
    if isinstance(value, int) and 10_000 <= value <= 10_000_000:
        return value
    return CONTEXT_WINDOW


def _parents() -> dict[int, int]:
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return {}
    parents: dict[int, int] = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return parents


def _image_path(pid: int) -> str:
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)
    ]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = ctypes.c_uint32(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def host_app() -> str | None:
    """The shelled app this hook is running under, by .exe name."""
    apps = _watched(_shell_config())
    parents = _parents()
    pid = os.getppid()
    seen: set[int] = set()
    while pid and pid not in seen and len(seen) < 64:
        seen.add(pid)
        path = _image_path(pid).lower().replace("/", "\\")
        name = path.rsplit("\\", 1)[-1]
        skips = apps.get(name)
        if skips is not None and not any(skip in path for skip in skips):
            return name
        pid = parents.get(pid, 0)
    return None


def context_used(transcript: str) -> int | None:
    """Tokens in context after the latest reply, read from the transcript tail."""
    try:
        path = Path(transcript)
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - 512_000))
            tail = handle.read().decode("utf-8", "replace")
    except (OSError, ValueError):
        return None
    for line in reversed(tail.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("isSidechain"):
            continue
        usage = (record.get("message") or {}).get("usage")
        if not isinstance(usage, dict):
            continue
        return sum(int(usage.get(key) or 0) for key in (
            "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
        ))
    return None


def _safe_id(text: str) -> str:
    return "".join(c for c in text if c.isalnum() or c in "-_")[:80]


def record(payload: dict, started: float) -> None:
    session = _safe_id(str(payload.get("session_id") or payload.get("conversation_id") or ""))
    event = str(payload.get("hook_event_name") or "")
    if not session:
        return
    target = STATUS_DIR / f"{session}.json"
    if event in END_EVENTS or event in CURSOR_END:
        target.unlink(missing_ok=True)
        return
    if event in BUSY_EVENTS or event in CURSOR_BUSY:
        state = "busy"
    elif event in DONE_EVENTS or event in CURSOR_DONE:
        state = "done"
    else:
        return
    cursor = event[:1].islower()
    previous: dict = {}
    try:
        previous = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    # Hooks run in the background, so an older one can finish after a newer one.
    if float(previous.get("at") or 0) > started:
        return
    app = previous.get("app") or host_app()
    if not app:
        return
    used = None if cursor else context_used(str(payload.get("transcript_path") or ""))
    if used is None:
        used = previous.get("used")
    STATUS_DIR.mkdir(exist_ok=True)
    temp = target.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(json.dumps({"app": app, "state": state, "at": started, "used": used}), encoding="utf-8")
    # Windows refuses the swap while another process has the file open.
    try:
        for attempt in range(5):
            try:
                os.replace(temp, target)
                return
            except PermissionError:
                time.sleep(0.05 * (attempt + 1))
    finally:
        temp.unlink(missing_ok=True)


class CodexLogs:
    """Follows the Codex app's session logs.

    Each turn writes a task_started event, token_count events with the
    model's context window, and task_complete or turn_aborted at the end.
    Files are read from where the last read stopped.
    """

    RESCAN_SECONDS = 15
    FIRST_READ = 2_000_000

    def __init__(self) -> None:
        self._files: dict[Path, dict] = {}
        self._next_scan = 0.0

    def _rescan(self, now: float) -> None:
        self._next_scan = now + self.RESCAN_SECONDS
        try:
            paths = list(CODEX_SESSIONS.glob("*/*/*/*.jsonl"))
        except OSError:
            return
        live = set()
        for path in paths:
            try:
                if now - path.stat().st_mtime > FORGET_AFTER:
                    continue
            except OSError:
                continue
            live.add(path)
            self._files.setdefault(path, {"offset": None, "busy": False, "share": None})
        for path in list(self._files):
            if path not in live:
                del self._files[path]

    def _read(self, path: Path, state: dict, size: int) -> None:
        offset = state["offset"]
        if offset is None or offset > size:
            offset = max(0, size - self.FIRST_READ)
        with path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read(size - offset)
        end = chunk.rfind(b"\n")
        if end < 0:
            return
        state["offset"] = offset + end + 1
        for line in chunk[: end + 1].decode("utf-8", "replace").splitlines():
            if '"event_msg"' not in line:
                continue
            try:
                payload = json.loads(line).get("payload") or {}
            except (json.JSONDecodeError, AttributeError):
                continue
            kind = payload.get("type")
            if kind == "task_started":
                state["busy"] = True
            elif kind in ("task_complete", "turn_aborted"):
                state["busy"] = False
            elif kind == "token_count":
                info = payload.get("info") or {}
                used = (info.get("last_token_usage") or {}).get("input_tokens")
                window = info.get("model_context_window")
                if isinstance(used, int) and isinstance(window, int) and window > 0:
                    state["share"] = min(1.0, used / window)

    def sessions(self) -> list[tuple[str, bool, float | None, float]]:
        now = time.time()
        if now >= self._next_scan:
            self._rescan(now)
        found = []
        for path, state in self._files.items():
            try:
                stat = path.stat()
                if stat.st_size != state.get("size"):
                    self._read(path, state, stat.st_size)
                    state["size"] = stat.st_size
            except OSError:
                continue
            busy = state["busy"] and now - stat.st_mtime < BUSY_STALE
            found.append((CODEX_APP, busy, state["share"], stat.st_mtime))
        return found


CODEX = CodexLogs()


def _hook_sessions() -> list[tuple[str, bool, float | None, float]]:
    now = time.time()
    window = context_window()
    found = []
    try:
        files = list(STATUS_DIR.glob("*.json"))[:64]
    except OSError:
        return found
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            at = float(data.get("at") or 0)
            app = str(data.get("app") or "").lower()
        except (OSError, json.JSONDecodeError, ValueError, AttributeError):
            continue
        if now - at > FORGET_AFTER:
            path.unlink(missing_ok=True)
            continue
        if not app:
            continue
        busy = data.get("state") == "busy" and now - at < BUSY_STALE
        used = data.get("used")
        share = min(1.0, used / window) if isinstance(used, (int, float)) and used > 0 else None
        found.append((app, busy, share, at))
    return found


def app_states() -> dict[str, tuple[bool, float | None]]:
    """For each app with a session: (working, share of context used)."""
    states: dict[str, tuple[bool, float | None]] = {}
    latest: dict[str, float] = {}
    for app, busy, share, at in _hook_sessions() + CODEX.sessions():
        was_busy, last_share = states.get(app, (False, None))
        # The usage fill follows the session that moved most recently.
        if at >= latest.get(app, 0):
            latest[app] = at
            last_share = share if share is not None else last_share
        states[app] = (was_busy or busy, last_share)
    return states


def main() -> None:
    started = time.time()
    payload: object = {}
    try:
        # Cursor's input starts with a UTF-8 byte order mark.
        payload = json.loads(sys.stdin.buffer.read(1_000_000).decode("utf-8-sig") or "{}")
        if isinstance(payload, dict):
            record(payload, started)
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    finally:
        # Cursor waits on its hooks and reads a JSON answer. Claude Code
        # accepts an empty object.
        event = payload.get("hook_event_name") if isinstance(payload, dict) else None
        print(json.dumps({"continue": True} if event == "beforeSubmitPrompt" else {}), flush=True)


if __name__ == "__main__":
    main()
