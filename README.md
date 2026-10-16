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

`Ctrl+Alt+Shift+Q` quits.

## Change a shell

Edit `shells.json`. A color can be `blue`, `red`, `orange`, `purple`, or `green`, or a hex code like `#2E6BFF`. You can change the hex behind a name, point an app at a different name, change its typeface, or add another app by its `.exe` name. Save the file and the shells update on their own.
