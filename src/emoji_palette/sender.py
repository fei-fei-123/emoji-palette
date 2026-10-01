"""SendInput Unicode 注入 / 焦点还原 / 剪贴板降级(纯 ctypes,零 Qt 依赖)。

上屏时序(调用方负责):先 hide 面板 → 还原焦点 → 注入。
非 BMP 字符按 UTF-16 代理对逐 code unit 注入,不使用剪贴板(降级除外)。
"""

import ctypes
import ctypes.wintypes as wt
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

INPUT_KEYBOARD: int = 1
KEYEVENTF_UNICODE: int = 0x0004
KEYEVENTF_KEYUP: int = 0x0002
VK_MENU: int = 0x12
VK_BACK: int = 0x08
CF_UNICODETEXT: int = 13
GMEM_MOVEABLE: int = 0x0002


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_ushort), ("wParamH", ctypes.c_ushort)]


class _INPUTU(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTU)]


# x64 下 INPUT 必须为 40 字节(union 须含 MOUSEINPUT),否则 SendInput 步长错乱
assert ctypes.sizeof(INPUT) == ctypes.sizeof(MOUSEINPUT) + 8, "INPUT 对齐错误"

# 函数签名一次性声明(x64 下句柄为 64 位,默认 int 截断会出错)
user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = ctypes.c_uint
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wt.HWND
user32.SetForegroundWindow.argtypes = (wt.HWND,)
user32.SetForegroundWindow.restype = wt.BOOL
user32.keybd_event.argtypes = (ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong,
                               ctypes.c_size_t)
user32.OpenClipboard.argtypes = (wt.HWND,)
user32.OpenClipboard.restype = wt.BOOL
user32.CloseClipboard.argtypes = ()
user32.CloseClipboard.restype = wt.BOOL
user32.EmptyClipboard.argtypes = ()
user32.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
user32.SetClipboardData.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)


def get_foreground_window() -> int:
    """当前前台窗口句柄;无前台返回 0。"""
    return user32.GetForegroundWindow() or 0


def restore_focus(hwnd: int, budget_s: float = 0.3) -> bool:
    """还原焦点到指定窗口:SetForegroundWindow + 轮询校验,
    预算内失败则敲一次 Alt 解前台锁再重试。"""
    if not hwnd:
        return False
    deadline = time.monotonic() + budget_s
    alt_tried = False
    while True:
        user32.SetForegroundWindow(hwnd)
        for _ in range(4):  # 每轮 4 次 × 5ms 校验
            if user32.GetForegroundWindow() == hwnd:
                return True
            time.sleep(0.005)
        if time.monotonic() >= deadline:
            return False
        if not alt_tried:  # 中途敲一下 Alt,解前台锁后继续轮询
            alt_tried = True
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)


def type_text(hwnd: int, text: str, backspaces: int = 0) -> bool:
    """向 hwnd 注入 Unicode 文本(可选前置 N 次退格,文本扩展回删用)。

    全部按键事件合并为单次 SendInput(原子性);任何单元失败返回 False。
    """
    if not text or not restore_focus(hwnd):
        return False
    data = text.encode("utf-16-le")
    n_units = len(data) // 2
    arr = (INPUT * (2 * (n_units + backspaces)))()
    for b in range(backspaces):
        arr[2 * b].type = INPUT_KEYBOARD
        arr[2 * b].ki = KEYBDINPUT(VK_BACK, 0, 0, 0, 0)
        arr[2 * b + 1].type = INPUT_KEYBOARD
        arr[2 * b + 1].ki = KEYBDINPUT(VK_BACK, 0, KEYEVENTF_KEYUP, 0, 0)
    for i in range(n_units):
        scan = int.from_bytes(data[2 * i:2 * i + 2], "little")  # 含代理对拆分
        down, up = arr[2 * (backspaces + i)], arr[2 * (backspaces + i) + 1]
        down.type = INPUT_KEYBOARD
        down.ki = KEYBDINPUT(0, scan, KEYEVENTF_UNICODE, 0, 0)
        up.type = INPUT_KEYBOARD
        up.ki = KEYBDINPUT(0, scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)
    total = 2 * (n_units + backspaces)
    sent = user32.SendInput(total, arr, ctypes.sizeof(INPUT))
    return sent == total


def clipboard_fallback(text: str) -> bool:
    """剪贴板降级:注入失败(如提权窗口)时复制文本,任何异常返回 False。"""
    try:
        if not text or not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            buf = text.encode("utf-16-le") + b"\x00\x00"
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(buf))
            if not handle:
                return False
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                kernel32.GlobalFree(handle)
                return False
            ctypes.memmove(ptr, buf, len(buf))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                kernel32.GlobalFree(handle)
                return False
            return True  # 所有权已移交系统,不得再 GlobalFree
        finally:
            user32.CloseClipboard()
    except Exception:  # noqa: BLE001 — 降级路径不得抛错
        return False
