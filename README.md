# tintja

Light click-through frames so desktop windows are easy to tell apart.

| App | Shell | Name type |
| --- | --- | --- |
| Cursor | Purple | Segoe UI |
| Claude | Blue | Georgia |
| ChatGPT | Green | Cascadia Mono |

Red and orange are in the palette too. The script asks Windows which windows belong to those apps and where they are, then draws a shell on top. Clicks pass through. It does not read the screen, take screenshots, or record anything.

## Run

Windows and Python 3.

```
python tint.py
```

`Ctrl+Alt+Shift+Q` quits. `Ctrl+Alt+Shift+I` toggles the taskbar icon tint.

## Startup

`launch.py` is started when you sign in to Windows. When a Cursor, Claude, or ChatGPT window is open, it starts tintja if the shells are not already up. Minimized windows keep tintja running. Once every one of those windows is closed, tintja quits. The Claude Code helper is ignored.

## Change a shell

Edit `shells.json`. A color can be `blue`, `red`, `orange`, `purple`, or `green`, or a hex code like `#2E6BFF`. You can change the hex behind a name, point an app at a different name, change its typeface, or add another app by its `.exe` name. Save the file and the shells update on their own.
