"""Tuning for tintja's taskbar dots and window shells.

Ctrl+Alt+Shift+D in tintja opens this, or run `python tune.py`. The window
takes the taskbar's own color and shows, magnified, each shelled app's
taskbar button with tintja's real dot on it, and the top-left of each open
window with its name tag. Sliders set the space between icon and dot, how
far each name tag reaches, and how round the shell's corners are. tintja
picks changes up from shells.json while you drag. Save keeps them and
Cancel puts the file back as it was.

tintja measures icons and names by itself, so this is only for nudging.
"""

from __future__ import annotations

import base64
import ctypes
import json
import struct
import subprocess
import sys
import tkinter as tk
import zlib
from pathlib import Path

import tint
import status
from taskbar import TaskbarTints, capture, median_color

HERE = Path(__file__).resolve().parent
ZOOM = 4
REFRESH_MS = 150
GAP_RANGE = (-6.0, 12.0)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def claim_single_instance() -> bool:
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW(None, False, "Local\\tintja-tune")
    return kernel32.GetLastError() != tint.ERROR_ALREADY_EXISTS


def tint_running() -> bool:
    kernel32.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    handle = kernel32.OpenMutexW(0x00100000, False, "Local\\tintja")
    if not handle:
        return False
    kernel32.CloseHandle(ctypes.c_void_p(handle))
    return True


def start_tint() -> None:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    subprocess.Popen([str(exe), str(HERE / "tint.py")], cwd=str(HERE), close_fds=True)


def taskbar_rect() -> tint.RECT | None:
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    tray = user32.FindWindowW("Shell_TrayWnd", None)
    rect = tint.RECT()
    if not tray or not user32.GetWindowRect(ctypes.c_void_p(tray), ctypes.byref(rect)):
        return None
    return rect


def taskbar_color() -> tuple[int, int, int]:
    """The taskbar's color, from a row of its pixels near the top edge."""
    rect = taskbar_rect()
    if rect is not None:
        width = rect.right - rect.left
        row = capture(rect.left, rect.top + 3, width, 1)
        if row:
            pixels = [(row[i + 2], row[i + 1], row[i]) for i in range(0, width * 4, 16)]
            return median_color(pixels)
    return (32, 32, 32)


def png(data: bytes, w: int, h: int) -> bytes:
    """Encode BGRA pixels as a PNG, which Tk can show without extra libraries."""
    rgb = bytearray(w * h * 3)
    rgb[0::3] = data[2::4]
    rgb[1::3] = data[1::4]
    rgb[2::3] = data[0::4]
    raw = b"".join(b"\x00" + bytes(rgb[y * w * 3:(y + 1) * w * 3]) for y in range(h))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def hex_color(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def read_config() -> dict:
    return json.loads(tint.CONFIG_PATH.read_text(encoding="utf-8"))


def write_config(raw: dict) -> None:
    tint.CONFIG_PATH.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8", newline="\n")


class Tuner:
    def __init__(self) -> None:
        tint.SHELLS.ensure()
        # Cancel puts this back exactly.
        self.original_bytes = tint.CONFIG_PATH.read_bytes()
        self.original = read_config()
        self.finder = TaskbarTints()
        self.buttons: dict = {}
        self.windows: dict = {}
        self.images: dict = {}
        self.covers: dict[str, tk.DoubleVar] = {}
        self._pending: str | None = None
        self.changed = False

        bg = taskbar_color()
        light = sum(bg) / 3 > 140
        self.bg = hex_color(bg)
        self.fg = "#1a1a1a" if light else "#f2f2f2"
        self.dim = "#5a5a5a" if light else "#a8a8a8"
        shade = 0.92 if light else 1.35
        self.raised = hex_color(tuple(min(255, int(c * shade + (0 if light else 8))) for c in bg))

        root = self.root = tk.Tk()
        root.title("tintja tuning")
        root.configure(bg=self.bg)
        root.attributes("-topmost", True)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.cancel)

        text = {"bg": self.bg, "fg": self.fg, "font": ("Segoe UI", 10)}
        tk.Label(root, text="Taskbar dots", **{**text, "font": ("Segoe UI Semibold", 13)}).pack(anchor="w", padx=18, pady=(14, 0))
        tk.Label(
            root,
            text="These are your real taskbar buttons, magnified. Slide until each dot sits just under its icon.",
            **{**text, "fg": self.dim},
        ).pack(anchor="w", padx=18, pady=(2, 10))

        self.strip = tk.Frame(root, bg=self.bg)
        self.strip.pack(padx=18, pady=4)
        self.empty = tk.Label(root, text="Open Claude, Cursor, or ChatGPT so its taskbar button shows up.", **text)

        controls = tk.Frame(root, bg=self.bg)
        controls.pack(fill="x", padx=18, pady=(10, 4))
        tk.Label(controls, text="Space under icon", **text).pack(side="left")
        self.gap = tk.DoubleVar(value=tint.SHELLS.dot_gap)
        self.slider(controls, self.gap, GAP_RANGE, 0.5).pack(side="left", padx=10)

        self.working = tk.BooleanVar(value=True)
        for label, value in (("Working", True), ("Done", False)):
            tk.Radiobutton(
                controls, text=label, value=value, variable=self.working, command=self.on_state,
                bg=self.bg, fg=self.fg, selectcolor=self.raised, activebackground=self.bg,
                activeforeground=self.fg, font=("Segoe UI", 10), highlightthickness=0,
            ).pack(side="left", padx=4)

        tk.Label(root, text="Window shells", **{**text, "font": ("Segoe UI Semibold", 13)}).pack(anchor="w", padx=18, pady=(18, 0))
        tk.Label(
            root,
            text="The top-left of each open window, magnified. Widen the name tag until it covers the app's own name or logo.",
            **{**text, "fg": self.dim},
        ).pack(anchor="w", padx=18, pady=(2, 8))
        self.window_rows = tk.Frame(root, bg=self.bg)
        self.window_rows.pack(fill="x", padx=18)

        corners = tk.Frame(root, bg=self.bg)
        corners.pack(fill="x", padx=18, pady=(10, 4))
        tk.Label(corners, text="Corner rounding", **text).pack(side="left")
        radius = tint.SHELLS.corner_radius
        self.auto_corners = tk.BooleanVar(value=radius is None)
        self.radius = tk.DoubleVar(value=8.0 if radius is None else radius)
        self.radius_slider = self.slider(corners, self.radius, (0.0, 16.0), 1.0)
        self.radius_slider.pack(side="left", padx=10)
        tk.Checkbutton(
            corners, text="Match each window", variable=self.auto_corners, command=self.on_auto_corners,
            bg=self.bg, fg=self.fg, selectcolor=self.raised, activebackground=self.bg,
            activeforeground=self.fg, font=("Segoe UI", 10), highlightthickness=0,
        ).pack(side="left", padx=4)
        self.on_auto_corners(write=False)

        actions = tk.Frame(root, bg=self.bg)
        actions.pack(fill="x", padx=18, pady=(8, 14))
        tk.Label(actions, text="Ctrl+Alt+Shift+D measures again and opens this.", **{**text, "fg": self.dim}).pack(side="left")
        for label, command in (("Cancel", self.cancel), ("Reset", self.reset), ("Save", self.save)):
            tk.Button(
                actions, text=label, command=command, width=8, relief="flat",
                bg=self.raised, fg=self.fg, activebackground=self.fg, activeforeground=self.bg,
                font=("Segoe UI", 10),
            ).pack(side="right", padx=(6, 0))

        if not tint_running():
            start_tint()
        status.clear_previews()
        self.on_state()
        self.find_buttons()
        self.find_windows()
        self.refresh()
        root.update_idletasks()
        self.place_window()

    def slider(self, parent, variable: tk.DoubleVar, bounds: tuple[float, float], step: float) -> tk.Scale:
        return tk.Scale(
            parent, from_=bounds[0], to=bounds[1], resolution=step, orient="horizontal",
            length=260, variable=variable, command=self.on_slide, showvalue=True,
            bg=self.bg, fg=self.fg, troughcolor=self.raised, highlightthickness=0, bd=0,
            activebackground=self.fg, font=("Segoe UI", 9),
        )

    def on_auto_corners(self, write: bool = True) -> None:
        self.radius_slider.configure(state="disabled" if self.auto_corners.get() else "normal")
        if write:
            self.on_slide("")

    def find_windows(self) -> None:
        tint.SHELLS.ensure()
        targets, _ = tint.find_targets()
        layout = sorted((style.key, style.label, hwnd) for hwnd, style, _title in targets)
        if layout != self.windows.get("layout"):
            for child in self.window_rows.winfo_children():
                child.destroy()
            self.windows = {"layout": layout, "rows": []}
            covers = {style.key: style.name_cover for style in tint.SHELLS.apps.values()}
            for key, label, hwnd in layout:
                row = tk.Frame(self.window_rows, bg=self.bg)
                row.pack(fill="x", pady=4)
                tk.Label(row, text=label, width=9, anchor="w", bg=self.bg, fg=self.fg, font=("Segoe UI", 10)).pack(side="left")
                picture = tk.Label(row, bg=self.bg, bd=0)
                picture.pack(side="left", padx=(0, 12))
                cover = self.covers.setdefault(key, tk.DoubleVar(value=covers.get(key, 0.0)))
                tk.Label(row, text="Name cover", bg=self.bg, fg=self.dim, font=("Segoe UI", 9)).pack(side="left")
                self.slider(row, cover, (-20.0, 60.0), 1.0).pack(side="left", padx=8)
                self.windows["rows"].append((picture, hwnd))
            if not layout:
                tk.Label(self.window_rows, text="No shelled windows are open.", bg=self.bg, fg=self.dim, font=("Segoe UI", 10)).pack(anchor="w")
        self.root.after(2000, self.find_windows)

    def place_window(self) -> None:
        rect = taskbar_rect()
        root = self.root
        width, height = root.winfo_reqwidth(), root.winfo_reqheight()
        x = (root.winfo_screenwidth() - width) // 2
        y = (rect.top if rect else root.winfo_screenheight()) - height - 60
        root.geometry(f"+{max(0, x)}+{max(0, y)}")

    def find_buttons(self) -> None:
        tint.SHELLS.ensure()
        found = self.finder._buttons(tint.SHELLS.apps)
        labels = {style.key: style.label for style in tint.SHELLS.apps.values()}
        order = sorted(found.values(), key=lambda b: b[0])
        layout = [(b[5], b[:4]) for b in order]
        if layout != self.buttons.get("layout"):
            for child in self.strip.winfo_children():
                child.destroy()
            self.images = {}
            self.buttons = {"layout": layout, "cells": []}
            for app, rect in layout:
                cell = tk.Frame(self.strip, bg=self.bg)
                cell.pack(side="left", padx=14)
                picture = tk.Label(cell, bg=self.bg, bd=0)
                picture.pack()
                tk.Label(cell, text=labels.get(app, app), bg=self.bg, fg=self.dim, font=("Segoe UI", 9)).pack(pady=(4, 0))
                self.buttons["cells"].append((picture, rect))
            if layout:
                self.empty.pack_forget()
            else:
                self.empty.pack(padx=18, pady=10)
        self.root.after(2000, self.find_buttons)

    def refresh(self) -> None:
        for index, (picture, (x, y, w, h)) in enumerate(self.buttons.get("cells", [])):
            data = capture(x, y, w, h)
            if not data:
                continue
            image = tk.PhotoImage(data=base64.b64encode(png(data, w, h)).decode("ascii")).zoom(ZOOM)
            self.images[index] = image
            picture.configure(image=image)
        for index, (picture, hwnd) in enumerate(self.windows.get("rows", [])):
            rect = tint.frame_rect(hwnd)
            if rect is None:
                continue
            dpi = user32.GetDpiForWindow(ctypes.c_void_p(hwnd)) or 96
            w = min(rect.right - rect.left, tint.dip(200, dpi))
            h = min(rect.bottom - rect.top, tint.title_bar_height(hwnd, dpi) + tint.dip(24, dpi))
            data = capture(rect.left, rect.top, w, h)
            if not data:
                continue
            image = tk.PhotoImage(data=base64.b64encode(png(data, w, h)).decode("ascii")).zoom(2)
            self.images[("window", index)] = image
            picture.configure(image=image)
        self.root.after(REFRESH_MS, self.refresh)

    def settings(self) -> dict:
        raw = json.loads(json.dumps(self.original))
        raw["dot_gap"] = round(self.gap.get(), 1)
        if self.auto_corners.get():
            raw.pop("corner_radius", None)
        else:
            raw["corner_radius"] = round(self.radius.get(), 1)
        for entry in raw.get("apps") or []:
            key = str(entry.get("process", "")).strip().lower()
            if key in self.covers:
                value = round(self.covers[key].get(), 1)
                if value:
                    entry["name_cover"] = value
                else:
                    entry.pop("name_cover", None)
        return raw

    def on_slide(self, _value: str) -> None:
        # Write once the slider settles, not on every pixel of a drag.
        if self._pending:
            self.root.after_cancel(self._pending)
        self.changed = True
        self._pending = self.root.after(120, lambda: write_config(self.settings()))

    def on_state(self) -> None:
        for style in tint.SHELLS.apps.values():
            status.write_preview(style.key, self.working.get())

    def reset(self) -> None:
        self.gap.set(1.5)
        self.auto_corners.set(True)
        self.on_auto_corners(write=False)
        for cover in self.covers.values():
            cover.set(0.0)
        self.on_slide("")

    def close(self) -> None:
        if self._pending:
            self.root.after_cancel(self._pending)
        status.clear_previews()
        self.root.destroy()

    def save(self) -> None:
        if self.changed:
            write_config(self.settings())
        self.close()

    def cancel(self) -> None:
        if self.changed:
            tint.CONFIG_PATH.write_bytes(self.original_bytes)
        self.close()


def main() -> None:
    if not claim_single_instance():
        return
    Tuner().root.mainloop()


if __name__ == "__main__":
    main()
