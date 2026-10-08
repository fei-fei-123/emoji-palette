"""SendInput Unicode 注入 / WM_CHAR 直投 / 焦点还原 / 剪贴板降级
(纯 ctypes,零 Qt 依赖)。

上屏时序(调用方负责):
- keep-open 首选 post_char 消息直投,面板不失焦,零前台切换;
- 键盘注入路径先 hide 面板 → 还原焦点 → 注入(keep-open 回落提交后
  由调用方延迟抢回前台)。
非 BMP 字符按 UTF-16 代理对逐 code unit 处理,不使用剪贴板(降级除外)。
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
VK_LSHIFT: int = 0xA0
VK_RSHIFT: int = 0xA1
VK_LCONTROL: int = 0xA2
VK_RCONTROL: int = 0xA3
VK_LMENU: int = 0xA4
VK_RMENU: int = 0xA5
VK_BACK: int = 0x08
WM_CHAR: int = 0x0102
CF_UNICODETEXT: int = 13
GMEM_MOVEABLE: int = 0x0002

# 批尾重压用的物理扫描码:与硬件释放事件一致,keyboard 库状态才能配平
_SCAN_BY_VK = {
    VK_LSHIFT: 0x2A, VK_RSHIFT: 0x36, VK_LCONTROL: 0x1D,
    VK_RCONTROL: 0x1D, VK_LMENU: 0x38, VK_RMENU: 0x38,
}
_MODIFIER_PAIRS = ((VK_LSHIFT, VK_RSHIFT), (VK_LCONTROL, VK_RCONTROL),
                   (VK_LMENU, VK_RMENU))


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


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG),
                ("right", wt.LONG), ("bottom", wt.LONG)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD),
                ("hwndActive", wt.HWND), ("hwndFocus", wt.HWND),
                ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND),
                ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND),
                ("rcCaret", RECT)]


# x64 下 INPUT 必须为 40 字节(union 须含 MOUSEINPUT),否则 SendInput 步长错乱
assert ctypes.sizeof(INPUT) == ctypes.sizeof(MOUSEINPUT) + 8, "INPUT 对齐错误"

# 函数签名一次性声明(x64 下句柄为 64 位,默认 int 截断会出错)
user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = ctypes.c_uint
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wt.HWND
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.PostMessageW.argtypes = (wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM)
user32.PostMessageW.restype = wt.BOOL
# GetWindowThreadProcessId / GetGUIThreadInfo 不设 argtypes:
# 前者项目内有单参调用;后者 user32 进程级共享,一处声明会排斥
# 他处同名结构体(ArgumentError)。GUITHREADINFO 统一用本模块这份。
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


def focus_window(hwnd: int) -> int:
    """所在线程当前的焦点窗口(0=无焦点,即上屏字符的空路由)。"""
    pid = wt.DWORD()
    tid = user32.GetWindowThreadProcessId(wt.HWND(hwnd), ctypes.byref(pid))
    if not tid:
        return 0
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
        return info.hwndFocus or 0
    return 0


def restore_focus(hwnd: int, budget_s: float = 0.3) -> bool:
    """还原焦点到指定窗口:等前台切换且目标线程焦点窗口落位。

    只等前台标志位不够:面板前台期间目标 WM_KILLFOCUS 后线程焦点为
    NULL,目标进程处理 WM_SETFOCUS 是异步的,抢跑注入会让 VK_PACKET
    路由到空焦点静默丢弃。预算内失败敲 Alt 解前台锁重试;超时但前台
    已切换则放行(保留旧行为)。
    """
    if not hwnd:
        return False
    deadline = time.monotonic() + budget_s
    alt_tried = False
    while True:
        user32.SetForegroundWindow(hwnd)
        for _ in range(4):  # 每轮 4 次 × 5ms 校验
            if user32.GetForegroundWindow() == hwnd:
                for _ in range(20):  # 再等焦点落位,最多 100ms
                    if focus_window(hwnd):
                        return True
                    time.sleep(0.005)
                return True
            time.sleep(0.005)
        if time.monotonic() >= deadline:
            return False
        if not alt_tried:  # 中途敲一下 Alt,解前台锁后继续轮询
            alt_tried = True
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)


def _held_modifiers() -> list[int]:
    """注入瞬间物理按住的修饰键(左右区分,批尾按原键重压)。"""
    held = []
    for left, right in _MODIFIER_PAIRS:
        if user32.GetAsyncKeyState(left) & 0x8000:
            held.append(left)
        elif user32.GetAsyncKeyState(right) & 0x8000:
            held.append(right)
    return held


def _build_keystrokes(text: str, backspaces: int,
                      held: list[int]) -> tuple[ctypes.Array, int]:
    """构造注入数组:[松开修饰键][退格×N][Unicode 文本][重压修饰键]。

    按住的 Shift 会让 VK_PACKET 字符被键盘态转写丢弃(Shift+Enter 上屏
    丢失根因),注入前必须合成松开;但松开会清掉 OS 修饰键状态,后续
    Enter 失去 ShiftModifier、keep-open 断成 dismiss,故批尾按原键重压。
    重压必须带物理扫描码:与硬件释放扫描码不一致会毒化 keyboard 库的
    热键匹配(Shift+Enter 后面板无法再唤出的根因)。纯构造不发送,供
    表驱动测试。
    """
    data = text.encode("utf-16-le")
    n_units = len(data) // 2
    arr = (INPUT * (2 * (len(held) + backspaces + n_units)))()
    i = 0
    for vk in held:
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)
        i += 1
    for _ in range(backspaces):
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki = KEYBDINPUT(VK_BACK, 0, 0, 0, 0)
        arr[i + 1].type = INPUT_KEYBOARD
        arr[i + 1].ki = KEYBDINPUT(VK_BACK, 0, KEYEVENTF_KEYUP, 0, 0)
        i += 2
    for j in range(n_units):
        scan = int.from_bytes(data[2 * j:2 * j + 2], "little")  # 含代理对拆分
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki = KEYBDINPUT(0, scan, KEYEVENTF_UNICODE, 0, 0)
        arr[i + 1].type = INPUT_KEYBOARD
        arr[i + 1].ki = KEYBDINPUT(0, scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)
        i += 2
    for vk in held:  # 批尾重压,恢复 OS 修饰键状态
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki = KEYBDINPUT(vk, _SCAN_BY_VK[vk], 0, 0, 0)
        i += 1
    return arr, i


def post_char(hwnd: int, text: str) -> bool:
    """向 hwnd 逐 code unit 投递 WM_CHAR(代理对各一条)。

    keep-open 上屏首选路径:面板不失焦,无前台切换、无键盘注入、无
    盲窗,连击任意速度不掉击。VK_PACKET 注入在目标应用内最终产生的
    就是同样的 WM_CHAR 序列,消息泵应用的兼容面等同。PostMessage 跨
    进程异步无回执:返回 False 仅代表投递失败(hwnd 失效/UIPI 拦截/
    队列满),应用忽略与送达在外部不可区分,由调用方决定是否回落。
    """
    if not hwnd or not text:
        return False
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        unit = int.from_bytes(data[i:i + 2], "little")
        if not user32.PostMessageW(wt.HWND(hwnd), WM_CHAR,
                                   wt.WPARAM(unit), wt.LPARAM(0)):
            return False  # 中途失败即止,避免半截代理对
    return True


def type_text(hwnd: int, text: str, backspaces: int = 0) -> bool:
    """向 hwnd 注入 Unicode 文本(可选前置 N 次退格,文本扩展回删用)。

    全部按键事件合并为单次 SendInput(原子性);任何单元失败返回 False。
    """
    if not text or not restore_focus(hwnd):
        return False
    arr, total = _build_keystrokes(text, backspaces, _held_modifiers())
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
