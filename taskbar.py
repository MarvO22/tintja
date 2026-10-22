"""50% color washes on the taskbar icons for the shelled apps.

An agent session (Claude Code, Cursor, or Codex) adds two marks to its app's
wash: a lighter fill from the left that grows with the session's context use,
and a half circle on the bottom edge that glows white while the agent works
and cools to a darker shade of the wash when it is done. status.py supplies
both.

The half circle reaches up to just under the app icon. To find where the
icon ends, each button's pixels are read once with the wash hidden and
compared against the taskbar's own color. That runs when a button first
appears, when its size changes, and when Ctrl+Alt+Shift+D asks for it.
"dot_gap" in shells.json sets the space left under the icon.
"""

from __future__ import annotations

import ctypes
import json
import math
import time
import uuid
from pathlib import Path
from ctypes import POINTER, byref, c_byte, c_float, c_int, c_long, c_uint, c_uint32, c_ushort, c_void_p, sizeof

import status

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
gdiplus = ctypes.windll.gdiplus
ole32 = ctypes.windll.ole32
oleaut = ctypes.windll.oleaut32

CLSCTX_INPROC_SERVER = 1
TREE_DESCENDANTS = 4
VT_BSTR = 8

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
HWND_TOPMOST = c_void_p(-1)
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1
ULW_ALPHA = 2
BI_RGB = 0
DIB_RGB_COLORS = 0
PIXEL_FORMAT_32BPP_PARGB = 0x000E200B

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
SW_HIDE = 0

gdiplus.GdipFillEllipse.argtypes = [c_void_p, c_void_p, c_float, c_float, c_float, c_float]
gdiplus.GdipFillEllipse.restype = c_int
gdi32.BitBlt.argtypes = [c_void_p, c_int, c_int, c_int, c_int, c_void_p, c_int, c_int, c_uint32]
gdi32.BitBlt.restype = ctypes.c_bool

PULSE_SECONDS = 1.6
COOL_SECONDS = 1.4
DOT_GAP = 1.5
# Windows 11's taskbar hover highlight, in DIPs, until one is measured.
DEFAULT_HIGHLIGHT = 40
DEFAULT_RADIUS = 4
MOUSEEVENTF_MOVE = 0x0001
# Measurements of this PC's taskbar. Not settings, so kept out of shells.json.
FIT_PATH = Path(__file__).resolve().parent / "fit.json"
# A pixel differs from the taskbar when a channel is this far off.
ICON_CONTRAST = 48


class GUID(ctypes.Structure):
    _fields_ = [
        ("d1", c_uint32),
        ("d2", c_ushort),
        ("d3", c_ushort),
        ("d4", ctypes.c_ubyte * 8),
    ]


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


def _guid(text: str) -> GUID:
    return GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


CLSID = _guid("{ff48dba4-60ef-4201-aa87-54103eef594e}")
IID = _guid("{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}")

Release = ctypes.WINFUNCTYPE(c_uint32, c_void_p)
ElementFromHandle = ctypes.WINFUNCTYPE(c_long, c_void_p, c_void_p, POINTER(c_void_p))
CreateTrueCondition = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(c_void_p))
FindAll = ctypes.WINFUNCTYPE(c_long, c_void_p, c_int, c_void_p, POINTER(c_void_p))
GetLength = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(c_int))
GetElement = ctypes.WINFUNCTYPE(c_long, c_void_p, c_int, POINTER(c_void_p))
GetName = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(c_void_p))
class RECT(ctypes.Structure):
    _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]


GetRect = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(RECT))


def _vt(ptr):
    return ctypes.cast(ctypes.cast(ptr, POINTER(c_void_p))[0], POINTER(c_void_p))


def _release(ptr) -> None:
    if ptr:
        Release(_vt(ptr)[2])(ptr)


def capture(x: int, y: int, w: int, h: int) -> bytes | None:
    """BGRA pixels of a screen rectangle, top row first."""
    if w <= 0 or h <= 0:
        return None
    screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(screen)
    info = BITMAPINFOHEADER()
    info.biSize = sizeof(BITMAPINFOHEADER)
    info.biWidth = w
    info.biHeight = -h
    info.biPlanes = 1
    info.biBitCount = 32
    info.biCompression = BI_RGB
    bits = c_void_p()
    bitmap = gdi32.CreateDIBSection(screen, byref(info), DIB_RGB_COLORS, byref(bits), None, 0)
    try:
        if not bitmap or not bits:
            return None
        old = gdi32.SelectObject(mem, bitmap)
        ok = gdi32.BitBlt(mem, 0, 0, w, h, screen, x, y, SRCCOPY | CAPTUREBLT)
        data = ctypes.string_at(bits, w * h * 4) if ok else None
        gdi32.SelectObject(mem, old)
        return data
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)


# Own handle to user32 so these calls do not clash with argtypes tint.py sets.
_user32 = ctypes.WinDLL("user32")
_user32.WindowFromPoint.argtypes = [POINT]
_user32.WindowFromPoint.restype = c_void_p
_user32.GetAncestor.argtypes = [c_void_p, c_uint]
_user32.GetAncestor.restype = c_void_p
_user32.GetForegroundWindow.restype = c_void_p
_user32.GetWindowRect.argtypes = [c_void_p, POINTER(RECT)]
_user32.GetClassNameW.argtypes = [c_void_p, ctypes.c_wchar_p, c_int]
TRAY_CLASSES = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd")
GA_ROOT = 2


def _class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(64)
    _user32.GetClassNameW(hwnd, buf, 64)
    return buf.value


def taskbar_uncovered(x: int, y: int) -> bool:
    """Whether the taskbar at this point is really on screen.

    A full-screen game or video in front covers it even when Windows still
    reports the taskbar under the point.
    """
    front = _user32.GetForegroundWindow()
    if front and _class_name(front) not in TRAY_CLASSES:
        rect = RECT()
        if _user32.GetWindowRect(front, byref(rect)) and rect.left <= x < rect.right and rect.top <= y < rect.bottom:
            return False
    hit = _user32.WindowFromPoint(POINT(x, y))
    return bool(hit) and _class_name(_user32.GetAncestor(hit, GA_ROOT)) in TRAY_CLASSES


def _pixel(data: bytes, w: int, x: int, y: int) -> tuple[int, int, int]:
    i = (y * w + x) * 4
    return data[i + 2], data[i + 1], data[i]


def median_color(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    return tuple(sorted(p[k] for p in pixels)[len(pixels) // 2] for k in range(3))


def icon_space(data: bytes, w: int, h: int) -> int | None:
    """Rows between the icon's lower edge and the bottom of the button.

    The button's corners give the taskbar color. From the middle row down,
    the icon ends at the first two rows that are all taskbar color, which
    also stops it short of Windows' open-window pill.
    """
    if w < 8 or h < 8:
        return None
    bg = median_color([_pixel(data, w, x, y) for x in (0, 1, w - 2, w - 1) for y in (0, 1, h - 2, h - 1)])

    def marked(y: int) -> bool:
        for x in range(w):
            if max(abs(a - b) for a, b in zip(_pixel(data, w, x, y), bg)) > ICON_CONTRAST:
                return True
        return False

    mid = h // 2
    band = [y for y in range(mid - 3, mid + 4) if marked(y)]
    if not band:
        return None
    for y in range(band[-1] + 1, h - 1):
        if not marked(y) and not marked(y + 1):
            space = h - y
            return space if 2 <= space <= h // 2 else None
    return None


def settle() -> None:
    """Wait until the screen shows windows just hidden as gone."""
    ctypes.windll.dwmapi.DwmFlush()
    time.sleep(0.05)
    ctypes.windll.dwmapi.DwmFlush()


def load_fit() -> dict:
    try:
        data = json.loads(FIT_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_fit(data: dict) -> None:
    FIT_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def round_corners(bits: c_void_p, width: int, height: int, radius: int) -> None:
    """Clear a bitmap outside rounded corners, smoothing the curve's edge."""
    radius = min(radius, width // 2, height // 2)
    if radius <= 0:
        return
    pixels = (ctypes.c_ubyte * (width * height * 4)).from_address(bits.value)
    for j in range(radius):
        for i in range(radius):
            # Distance from this pixel's center to the corner circle's center.
            d = math.hypot(radius - (i + 0.5), radius - (j + 0.5))
            keep = min(1.0, max(0.0, radius + 0.5 - d))
            if keep >= 1.0:
                continue
            for x, y in ((i, j), (width - 1 - i, j), (i, height - 1 - j), (width - 1 - i, height - 1 - j)):
                at = (y * width + x) * 4
                for k in range(4):
                    pixels[at + k] = int(pixels[at + k] * keep)


def highlight_mask(plain: bytes, hover: bytes, w: int, h: int) -> tuple[int, int, int, int, int] | None:
    """Where Windows draws its hover highlight in a button: left, top, right,
    and bottom insets and the corner radius, in pixels."""
    marked = [[max(abs(a - b) for a, b in zip(_pixel(hover, w, x, y), _pixel(plain, w, x, y))) > 3
               for x in range(w)] for y in range(h)]
    xs = [x for y in range(h) for x in range(w) if marked[y][x]]
    ys = [y for y in range(h) if any(marked[y])]
    if not xs or not ys:
        return None
    left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
    if right - left < w // 2 or bottom - top < h // 2:
        return None
    # A circle of radius r leaves about r / 2 pixels open at the end of its
    # first row.
    row = marked[top]
    first = next((x for x in range(left, right + 1) if row[x]), left)
    radius = min(16, round((first - left) * 1.95))
    return left, top, w - 1 - right, h - 1 - bottom, radius


def _blend(a: int, b: int, t: float) -> int:
    t = min(1.0, max(0.0, t))
    out = 0
    for shift in (16, 8, 0):
        ca = (a >> shift) & 0xFF
        cb = (b >> shift) & 0xFF
        out |= round(ca + (cb - ca) * t) << shift
    return out


def _argb(alpha: float, rgb: int) -> int:
    return ((round(min(255, max(0, alpha))) & 0xFF) << 24) | (rgb & 0xFFFFFF)


def _fill(graphics, color: int, shape, x: float, y: float, w: float, h: float) -> None:
    if w <= 0 or h <= 0:
        return
    brush = c_void_p()
    if gdiplus.GdipCreateSolidFill(color, byref(brush)) != 0:
        return
    try:
        shape(graphics, brush, float(x), float(y), float(w), float(h))
    finally:
        gdiplus.GdipDeleteBrush(brush)


class IconWash:
    def __init__(self, color: int):
        self.color = color
        self.bits = None
        # Session marks: None until a Claude Code session reports in.
        self.busy: bool | None = None
        self.done_at = 0.0
        self.share: float | None = None
        self.dot_gap = DOT_GAP
        # Rows under the icon, measured from the screen for this button size.
        self.icon_space: int | None = None
        self.measured: tuple | None = None
        self.retry_at = 0.0
        self.fit = (0, 0, 0, 0, 0)
        self.button_h = 0
        self._drawn: tuple | None = None
        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST,
            "tintja",
            "",
            WS_POPUP,
            0, 0, 10, 10,
            None, None, kernel32.GetModuleHandleW(None), None,
        )
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

    def _ensure_bitmap(self, width: int, height: int) -> None:
        if self.size == (width, height) and self.bitmap:
            return
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
        self.old_bitmap = gdi32.SelectObject(self.mem_dc, self.bitmap)
        self.bits = bits
        self.size = (width, height)
        self._drawn = None

    def _cooling(self, now: float) -> float | None:
        """0 to 1 through the cool-down after a turn ends, else None."""
        if self.busy is not False:
            return None
        k = (now - self.done_at) / COOL_SECONDS
        return k if 0 <= k < 1 else None

    def _paint(self, now: float) -> None:
        width, height = self.size
        if not self.bits or width <= 0 or height <= 0:
            return
        cooling = self._cooling(now)
        animated = self.busy or cooling is not None
        frame = (self.size, self.origin, self.color, self.busy, round(self.share or 0, 3), self.dot_gap, self.icon_space, self.fit)
        if not animated and frame == self._drawn:
            return
        image = c_void_p()
        graphics = c_void_p()
        gdiplus.GdipCreateBitmapFromScan0(width, height, width * 4, PIXEL_FORMAT_32BPP_PARGB, self.bits, byref(image))
        try:
            gdiplus.GdipGetImageGraphicsContext(image, byref(graphics))
            gdiplus.GdipGraphicsClear(graphics, 0)
            gdiplus.GdipSetSmoothingMode(graphics, 4)
            rect = gdiplus.GdipFillRectangle
            _fill(graphics, _argb(0x80, self.color), rect, 0, 0, width, height)
            if self.share:
                _fill(graphics, _argb(0x2E, 0xFFFFFF), rect, 0, 0, width * self.share, height)
            if self.busy is not None:
                self._paint_dot(graphics, now, cooling, width, height)
        finally:
            if graphics:
                gdiplus.GdipDeleteGraphics(graphics)
            if image:
                gdiplus.GdipDisposeImage(image)
        round_corners(self.bits, width, height, self.fit[4])
        origin = POINT(0, 0)
        size = SIZE(width, height)
        dest = POINT(self.origin[0], self.origin[1])
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(
            self.hwnd, self.screen_dc, byref(dest), byref(size),
            self.mem_dc, byref(origin), 0, byref(blend), ULW_ALPHA,
        )
        self._drawn = frame

    def _paint_dot(self, graphics, now: float, cooling: float | None, width: int, height: int) -> None:
        # A circle centered on the highlight's bottom edge, which cuts off its
        # lower half. It reaches up to just under the app icon, so it also
        # covers the open-window pill. Without a measurement, assume Windows'
        # 24-DIP icon centered in the button.
        scale = (user32.GetDpiForWindow(self.hwnd) or 96) / 96
        space = self.icon_space if self.icon_space else (self.button_h - 24 * scale) / 2
        r = max(3.0, space - self.fit[3] - self.dot_gap * scale)
        cx = width / 2
        glow = _blend(self.color, 0xFFFFFF, 0.85)
        dark = _blend(self.color, 0x000000, 0.4)
        if self.busy:
            s = 0.5 - 0.5 * math.cos(2 * math.pi * (now % PULSE_SECONDS) / PULSE_SECONDS)
            core = _blend(self.color, 0xFFFFFF, 0.7 + 0.3 * s)
            halo = 0x28 + 0x50 * s
        elif cooling is not None:
            ease = cooling * cooling * (3 - 2 * cooling)
            core = _blend(glow, dark, ease)
            halo = 0x50 * (1 - ease)
        else:
            core = dark
            halo = 0
        ellipse = gdiplus.GdipFillEllipse
        if halo:
            # A thin rim, so the glow barely reaches the icon.
            big = r * 1.2
            _fill(graphics, _argb(halo, 0xFFFFFF), ellipse, cx - big, height - big, big * 2, big * 2)
        _fill(graphics, _argb(0xF0, core), ellipse, cx - r, height - r, r * 2, r * 2)

    def mark(self, state: tuple[bool, float | None] | None, now: float) -> None:
        busy, share = state if state is not None else (None, None)
        if self.busy and busy is False:
            self.done_at = now
        self.busy = busy
        self.share = share

    def measure(self, x: int, y: int, w: int, h: int, fit: tuple) -> None:
        """Find where the icon ends, with this wash out of the way."""
        if user32.IsWindowVisible(self.hwnd):
            user32.ShowWindow(self.hwnd, SW_HIDE)
            settle()
        data = capture(x, y, w, h)
        # Beside the icon, inside the highlight, a bare taskbar is close to
        # its corners' color, give or take the active app's own faint
        # highlight. If the wash still shows there, the screen had not
        # caught up yet.
        if data and fit[0] + 1 < w:
            inside, corner = _pixel(data, w, fit[0] + 1, h // 2), _pixel(data, w, 0, 1)
            if max(abs(a - b) for a, b in zip(inside, corner)) > 32:
                data = None
        space = icon_space(data, w, h) if data else None
        # A locked screen or a hovered button reads wrong; keep the old value
        # and try again later.
        if space is not None:
            self.icon_space = space
            self.measured = (w, h)
        self._drawn = None

    def place(self, x: int, y: int, w: int, h: int, fit: tuple, color: int, now: float) -> None:
        """Cover the hover highlight of the taskbar button at x, y, w, h.

        fit is the highlight's left, top, right, and bottom insets and its
        corner radius, in pixels.
        """
        if color != self.color:
            self.color = color
        if self.measured != (w, h) and now >= self.retry_at:
            if taskbar_uncovered(x + w // 2, y + h // 2):
                self.measure(x, y, w, h, fit)
            if self.measured != (w, h):
                self.retry_at = now + 30
        left, top, right, bottom, _radius = fit
        self.fit = fit
        self.button_h = h
        hx, hy, hw, hh = x + left, y + top, w - left - right, h - top - bottom
        self.origin = (hx, hy)
        self._ensure_bitmap(hw, hh)
        self._paint(now)
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, hx, hy, hw, hh, SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def animate(self, now: float) -> None:
        if self.busy or self._cooling(now) is not None:
            self._paint(now)


class TaskbarTints:
    def __init__(self) -> None:
        self.enabled = True
        self._automation = c_void_p()
        self._washes: dict[tuple, IconWash] = {}
        self._next_scan = 0.0
        self._fit = load_fit()
        ole32.CoInitialize(None)
        ole32.CoCreateInstance.argtypes = [POINTER(GUID), c_void_p, c_uint32, POINTER(GUID), POINTER(c_void_p)]
        ole32.CoCreateInstance.restype = c_long
        hr = ole32.CoCreateInstance(byref(CLSID), None, CLSCTX_INPROC_SERVER, byref(IID), byref(self._automation))
        if hr != 0 or not self._automation:
            self._automation = c_void_p()

    def close(self) -> None:
        for wash in self._washes.values():
            wash.close()
        self._washes.clear()
        _release(self._automation)
        self._automation = c_void_p()

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        if not self.enabled:
            for wash in self._washes.values():
                wash.close()
            self._washes.clear()
        self._next_scan = 0.0
        return self.enabled

    def remeasure(self) -> None:
        for wash in self._washes.values():
            wash.measured = None
            wash.retry_at = 0.0
        self._next_scan = 0.0

    def _highlight(self, w: int, h: int, hwnd) -> tuple[int, int, int, int, int]:
        """The hover highlight inside a w by h button, in pixels.

        Uses the shape measured on this PC when it was measured for buttons
        this size, and otherwise Windows 11's centered 40 by 40 DIP square
        with 4 DIP corners.
        """
        scale = (user32.GetDpiForWindow(hwnd) or 96) / 96
        saved = self._fit.get("highlight")
        if isinstance(saved, dict) and saved.get("button") == [round(w / scale), round(h / scale)]:
            left, top, right, bottom = (round(v * scale) for v in saved["insets"])
            return left, top, right, bottom, round(saved["radius"] * scale)
        side_w, side_h = min(w, round(DEFAULT_HIGHLIGHT * scale)), min(h, round(DEFAULT_HIGHLIGHT * scale))
        left, top = (w - side_w) // 2, (h - side_h) // 2
        return left, top, w - side_w - left, h - side_h - top, round(DEFAULT_RADIUS * scale)

    def measure_highlight(self, apps: dict, avoid: str | None = None) -> bool:
        """Hover one shelled taskbar button with the mouse and record where
        Windows draws its highlight. Puts the mouse back afterwards."""
        buttons = sorted(self._buttons(apps).values())
        buttons = [b for b in buttons if b[5] != avoid] or buttons
        if not buttons:
            return False
        x, y, w, h = buttons[0][:4]
        if not taskbar_uncovered(x + w // 2, y + h // 2):
            return False
        for wash in self._washes.values():
            user32.ShowWindow(wash.hwnd, SW_HIDE)
        saved = POINT()
        user32.GetCursorPos(byref(saved))
        try:
            settle()
            plain = capture(x, y, w, h)
            # A real mouse move, so the taskbar notices the pointer.
            user32.SetCursorPos(x + w // 2, y + h // 2)
            user32.mouse_event(MOUSEEVENTF_MOVE, 0, 1, 0, 0)
            user32.mouse_event(MOUSEEVENTF_MOVE, 0, -1, 0, 0)
            time.sleep(0.7)
            hover = capture(x, y, w, h)
        finally:
            user32.SetCursorPos(saved.x, saved.y)
            self._next_scan = 0.0
        found = highlight_mask(plain, hover, w, h) if plain and hover else None
        if found is None:
            return False
        scale = (user32.GetDpiForWindow(user32.GetDesktopWindow()) or 96) / 96
        fit = load_fit()
        fit["highlight"] = {
            "button": [round(w / scale), round(h / scale)],
            "insets": [round(v / scale, 1) for v in found[:4]],
            "radius": round(found[4] / scale, 1),
        }
        save_fit(fit)
        self._fit = fit
        for wash in self._washes.values():
            wash._drawn = None
        return True

    def update(self, apps: dict, dot_gap: float = DOT_GAP) -> None:
        now = time.monotonic()
        if not self.enabled:
            return
        if now >= self._next_scan:
            self._next_scan = now + 0.4
            sessions = status.app_states()
            found = self._buttons(apps)
            live = set()
            for key, (x, y, w, h, color, app) in found.items():
                live.add(key)
                wash = self._washes.get(key)
                if wash is None:
                    wash = IconWash(color)
                    self._washes[key] = wash
                wash.mark(sessions.get(app), now)
                wash.dot_gap = dot_gap
                wash.place(x, y, w, h, self._highlight(w, h, wash.hwnd), color, now)
            for key in list(self._washes):
                if key not in live:
                    self._washes.pop(key).close()
        for wash in self._washes.values():
            wash.animate(now)

    def _buttons(self, apps: dict) -> dict[tuple, tuple[int, int, int, int, int, str]]:
        if not self._automation:
            return {}
        labels = [(style.label.casefold(), (style.color, style.key)) for style in apps.values() if style.label]
        found: dict[tuple, tuple[int, int, int, int, int, str]] = {}
        trays = []

        def collect(hwnd, _lparam):
            class_name = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, class_name, 64)
            if class_name.value in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
                trays.append(hwnd)
            return True

        callback = ctypes.WINFUNCTYPE(ctypes.c_bool, c_void_p, ctypes.c_ssize_t)(collect)
        user32.EnumWindows(callback, 0)
        for tray in trays:
            element = c_void_p()
            if ElementFromHandle(_vt(self._automation)[6])(self._automation, tray, byref(element)) != 0 or not element:
                continue
            condition = c_void_p()
            array = c_void_p()
            try:
                if CreateTrueCondition(_vt(self._automation)[21])(self._automation, byref(condition)) != 0:
                    continue
                if FindAll(_vt(element)[6])(element, TREE_DESCENDANTS, condition, byref(array)) != 0 or not array:
                    continue
                length = c_int()
                GetLength(_vt(array)[3])(array, byref(length))
                for index in range(max(0, length.value)):
                    item = c_void_p()
                    if GetElement(_vt(array)[4])(array, index, byref(item)) != 0 or not item:
                        continue
                    try:
                        label, rect = _read_button(item)
                    finally:
                        _release(item)
                    if not label or rect is None:
                        continue
                    folded = label.casefold()
                    match = _matching_color(folded, labels)
                    if match is None:
                        continue
                    color, app = match
                    x, y, w, h = rect
                    if not (8 <= w <= 96 and 8 <= h <= 96):
                        continue
                    found[(folded.split(" - ", 1)[0], x // 8, y // 8)] = (x, y, w, h, color, app)
            finally:
                _release(array)
                _release(condition)
                _release(element)
        return found


def _matching_color(name: str, labels: list[tuple[str, tuple[int, str]]]) -> tuple[int, str] | None:
    for label, match in labels:
        if name == label or name.startswith(label + " ") or name.startswith(label + "-"):
            return match
    return None


def _read_button(item) -> tuple[str, tuple[int, int, int, int] | None]:
    bstr = c_void_p()
    if GetName(_vt(item)[23])(item, byref(bstr)) != 0 or not bstr:
        return "", None
    try:
        name = ctypes.wstring_at(bstr)
    finally:
        oleaut.SysFreeString(bstr)
    left = RECT()
    if GetRect(_vt(item)[43])(item, byref(left)) != 0:
        return name, None
    width = left.right - left.left
    height = left.bottom - left.top
    if width <= 0 or height <= 0:
        return name, None
    return name, (left.left, left.top, width, height)
