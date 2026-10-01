"""全局热键注册/改绑 + 键盘钩子看护。"""

import sys

import keyboard
from PySide6.QtCore import QObject, QTimer, Signal

from emoji_palette import sender


class HotkeyBridge(QObject):
    """钩子线程 → 主线程的信号桥(跨线程自动 queued)。"""

    activated = Signal(int)  # 呼出瞬间的前台窗口 hwnd


class HotkeyManager:
    """全局热键注册;改绑 = 先移除再注册(keyboard 库不支持原地改)。"""

    def __init__(self, bridge: HotkeyBridge) -> None:
        self._bridge = bridge
        self._hotkey: str | None = None

    def start(self, hotkey_str: str) -> None:
        self._hotkey = hotkey_str
        keyboard.add_hotkey(hotkey_str, self._on_hotkey, suppress=False)

    def rebind(self, new_hotkey: str) -> None:
        self.stop()
        self.start(new_hotkey)

    def stop(self) -> None:
        if self._hotkey is None:
            return
        try:
            keyboard.remove_hotkey(self._hotkey)
        except (KeyError, ValueError):
            pass  # 已被移除/库状态异常,不抛出
        self._hotkey = None

    def _on_hotkey(self) -> None:
        """钩子线程回调:只做 O(1) 工作,异常全吞(键盘安全优先)。"""
        try:
            hwnd = sender.get_foreground_window()
            self._bridge.activated.emit(hwnd)
        except Exception:  # noqa: BLE001, S110 — 钩子回调严禁抛出
            pass


class HookWatchdog(QObject):
    """每 30s 校验 keyboard 监听线程存活;失活(低级钩子被系统摘除)
    则回调重挂全部钩子并发 rehooked 信号(托盘气泡用)。"""

    rehooked = Signal()

    def __init__(self, rehook, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rehook = rehook
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self._check)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _check(self) -> None:
        try:
            listener = keyboard._listener
            thread = getattr(listener, "listening_thread", None)
            if (getattr(listener, "listening", False) and thread is not None
                    and thread.is_alive()):
                return
            print("[watchdog] 键盘监听线程失活,强制重启并重挂钩子", file=sys.stderr)
            listener.listening = False  # 解除 start_if_necessary 的已启动判定
            self._rehook()
            self.rehooked.emit()
        except Exception:  # noqa: BLE001, S110 — 看护自身不得影响主流程
            pass
