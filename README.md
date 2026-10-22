# tintja

Light click-through frames and taskbar tints so desktop windows are easy to tell apart, plus a taskbar dot that shows when Claude Code is working and how full its session is.

| App | Shell | Name type |
| --- | --- | --- |
| Cursor | Purple | Segoe UI |
| Claude | Blue | Georgia |
| ChatGPT | Green | Cascadia Mono |

Red and orange are in the palette too. The script asks Windows which windows belong to those apps and where they are, then draws a shell on top. Each app's taskbar icon gets a wash in its color. Clicks pass through. It does not read the screen, take screenshots, or record anything. The Claude Code status reads token counts from the session's own transcript and nothing else.

## Run

Windows and Python 3.

```
python tint.py
```

`Ctrl+Alt+Shift+Q` quits. `Ctrl+Alt+Shift+I` toggles the taskbar icon tint.

## Startup

`launch.py` is started when you sign in to Windows. When a Cursor, Claude, or ChatGPT window is open, it starts tintja if the shells are not already up. Minimized windows keep tintja running. Once every one of those windows is closed, tintja quits. The Claude Code helper is ignored.

## Claude Code status

When a Claude Code session runs inside one of the shelled apps, its taskbar icon shows two more marks:

- A half circle on the bottom edge. It glows white while Claude is working and cools to a darker shade of the icon tint when the turn ends or Claude is waiting on you.
- A lighter fill from the left edge that grows with how full the session's context is. With several sessions in one app, it follows the one that moved most recently.

Claude Code hooks in `~/.claude/settings.json` run `status.py` when a prompt is sent, after each tool, and when Claude stops or asks for something. `status.py` writes one small file per session into `status/`, and tintja reads them. It works out the host app by walking up its parent processes, so a session in Cursor's terminal lights Cursor. Plain Claude chat and ChatGPT do not report anything.

To turn it on, add these hooks to `~/.claude/settings.json`, with your own paths to Python and `status.py`. Merge them into any `hooks` you already have.

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

The fill assumes a 1,000,000-token context window. Set `"context_window": 200000` (or another number) at the top level of `shells.json` to change it. If you press Esc in the middle of a turn, no stop event fires, so the dot keeps glowing for up to 20 minutes.

## Change a shell

Edit `shells.json`. A color can be `blue`, `red`, `orange`, `purple`, or `green`, or a hex code like `#2E6BFF`. You can change the hex behind a name, point an app at a different name, change its typeface, or add another app by its `.exe` name. Save the file and the shells update on their own.
