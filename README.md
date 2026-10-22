# tintja

Light click-through frames and taskbar tints so desktop windows are easy to tell apart, plus a taskbar dot that shows when Claude Code, Cursor, or Codex is working, and how full the session is.

| App | Shell | Name type |
| --- | --- | --- |
| Cursor | Purple | Segoe UI |
| Claude | Blue | Georgia |
| ChatGPT | Green | Cascadia Mono |

Red and orange are in the palette too. The script asks Windows which windows belong to those apps and where they are, then draws a shell on top. Each app's taskbar icon gets a wash in its color. Clicks pass through. It does not read the screen, take screenshots, or record anything. The agent status reads only state events and token counts from each session's own log.

## Run

Windows and Python 3.

```
python tint.py
```

`Ctrl+Alt+Shift+Q` quits. `Ctrl+Alt+Shift+I` toggles the taskbar icon tint.

## Startup

`launch.py` is started when you sign in to Windows. When a Cursor, Claude, or ChatGPT window is open, it starts tintja if the shells are not already up. Minimized windows keep tintja running. Once every one of those windows is closed, tintja quits. The Claude Code helper is ignored.

## Agent status

When an agent session runs in one of the shelled apps, that app's taskbar icon shows two more marks:

- A half circle on the bottom edge. It glows white while the agent is working and cools to a darker shade of the icon tint when the turn ends or the agent is waiting on you.
- A lighter fill from the left edge that grows with how full the session's context is. With several sessions in one app, it follows the one that moved most recently.

| App | Working dot | Context fill | Source |
| --- | --- | --- | --- |
| Claude (Claude Code) | Yes | Yes | Hooks in `~/.claude/settings.json` |
| Cursor (agent) | Yes | No | Hooks in `~/.cursor/hooks.json` |
| ChatGPT (Codex app) | Yes | Yes | Its own session logs in `~/.codex/sessions` |

The hooks run `status.py`, which writes one small file per session into `status/`, and tintja reads them. It works out the host app by walking up its parent processes, so a Claude Code session in Cursor's terminal lights Cursor. Cursor's transcripts carry no token counts, so Cursor gets the dot only. The ChatGPT app here is OpenAI's Codex app, and tintja follows the turn and token events it already logs, so it needs no setup. Its fill uses the context window each Codex model reports. Plain Claude chat does not report anything.

### Claude Code hooks

Add these to `~/.claude/settings.json`, with your own paths to Python and `status.py`. Merge them into any `hooks` you already have.

```json
"hooks": {
  "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "C:\\Python314\\python.exe", "args": ["D:\\DEV\\app-tint\\status.py"], "async": true, "timeout": 10 }] }],
  "PostToolUse":      [{ "hooks": [{ "type": "command", "command": "C:\\Python314\\python.exe", "args": ["D:\\DEV\\app-tint\\status.py"], "async": true, "timeout": 10 }] }],
  "Notification":     [{ "hooks": [{ "type": "command", "command": "C:\\Python314\\python.exe", "args": ["D:\\DEV\\app-tint\\status.py"], "async": true, "timeout": 10 }] }],
  "Stop":             [{ "hooks": [{ "type": "command", "command": "C:\\Python314\\python.exe", "args": ["D:\\DEV\\app-tint\\status.py"], "async": true, "timeout": 10 }] }],
  "StopFailure":      [{ "hooks": [{ "type": "command", "command": "C:\\Python314\\python.exe", "args": ["D:\\DEV\\app-tint\\status.py"], "async": true, "timeout": 10 }] }],
  "SessionEnd":       [{ "hooks": [{ "type": "command", "command": "C:\\Python314\\python.exe", "args": ["D:\\DEV\\app-tint\\status.py"], "timeout": 5 }] }]
}
```

### Cursor hooks

Put this in `~/.cursor/hooks.json`. Cursor waits for each hook, and `status.py` answers with the JSON Cursor expects.

```json
{
  "version": 1,
  "hooks": {
    "beforeSubmitPrompt": [{ "command": "C:\\Python314\\python.exe D:\\DEV\\app-tint\\status.py", "timeout": 5 }],
    "postToolUse":        [{ "command": "C:\\Python314\\python.exe D:\\DEV\\app-tint\\status.py", "timeout": 5 }],
    "postToolUseFailure": [{ "command": "C:\\Python314\\python.exe D:\\DEV\\app-tint\\status.py", "timeout": 5 }],
    "stop":               [{ "command": "C:\\Python314\\python.exe D:\\DEV\\app-tint\\status.py", "timeout": 5 }],
    "sessionEnd":         [{ "command": "C:\\Python314\\python.exe D:\\DEV\\app-tint\\status.py", "timeout": 5 }]
  }
}
```

### Notes

Claude Code's fill assumes a 1,000,000-token context window. Set `"context_window": 200000` (or another number) at the top level of `shells.json` to change it. If you press Esc in the middle of a Claude Code turn, no stop event fires, so the dot keeps glowing for up to 20 minutes.

## Change a shell

Edit `shells.json`. A color can be `blue`, `red`, `orange`, `purple`, or `green`, or a hex code like `#2E6BFF`. You can change the hex behind a name, point an app at a different name, change its typeface, or add another app by its `.exe` name. Save the file and the shells update on their own.
