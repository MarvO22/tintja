"""50% color washes on the taskbar icons for the shelled apps.

A Claude Code session adds two marks to its app's wash: a lighter fill from
the left that grows with the session's context use, and a half circle on the
bottom edge that glows white while Claude works and cools to a darker shade
of the wash when it is done. status.py supplies both.
"""

from __future__ import annotations

import ctypes
import math
import time
import uuid
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

gdiplus.GdipFillEllipse.argtypes = [c_void_p, c_void_p, c_float, c_float, c_float, c_float]
gdiplus.GdipFillEllipse.restype = c_int

PULSE_SECONDS = 1.6
COOL_SECONDS = 1.4


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
        frame = (self.size, self.origin, self.color, self.busy, round(self.share or 0, 3))
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
        # A circle centered on the bottom edge. The bitmap cuts off its lower half.
        r = max(3.0, min(width, height) * 0.13)
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
            big = r * 2.0
            _fill(graphics, _argb(halo, 0xFFFFFF), ellipse, cx - big, height - big, big * 2, big * 2)
        _fill(graphics, _argb(0xF0, core), ellipse, cx - r, height - r, r * 2, r * 2)

    def mark(self, state: tuple[bool, float | None] | None, now: float) -> None:
        busy, share = state if state is not None else (None, None)
        if self.busy and busy is False:
            self.done_at = now
        self.busy = busy
        self.share = share

    def place(self, x: int, y: int, w: int, h: int, color: int, now: float) -> None:
        if color != self.color:
            self.color = color
        self.origin = (x, y)
        self._ensure_bitmap(w, h)
        self._paint(now)
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def animate(self, now: float) -> None:
        if self.busy or self._cooling(now) is not None:
            self._paint(now)


class TaskbarTints:
    def __init__(self) -> None:
        self.enabled = True
        self._automation = c_void_p()
        self._washes: dict[tuple, IconWash] = {}
        self._next_scan = 0.0
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

    def update(self, apps: dict) -> None:
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
                wash.place(x, y, w, h, color, now)
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
