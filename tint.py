"""tintja.

Light click-through frames for desktop windows. The default shells are the
four mask colors: blue, red, orange, and purple. Edit shells.json to change
a color, a typeface, or which app wears which shell. Ctrl+Alt+Shift+Q quits.
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path
from ctypes import (
    POINTER,
    WINFUNCTYPE,
    byref,
    c_byte,
    c_float,
    c_int,
    c_long,
    c_uint,
    c_uint32,
    c_ushort,
    c_void_p,
    c_wchar_p,
    sizeof,
)
from dataclasses import dataclass

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi
gdiplus = ctypes.windll.gdiplus

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = c_void_p(-4)
user32.SetProcessDpiAwarenessContext.argtypes = [c_void_p]
user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)

WM_HOTKEY = 0x0312
WM_DESTROY = 0x0002
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_Q = 0x51
VK_I = 0x49
HOTKEY_QUIT = 1
HOTKEY_ICONS = 2

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
HWND_TOP = c_void_p(0)

GW_HWNDPREV = 3
GW_OWNER = 4
GWL_EXSTYLE = -20

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

BI_RGB = 0
DIB_RGB_COLORS = 0
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1
ULW_ALPHA = 2
PIXEL_FORMAT_32BPP_PARGB = 0x000E200B

PM_REMOVE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ALREADY_EXISTS = 183

BAR_DIP = 30
RAIL_DIP = 8
EDGE_DIP = 5
DWMWA_CAPTION_BUTTON_BOUNDS = 5


class RECT(ctypes.Structure):
    _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", c_long), ("y", c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", c_long), ("cy", c_long)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", c_byte),
        ("BlendFlags", c_byte),
        ("SourceConstantAlpha", c_byte),
        ("AlphaFormat", c_byte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", c_uint32),
        ("biWidth", c_long),
        ("biHeight", c_long),
        ("biPlanes", c_ushort),
        ("biBitCount", c_ushort),
        ("biCompression", c_uint32),
        ("biSizeImage", c_uint32),
        ("biXPelsPerMeter", c_long),
        ("biYPelsPerMeter", c_long),
        ("biClrUsed", c_uint32),
        ("biClrImportant", c_uint32),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", c_uint),
        ("lpfnWndProc", c_void_p),
        ("cbClsExtra", c_int),
        ("cbWndExtra", c_int),
        ("hInstance", c_void_p),
        ("hIcon", c_void_p),
        ("hCursor", c_void_p),
        ("hbrBackground", c_void_p),
        ("lpszMenuName", c_wchar_p),
        ("lpszClassName", c_wchar_p),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", c_void_p),
        ("message", c_uint),
        ("wParam", c_void_p),
        ("lParam", c_void_p),
        ("time", c_uint32),
        ("pt", POINT),
    ]


class RectF(ctypes.Structure):
    _fields_ = [("x", c_float), ("y", c_float), ("w", c_float), ("h", c_float)]


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", c_uint32),
        ("DebugEventCallback", c_void_p),
        ("SuppressBackgroundThread", c_int),
        ("SuppressExternalCodecs", c_int),
    ]


LRESULT = ctypes.c_ssize_t
WNDPROC = WINFUNCTYPE(LRESULT, c_void_p, c_uint, c_void_p, c_void_p)
WNDENUMPROC = WINFUNCTYPE(ctypes.c_bool, c_void_p, ctypes.c_ssize_t)

user32.DefWindowProcW.argtypes = [c_void_p, c_uint, c_void_p, c_void_p]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [
    c_uint, c_wchar_p, c_wchar_p, c_uint,
    c_int, c_int, c_int, c_int,
    c_void_p, c_void_p, c_void_p, c_void_p,
]
user32.CreateWindowExW.restype = c_void_p
user32.SetWindowPos.argtypes = [c_void_p, c_void_p, c_int, c_int, c_int, c_int, c_uint]
user32.SetWindowPos.restype = ctypes.c_bool
user32.GetWindowRect.argtypes = [c_void_p, POINTER(RECT)]
user32.GetWindowRect.restype = ctypes.c_bool
user32.GetWindowTextLengthW.argtypes = [c_void_p]
user32.GetWindowTextLengthW.restype = c_int
user32.GetWindowTextW.argtypes = [c_void_p, c_wchar_p, c_int]
user32.GetWindowTextW.restype = c_int
user32.IsWindowVisible.argtypes = [c_void_p]
user32.IsWindowVisible.restype = ctypes.c_bool
user32.IsWindow.argtypes = [c_void_p]
user32.IsWindow.restype = ctypes.c_bool
user32.IsIconic.argtypes = [c_void_p]
user32.IsIconic.restype = ctypes.c_bool
user32.GetWindow.argtypes = [c_void_p, c_uint]
user32.GetWindow.restype = c_void_p
user32.GetWindowThreadProcessId.argtypes = [c_void_p, POINTER(c_uint32)]
user32.GetWindowThreadProcessId.restype = c_uint32
user32.GetDpiForWindow.argtypes = [c_void_p]
user32.GetDpiForWindow.restype = c_uint
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_ssize_t]
user32.EnumWindows.restype = ctypes.c_bool
user32.RegisterClassW.argtypes = [POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = c_ushort
user32.DestroyWindow.argtypes = [c_void_p]
user32.DestroyWindow.restype = ctypes.c_bool
user32.ShowWindow.argtypes = [c_void_p, c_int]
user32.ShowWindow.restype = ctypes.c_bool
user32.UpdateLayeredWindow.argtypes = [
    c_void_p, c_void_p, c_void_p, c_void_p,
    c_void_p, c_void_p, c_uint32, c_void_p, c_uint32,
]
user32.UpdateLayeredWindow.restype = ctypes.c_bool
user32.GetDC.argtypes = [c_void_p]
user32.GetDC.restype = c_void_p
user32.ReleaseDC.argtypes = [c_void_p, c_void_p]
user32.ReleaseDC.restype = c_int
user32.PeekMessageW.argtypes = [POINTER(MSG), c_void_p, c_uint, c_uint, c_uint]
user32.PeekMessageW.restype = ctypes.c_bool
user32.TranslateMessage.argtypes = [POINTER(MSG)]
user32.DispatchMessageW.argtypes = [POINTER(MSG)]
user32.RegisterHotKey.argtypes = [c_void_p, c_int, c_uint, c_uint]
user32.RegisterHotKey.restype = ctypes.c_bool
user32.UnregisterHotKey.argtypes = [c_void_p, c_int]
user32.UnregisterHotKey.restype = ctypes.c_bool

gdi32.CreateCompatibleDC.argtypes = [c_void_p]
gdi32.CreateCompatibleDC.restype = c_void_p
gdi32.CreateDIBSection.argtypes = [c_void_p, c_void_p, c_uint, POINTER(c_void_p), c_void_p, c_uint32]
gdi32.CreateDIBSection.restype = c_void_p
gdi32.SelectObject.argtypes = [c_void_p, c_void_p]
gdi32.SelectObject.restype = c_void_p
gdi32.DeleteObject.argtypes = [c_void_p]
gdi32.DeleteObject.restype = ctypes.c_bool
gdi32.DeleteDC.argtypes = [c_void_p]
gdi32.DeleteDC.restype = ctypes.c_bool

kernel32.OpenProcess.argtypes = [c_uint32, ctypes.c_bool, c_uint32]
kernel32.OpenProcess.restype = c_void_p
kernel32.CloseHandle.argtypes = [c_void_p]
kernel32.CloseHandle.restype = ctypes.c_bool
kernel32.QueryFullProcessImageNameW.argtypes = [c_void_p, c_uint32, c_wchar_p, POINTER(c_uint32)]
kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool
kernel32.GetModuleHandleW.argtypes = [c_wchar_p]
kernel32.GetModuleHandleW.restype = c_void_p

dwmapi.DwmGetWindowAttribute.argtypes = [c_void_p, c_uint32, c_void_p, c_uint32]
dwmapi.DwmGetWindowAttribute.restype = c_int

gdiplus.GdiplusStartup.argtypes = [POINTER(c_void_p), POINTER(GdiplusStartupInput), c_void_p]
gdiplus.GdiplusStartup.restype = c_int
gdiplus.GdipCreateBitmapFromScan0.argtypes = [c_int, c_int, c_int, c_int, c_void_p, POINTER(c_void_p)]
gdiplus.GdipCreateBitmapFromScan0.restype = c_int
gdiplus.GdipGetImageGraphicsContext.argtypes = [c_void_p, POINTER(c_void_p)]
gdiplus.GdipGetImageGraphicsContext.restype = c_int
gdiplus.GdipDeleteGraphics.argtypes = [c_void_p]
gdiplus.GdipDeleteGraphics.restype = c_int
gdiplus.GdipDisposeImage.argtypes = [c_void_p]
gdiplus.GdipDisposeImage.restype = c_int
gdiplus.GdipGraphicsClear.argtypes = [c_void_p, c_uint32]
gdiplus.GdipGraphicsClear.restype = c_int
gdiplus.GdipSetSmoothingMode.argtypes = [c_void_p, c_int]
gdiplus.GdipSetSmoothingMode.restype = c_int
gdiplus.GdipSetTextRenderingHint.argtypes = [c_void_p, c_int]
gdiplus.GdipSetTextRenderingHint.restype = c_int
gdiplus.GdipCreateSolidFill.argtypes = [c_uint32, POINTER(c_void_p)]
gdiplus.GdipCreateSolidFill.restype = c_int
gdiplus.GdipDeleteBrush.argtypes = [c_void_p]
gdiplus.GdipDeleteBrush.restype = c_int
gdiplus.GdipFillRectangle.argtypes = [c_void_p, c_void_p, c_float, c_float, c_float, c_float]
gdiplus.GdipFillRectangle.restype = c_int
gdiplus.GdipCreateFontFamilyFromName.argtypes = [c_wchar_p, c_void_p, POINTER(c_void_p)]
gdiplus.GdipCreateFontFamilyFromName.restype = c_int
gdiplus.GdipDeleteFontFamily.argtypes = [c_void_p]
gdiplus.GdipDeleteFontFamily.restype = c_int
gdiplus.GdipCreateFont.argtypes = [c_void_p, c_float, c_int, c_int, POINTER(c_void_p)]
gdiplus.GdipCreateFont.restype = c_int
gdiplus.GdipDeleteFont.argtypes = [c_void_p]
gdiplus.GdipDeleteFont.restype = c_int
gdiplus.GdipCreateStringFormat.argtypes = [c_int, c_int, POINTER(c_void_p)]
gdiplus.GdipCreateStringFormat.restype = c_int
gdiplus.GdipDeleteStringFormat.argtypes = [c_void_p]
gdiplus.GdipDeleteStringFormat.restype = c_int
gdiplus.GdipSetStringFormatAlign.argtypes = [c_void_p, c_int]
gdiplus.GdipSetStringFormatAlign.restype = c_int
gdiplus.GdipSetStringFormatLineAlign.argtypes = [c_void_p, c_int]
gdiplus.GdipSetStringFormatLineAlign.restype = c_int
gdiplus.GdipMeasureString.argtypes = [
    c_void_p, c_wchar_p, c_int, c_void_p, POINTER(RectF), c_void_p,
    POINTER(RectF), POINTER(c_int), POINTER(c_int),
]
gdiplus.GdipMeasureString.restype = c_int
gdiplus.GdipDrawString.argtypes = [
    c_void_p, c_wchar_p, c_int, c_void_p, POINTER(RectF), c_void_p, c_void_p,
]
gdiplus.GdipDrawString.restype = c_int


@dataclass(frozen=True)
class AppStyle:
    key: str
    label: str
    color: int  # 0xRRGGBB
    fonts: tuple[str, ...]
    skip_path_contains: tuple[str, ...] = ()


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "shells.json"

# Blue, red, orange, and purple are the built-in shells. Green is included
# because ChatGPT wears it by default.
DEFAULT_CONFIG = {
    "colors": {
        "blue": "#2E6BFF",
        "red": "#E23B3B",
        "orange": "#F47B20",
        "purple": "#7B3FF2",
        "green": "#10A37F",
    },
    "apps": [
        {
            "process": "cursor.exe",
            "label": "Cursor",
            "color": "purple",
            "fonts": ["Segoe UI", "Arial"],
        },
        {
            "process": "claude.exe",
            "label": "Claude",
            "color": "blue",
            "fonts": ["Georgia", "Palatino Linotype", "Times New Roman"],
            "skip_if_path_contains": ["claude-code"],
        },
        {
            "process": "chatgpt.exe",
            "label": "ChatGPT",
            "color": "green",
            "fonts": ["Cascadia Mono", "Consolas", "Courier New"],
        },
    ],
}


def argb(alpha: int, rgb: int) -> int:
    return ((alpha & 0xFF) << 24) | (rgb & 0xFFFFFF)


def dip(px: int, dpi: int) -> int:
    return max(1, round(px * dpi / 96))


def start_gdiplus() -> None:
    token = c_void_p()
    startup = GdiplusStartupInput(1, None, 0, 0)
    status = gdiplus.GdiplusStartup(byref(token), byref(startup), None)
    if status != 0:
        raise RuntimeError(f"GdiplusStartup failed ({status})")


def font_family(names: tuple[str, ...]) -> c_void_p:
    for name in names:
        family = c_void_p()
        if gdiplus.GdipCreateFontFamilyFromName(name, None, byref(family)) == 0:
            return family
    family = c_void_p()
    if gdiplus.GdipCreateFontFamilyFromName("Segoe UI", None, byref(family)) == 0:
        return family
    raise RuntimeError("no usable font")


def process_path(hwnd: int) -> str:
    pid = c_uint32()
    user32.GetWindowThreadProcessId(hwnd, byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = c_uint32(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, byref(size)):
            return ""
        return buf.value
    finally:
        kernel32.CloseHandle(handle)


def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def frame_rect(hwnd: int) -> RECT | None:
    rect = RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, byref(rect), sizeof(rect)) == 0:
        if rect.right > rect.left and rect.bottom > rect.top:
            return rect
    if not user32.GetWindowRect(hwnd, byref(rect)):
        return None
    return rect


def title_bar_height(hwnd: int, dpi: int) -> int:
    rect = RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CAPTION_BUTTON_BOUNDS, byref(rect), sizeof(rect)) == 0:
        height = rect.bottom - rect.top
        if 20 <= height <= 80:
            return height
    return dip(BAR_DIP, dpi)


def is_cloaked(hwnd: int) -> bool:
    cloaked = c_int()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, byref(cloaked), sizeof(cloaked)) != 0:
        return False
    return cloaked.value != 0


def parse_rgb(value: object, palette: dict[str, int]) -> int:
    text = str(value).strip().lower()
    if text in palette:
        return palette[text]
    hex_part = text[1:] if text.startswith("#") else text
    if len(hex_part) == 6 and all(c in "0123456789abcdef" for c in hex_part):
        return int(hex_part, 16)
    raise ValueError(f"unknown color {value!r}")


def load_shells(raw: dict) -> dict[str, AppStyle]:
    palette_raw = raw.get("colors") or DEFAULT_CONFIG["colors"]
    palette = {str(name).strip().lower(): parse_rgb(hex_color, {}) for name, hex_color in palette_raw.items()}
    apps: dict[str, AppStyle] = {}
    for entry in raw.get("apps") or []:
        process = str(entry.get("process", "")).strip().lower()
        if not process:
            continue
        fonts = entry.get("fonts") or ["Segoe UI"]
        skips = entry.get("skip_if_path_contains") or []
        label = str(entry.get("label") or process)[:40]
        apps[process] = AppStyle(
            process,
            label,
            parse_rgb(entry.get("color", "blue"), palette),
            tuple(str(font)[:80] for font in list(fonts)[:4]),
            tuple(str(skip).lower()[:80] for skip in list(skips)[:8]),
        )
    return apps


class ShellBook:
    def __init__(self) -> None:
        self.apps: dict[str, AppStyle] = {}
        self._mtime: float | None = None

    def ensure(self) -> bool:
        if not CONFIG_PATH.exists():
            CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
        mtime = CONFIG_PATH.stat().st_mtime
        if mtime == self._mtime:
            return False
        if CONFIG_PATH.stat().st_size > 65_536:
            raise ValueError("shells.json is too large")
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.apps = load_shells(raw)
        self._mtime = mtime
        return True


SHELLS = ShellBook()


def style_for_path(path: str) -> AppStyle | None:
    lowered = path.lower().replace("/", "\\")
    name = lowered.rsplit("\\", 1)[-1]
    style = SHELLS.apps.get(name)
    if style is None:
        return None
    if any(skip in lowered for skip in style.skip_path_contains):
        return None
    return style


MAX_BITMAP_EDGE = 8192


def find_targets() -> tuple[list[tuple[int, AppStyle, str]], bool]:
    """Return windows to paint, and whether any shell window still exists.

    A minimized window still counts as open. A closed one does not.
    """
    found: list[tuple[int, AppStyle, str]] = []
    any_open = False

    def visit(hwnd, _lparam):
        nonlocal any_open
        if user32.GetWindow(hwnd, GW_OWNER) or is_cloaked(hwnd):
            return True
        iconic = bool(user32.IsIconic(hwnd))
        if not iconic and not user32.IsWindowVisible(hwnd):
            return True
        title = window_title(hwnd)
        if not title:
            return True
        style = style_for_path(process_path(hwnd))
        if style is None:
            return True
        if iconic:
            any_open = True
            return True
        rect = frame_rect(hwnd)
        if rect is None:
            return True
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width < 480 or height < 320:
            return True
        if width > MAX_BITMAP_EDGE or height > MAX_BITMAP_EDGE:
            return True
        any_open = True
        found.append((hwnd, style, title))
        return True

    user32.EnumWindows(WNDENUMPROC(visit), 0)
    return found, any_open


class Overlay:
    def __init__(self, hwnd_target: int, style: AppStyle):
        self.target = hwnd_target
        self.style = style
        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            "tintja",
            "",
            WS_POPUP,
            0, 0, 10, 10,
            None, None, kernel32.GetModuleHandleW(None), None,
        )
        if not self.hwnd:
            raise RuntimeError(f"CreateWindowEx failed ({ctypes.get_last_error()})")
        self.screen_dc = user32.GetDC(None)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)
        self.bitmap = None
        self.old_bitmap = None
        self.size = (0, 0)
        self.origin = (0, 0)

    def close(self) -> None:
        self._free_bitmap()
        if self.mem_dc:
            gdi32.DeleteDC(self.mem_dc)
            self.mem_dc = None
        if self.screen_dc:
            user32.ReleaseDC(None, self.screen_dc)
            self.screen_dc = None
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None

    def _free_bitmap(self) -> None:
        if self.mem_dc and self.old_bitmap:
            gdi32.SelectObject(self.mem_dc, self.old_bitmap)
            self.old_bitmap = None
        if self.bitmap:
            gdi32.DeleteObject(self.bitmap)
            self.bitmap = None

    def _ensure_bitmap(self, width: int, height: int) -> c_void_p:
        if self.size == (width, height) and self.bitmap:
            return self.bitmap
        self._free_bitmap()
        info = BITMAPINFOHEADER()
        info.biSize = sizeof(BITMAPINFOHEADER)
        info.biWidth = width
        info.biHeight = -height
        info.biPlanes = 1
        info.biBitCount = 32
        info.biCompression = BI_RGB
        bits = c_void_p()
        self.bitmap = gdi32.CreateDIBSection(self.screen_dc, byref(info), DIB_RGB_COLORS, byref(bits), None, 0)
        if not self.bitmap or not bits:
            raise RuntimeError("CreateDIBSection failed")
        self.old_bitmap = gdi32.SelectObject(self.mem_dc, self.bitmap)
        self._paint(bits, width, height)
        self.size = (width, height)
        return bits

    def _paint(self, bits: c_void_p, width: int, height: int) -> None:
        image = c_void_p()
        graphics = c_void_p()
        text_brush = c_void_p()
        family = None
        font = c_void_p()
        fmt = c_void_p()
        dpi = user32.GetDpiForWindow(self.target) or 96
        bar = min(title_bar_height(self.target, dpi), max(1, height // 5))
        rail_w = min(dip(RAIL_DIP, dpi), max(1, width // 8))
        edge = dip(EDGE_DIP, dpi)
        status = gdiplus.GdipCreateBitmapFromScan0(
            width, height, width * 4, PIXEL_FORMAT_32BPP_PARGB, bits, byref(image)
        )
        if status != 0:
            raise RuntimeError(f"bitmap failed ({status})")
        try:
            if gdiplus.GdipGetImageGraphicsContext(image, byref(graphics)) != 0:
                raise RuntimeError("graphics failed")
            gdiplus.GdipGraphicsClear(graphics, 0)
            gdiplus.GdipSetSmoothingMode(graphics, 4)
            gdiplus.GdipSetTextRenderingHint(graphics, 4)
            rgb = self.style.color
            # 10% wash across the real title bar. File, Edit, and the rest stay readable.
            fill(graphics, argb(0x1A, rgb), 0, 0, width, bar)
            fill(graphics, argb(0xE6, rgb), 0, bar, rail_w, height - bar)
            fill(graphics, argb(0xB0, rgb), 0, height - edge, width, edge)
            fill(graphics, argb(0xB0, rgb), width - edge, bar, edge, height - bar)
            family = font_family(self.style.fonts)
            if gdiplus.GdipCreateFont(family, float(dip(13, dpi)), 1, 2, byref(font)) != 0:
                return
            if gdiplus.GdipCreateStringFormat(0, 0, byref(fmt)) != 0:
                return
            gdiplus.GdipSetStringFormatAlign(fmt, 0)
            gdiplus.GdipSetStringFormatLineAlign(fmt, 1)
            layout = RectF(0, 0, 800, float(bar))
            measured = RectF()
            chars = c_int()
            lines = c_int()
            gdiplus.GdipMeasureString(
                graphics, self.style.label, -1, font, byref(layout), fmt,
                byref(measured), byref(chars), byref(lines),
            )
            pad_x = dip(6, dpi)
            overrun = dip(8, dpi)
            if self.style.key == "cursor.exe":
                overrun += dip(5, dpi)
            pill_w = min(float(width), measured.w + pad_x + overrun)
            fill(graphics, argb(0xFF, rgb), 0, 0, pill_w, bar)
            if gdiplus.GdipCreateSolidFill(argb(0xFF, 0xFFFFFF), byref(text_brush)) == 0:
                text_rect = RectF(float(pad_x), 0, measured.w + 2, float(bar))
                gdiplus.GdipDrawString(graphics, self.style.label, -1, font, byref(text_rect), fmt, text_brush)
        finally:
            if text_brush:
                gdiplus.GdipDeleteBrush(text_brush)
            if fmt:
                gdiplus.GdipDeleteStringFormat(fmt)
            if font:
                gdiplus.GdipDeleteFont(font)
            if family:
                gdiplus.GdipDeleteFontFamily(family)
            if graphics:
                gdiplus.GdipDeleteGraphics(graphics)
            if image:
                gdiplus.GdipDisposeImage(image)

    def sync(self, rect: RECT, style: AppStyle) -> None:
        if style != self.style:
            self.style = style
            self.size = (0, 0)
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        moved = self.origin != (rect.left, rect.top) or self.size != (width, height)
        if self.size != (width, height):
            self._ensure_bitmap(width, height)
            origin = POINT(0, 0)
            size = SIZE(width, height)
            dest = POINT(rect.left, rect.top)
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
            ok = user32.UpdateLayeredWindow(
                self.hwnd, self.screen_dc, byref(dest), byref(size),
                self.mem_dc, byref(origin), 0, byref(blend), ULW_ALPHA,
            )
            if not ok:
                raise RuntimeError(f"UpdateLayeredWindow failed ({ctypes.get_last_error()})")
            self.origin = (rect.left, rect.top)
        elif moved:
            user32.SetWindowPos(
                self.hwnd, HWND_TOP, rect.left, rect.top, width, height,
                SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
            self.origin = (rect.left, rect.top)
        self._raise_above_target()

    def _raise_above_target(self) -> None:
        prev = user32.GetWindow(self.target, GW_HWNDPREV)
        if prev == self.hwnd:
            return
        insert_after = prev if prev else HWND_TOP
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
        user32.SetWindowPos(self.hwnd, insert_after, 0, 0, 0, 0, flags)


def fill(graphics, color, x, y, w, h) -> None:
    if w <= 0 or h <= 0:
        return
    brush = c_void_p()
    if gdiplus.GdipCreateSolidFill(color, byref(brush)) != 0:
        return
    gdiplus.GdipFillRectangle(graphics, brush, float(x), float(y), float(w), float(h))
    gdiplus.GdipDeleteBrush(brush)


def claim_single_instance() -> bool:
    kernel32.CreateMutexW.argtypes = [c_void_p, ctypes.c_bool, c_wchar_p]
    kernel32.CreateMutexW.restype = c_void_p
    kernel32.GetLastError.restype = c_uint32
    kernel32.CreateMutexW(None, False, "Local\\tintja")
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def main() -> None:
    if not claim_single_instance():
        print("tintja is already running.", flush=True)
        return
    start_gdiplus()

    def wndproc(hwnd, msg, wparam, lparam):
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    proc = WNDPROC(wndproc)
    klass = WNDCLASSW()
    klass.lpfnWndProc = ctypes.cast(proc, c_void_p)
    klass.hInstance = kernel32.GetModuleHandleW(None)
    klass.lpszClassName = "tintja"
    atom = user32.RegisterClassW(byref(klass))
    if not atom:
        raise RuntimeError(f"RegisterClass failed ({ctypes.get_last_error()})")

    if not user32.RegisterHotKey(None, HOTKEY_QUIT, MOD_CONTROL | MOD_ALT | MOD_SHIFT, VK_Q):
        print("Quit hotkey is already taken. Close this window to stop.", flush=True)
    else:
        print("tintja. Ctrl+Alt+Shift+Q quits.", flush=True)
    icons_toggle = user32.RegisterHotKey(None, HOTKEY_ICONS, MOD_CONTROL | MOD_ALT | MOD_SHIFT, VK_I)
    if icons_toggle:
        print("Taskbar icons on. Ctrl+Alt+Shift+I toggles them.", flush=True)

    from taskbar import TaskbarTints
    taskbar = TaskbarTints()

    overlays: dict[int, Overlay] = {}
    # A short beat so a window that is still opening is not treated as closed.
    closed_since: float | None = None
    try:
        while True:
            msg = MSG()
            while user32.PeekMessageW(byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_QUIT:
                    return
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ICONS:
                    state = "on" if taskbar.toggle() else "off"
                    print(f"Taskbar icons {state}.", flush=True)
                    continue
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))

            try:
                if SHELLS.ensure():
                    print(f"Shells loaded from {CONFIG_PATH.name}.", flush=True)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                print(f"Could not read {CONFIG_PATH.name}: {exc}", flush=True)

            targets, any_open = find_targets()
            if any_open:
                closed_since = None
            else:
                closed_since = time.monotonic() if closed_since is None else closed_since
                if time.monotonic() - closed_since >= 2:
                    print("Shell windows are closed. tintja is stopping.", flush=True)
                    return

            live: set[int] = set()
            for hwnd, style, _title in targets:
                live.add(hwnd)
                overlay = overlays.get(hwnd)
                if overlay is None:
                    overlay = Overlay(hwnd, style)
                    overlays[hwnd] = overlay
                    print(f"  {style.label}: {_title}", flush=True)
                rect = frame_rect(hwnd)
                if rect is not None:
                    overlay.sync(rect, style)

            taskbar.update(SHELLS.apps)

            for hwnd in list(overlays):
                if hwnd not in live or not user32.IsWindow(hwnd):
                    overlays.pop(hwnd).close()
            time.sleep(0.03)
    finally:
        user32.UnregisterHotKey(None, HOTKEY_QUIT)
        user32.UnregisterHotKey(None, HOTKEY_ICONS)
        taskbar.close()
        for overlay in overlays.values():
            overlay.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
