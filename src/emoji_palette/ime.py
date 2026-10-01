"""IME 开合状态检测 + 前台进程名查询(DESIGN.md §6.5)。

纯 ctypes 零 Qt 依赖。FR4.3 硬性要求:焦点窗口中文输入法开启时
文本扩展自动暂停(按键归 IME 所有);FR4.4 黑名单按前台进程名旁路。
调用方为键盘钩子回调,函数保持轻量且永不抛错(失败一律按「不活跃」
或空名处理,宁可扩展失效也不打扰打字)。
"""

import ctypes
import ctypes.wintypes as wt

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
imm32 = ctypes.windll.imm32

WM_IME_CONTROL = 0x283
IMC_GETOPENSTATUS = 5
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

imm32.ImmGetDefaultIMEWnd.argtypes = (wt.HWND,)
imm32.ImmGetDefaultIMEWnd.restype = wt.HWND

kernel32.OpenProcess.argtypes = (wt.DWORD, wt.BOOL, wt.DWORD)
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (
    wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD))
kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
kernel32.CloseHandle.argtypes = (wt.HANDLE,)


def ime_open(hwnd: int | None = None) -> bool:
    """前台(或指定)窗口的 IME 是否处于开启状态(§6.5)。

    无前台/无默认 IME 窗口/SendMessage 异常 → False(视为英文态)。
    """
    try:
        hwnd = hwnd or user32.GetForegroundWindow()
        if not hwnd:
            return False
        hime = imm32.ImmGetDefaultIMEWnd(hwnd)
        if not hime:
            return False
        return bool(user32.SendMessageW(hime, WM_IME_CONTROL, IMC_GETOPENSTATUS, 0))
    except Exception:  # noqa: BLE001 — 钩子路径永不抛错
        return False


def foreground_process_name() -> str:
    """前台窗口所属进程名(小写含 .exe);失败返回空串。

    tid 反查 pid → OpenProcess(仅查询权限)→ 全路径取尾部。
    """
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = wt.DWORD(512)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value.rsplit("\\", 1)[-1].lower()
            return ""
        finally:
            kernel32.CloseHandle(h)
    except Exception:  # noqa: BLE001
        return ""
