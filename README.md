# tintja

Light click-through frames and taskbar tints so desktop windows are easy to tell apart, plus a taskbar dot that shows when Claude Code, Cursor, or Codex is working, and how full the session is.

| App | Shell | Name type |
| --- | --- | --- |
| Cursor | Purple | Segoe UI |
| Claude | Blue | Georgia |
| ChatGPT | Green | Cascadia Mono |

Red and orange are in the palette too. The script asks Windows which windows belong to those apps and where they are, then draws a shell on top. Each app's taskbar button gets a wash in its color, in the same rounded square Windows lights up when you hover it. Clicks pass through. The only pixels it reads are the shelled apps' own taskbar buttons and the left end of their title bars, briefly, to find where each icon and app name ends. It takes no screenshots and records nothing. The agent status reads only state events and token counts from each session's own log.

## Run

Windows and Python 3.

```
python tint.py
```

| Hotkey | Does |
| --- | --- |
| `Ctrl+Alt+Shift+Q` | Quits |
| `Ctrl+Alt+Shift+I` | Turns the taskbar icon tint on or off |
| `Ctrl+Alt+Shift+D` | Brings each shelled window to the front to measure it, hovers one taskbar button to measure Windows' highlight, puts your front window and mouse back, and opens tuning |

## Fit

tintja fits itself to each PC, so a new install needs no setup.

- **Corners** follow each window's own rounding: 8 pixels at 100% scale on Windows 11, 4 for windows that ask for small corners, and square when maximized or on Windows 10.
- **Title bar and name tag.** Apps that draw their own title bar often make it taller than Windows' standard one, so tintja measures each app's real title bar height and fits the title wash and the name tag to it, with the label centered. The tag covers the app's own logo, makes room for the label, and always ends in a gap, never partway through an icon or a word such as Cursor's File menu. tintja finds these by reading the left end of the title bar, with the shell hidden for a moment. It only does this while that window is in front, so a game or another window can't be mistaken for it. That happens the first time you click into each app, or right away with `Ctrl+Alt+Shift+D`.
- **Taskbar wash.** The wash covers just the rounded square Windows highlights when you hover a taskbar button. `Ctrl+Alt+Shift+D` measures that square by hovering one button for a moment, and saves it in `fit.json`. Until then, tintja uses Windows 11's standard 40 by 40 square with 4-pixel corners.
- **Working dot.** See [Dot size](#dot-size) below.

`Ctrl+Alt+Shift+D` also opens the tuning window, or run `python tune.py`. It takes your taskbar's color and shows magnified, live views of each taskbar button and each window's top-left corner. Its sliders set the space under the taskbar icons, how far each app's name tag reaches, and the corner rounding, where **Match each window** follows Windows. tintja updates while you drag. **Save** keeps the changes and **Cancel** puts `shells.json` back exactly as it was. The settings are `"dot_gap"` and `"corner_radius"` at the top of `shells.json` and `"name_cover"` on each app, all in pixels at 100% scale.

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
  "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "C:/Python314/python.exe D:/DEV/app-tint/status.py", "async": true, "timeout": 10 }] }],
  "PostToolUse":      [{ "hooks": [{ "type": "command", "command": "C:/Python314/python.exe D:/DEV/app-tint/status.py", "async": true, "timeout": 10 }] }],
  "Notification":     [{ "hooks": [{ "type": "command", "command": "C:/Python314/python.exe D:/DEV/app-tint/status.py", "async": true, "timeout": 10 }] }],
  "Stop":             [{ "hooks": [{ "type": "command", "command": "C:/Python314/python.exe D:/DEV/app-tint/status.py", "async": true, "timeout": 10 }] }],
  "StopFailure":      [{ "hooks": [{ "type": "command", "command": "C:/Python314/python.exe D:/DEV/app-tint/status.py", "async": true, "timeout": 10 }] }],
  "SessionEnd":       [{ "hooks": [{ "type": "command", "command": "C:/Python314/python.exe D:/DEV/app-tint/status.py", "timeout": 5 }] }]
}
```

Keep the script path inside `command`, with forward slashes. Cursor also runs the hooks in `~/.claude/settings.json`, and it ignores an `args` list.

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

### Dot size

The half circle sits on the bottom edge of the highlight square and reaches up to just under the app icon, which also hides Windows' open-window pill. When a taskbar button first appears or changes size, tintja hides its own wash for a moment, reads that button's pixels, and finds the icon's lower edge by comparing against the taskbar's color. If a full-screen game or another window covers the taskbar, it uses Windows' standard 24-pixel icon size and tries again 30 seconds later.

In the tuning window, drag **Space under icon** until the dot sits where you want, and switch between **Working** and **Done** to see both states. The default is 1.5, and a negative number lets the dot overlap the icon.

### Notes

Claude Code's fill assumes a 1,000,000-token context window. Set `"context_window": 200000` (or another number) at the top level of `shells.json` to change it. If you press Esc in the middle of a Claude Code turn, no stop event fires, so the dot keeps glowing for up to 20 minutes.

## Change a shell

Edit `shells.json`. A color can be `blue`, `red`, `orange`, `purple`, or `green`, or a hex code like `#2E6BFF`. You can change the hex behind a name, point an app at a different name, change its typeface, or add another app by its `.exe` name. Save the file and the shells update on their own.
