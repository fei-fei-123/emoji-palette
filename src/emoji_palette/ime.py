"""IME 状态检测 + 前台进程名查询(纯 ctypes,永不抛错:钩子回调安全)。"""

import ctypes
import ctypes.wintypes as wt

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
imm32 = ctypes.windll.imm32

WM_IME_CONTROL = 0x283
IMC_GETOPENSTATUS = 5
IMC_GETCONVERSIONMODE = 0x0001  # WinUser.h 文档值(0x0101 为讹传,不响应)
IME_CMODE_NATIVE = 0x0001       # 原生转写位(中文等)
IME_CMODE_FULLSHAPE = 0x0008    # 全角位
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
    """前台(或指定)窗口的 IME 是否开启;失败一律按关闭处理。"""
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


def ime_transcribing(hwnd: int | None = None) -> bool:
    """IME 是否处于「会转写按键」的模式:中文原生/全角子模式 → True
    (按键归 IME,文本扩展让位);英文半角子模式 → False。

    判定 = 开合状态 ∧ 转写模式位,均经 WM_IME_CONTROL 探针
    (ImmGetConversionStatus 在 TSF 应用上拿不到上下文,不可用)。
    无响应的 IME 无法与「英文子模式」区分,误判为英文态,可接受。
    """
    try:
        hwnd = hwnd or user32.GetForegroundWindow()
        if not hwnd:
            return False
        hime = imm32.ImmGetDefaultIMEWnd(hwnd)
        if not hime:
            return False
        if not user32.SendMessageW(hime, WM_IME_CONTROL, IMC_GETOPENSTATUS, 0):
            return False  # IME 关闭(纯英文键盘)
        mode = user32.SendMessageW(hime, WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0)
        return bool(mode & (IME_CMODE_NATIVE | IME_CMODE_FULLSHAPE))
    except Exception:  # noqa: BLE001 — 钩子路径永不抛错
        return False


def foreground_process_name() -> str:
    """前台窗口所属进程名(小写含 .exe);失败返回空串。"""
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
