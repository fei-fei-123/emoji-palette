"""全局热键注册/改绑 + 钩子保活 Watchdog(DESIGN.md §6.1/§6.7)。

Watchdog(M4)偏差实现:不发测试键(§6.7 原案的全局注入在本机不可靠,
且会向用户前台应用打进按键),改为 30s 校验 keyboard 监听线程存活,
失活即强制重启监听 + 业务层重挂钩子(决议见 DEVLOG)。
"""

import sys

import keyboard
from PySide6.QtCore import QObject, QTimer, Signal

from emoji_palette import sender


class HotkeyBridge(QObject):
    """钩子线程 → 主线程的信号桥(AutoConnection 跨线程自动 queued,§3)。"""

    activated = Signal(int)  # 呼出瞬间的前台窗口 hwnd


class HotkeyManager:
    """add_hotkey 包装:改绑 = 先移除再注册(keyboard 库不支持原地改)。"""

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
        """钩子线程回调:只做 O(1) 工作,异常全吞(键盘安全 > 功能完整,§12)。"""
        try:
            hwnd = sender.get_foreground_window()
            self._bridge.activated.emit(hwnd)
        except Exception:  # noqa: BLE001, S110 — 钩子回调严禁抛出,静默即键盘安全
            pass


class HookWatchdog(QObject):
    """钩子活性看护(§6.7,M4):30s 校验 keyboard 监听线程存活。

    失活(低级钩子被系统摘除后线程退出/GC 停顿致死)→ 置 listening=False
    让 start_if_necessary 可重启,再回调 rehook 由业务层重挂全部钩子;
    rehooked 信号供托盘气泡(app 侧节流 ≤1 次/小时,§6.7)。
    """

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
