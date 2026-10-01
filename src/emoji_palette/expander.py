"""文本扩展状态机:``::`` 前缀录制 → 匹配 → 回删+注入(DESIGN.md §6.6)。

分层:
- ``Expander``      纯状态机(on_key → (吞键?, 任务?)),表驱动单测的直接靶;
- ``ExpandBridge``  钩子线程 → Qt 主线程信号桥(§3 线程约定,同 HotkeyBridge);
- ``ExpanderHook``  keyboard 库 suppress 钩子适配:门禁节流 + 状态机 + 任务排队。

异常安全硬性要求(§12):任何回调路径异常均「默认放行」——suppress 钩子
吞掉异常键或卡死回调 = 系统键盘失灵,功能失败远轻于键盘失灵。
注入不进钩子线程:SendInput 在低级钩子回调内重入有超时/死锁风险
(LowLevelHooksTimeout,§6.7),任务经信号排队到主线程执行。
"""

import time
from collections.abc import Callable

import keyboard
from PySide6.QtCore import QObject, Signal

Matcher = Callable[[str], str | None]
Gate = Callable[[], bool]

IDLE, ARMED, REC = 0, 1, 2
_MAX_BUF = 24  # §6.6:缓冲超长复位


class Expander:
    """``::`` 录制状态机(§6.6 图):IDLE →(前缀首键)→ ARMED →(前缀余键)→ REC。

    - REC 中 [a-z0-9] 入缓冲,空格触发匹配:命中 → 吞键 + 回删注入任务,
      未命中 → 放行回 IDLE(不打扰正常打字);
    - 非 [a-z0-9 ] / Esc / 超长 → 放行并复位;
    - 门禁(IME 开启/黑名单/总开关)由注入的 ``gate`` 决定:进入录制前与
      录制中(500ms 节流,§6.5「录制期间复查」)咨询,False → 丢缓冲复位。
    前缀所有键、缓冲键均放行(它们是要留在目标窗口的真实文本);
    唯一被吞的键 = 命中时的触发键(空格)。
    """

    def __init__(self, matcher: Matcher, gate: Gate,
                 prefix: str = "::") -> None:
        self._matcher = matcher
        self._gate = gate
        self._prefix = prefix or "::"
        self._state = IDLE
        self._matched = 0  # 前缀已匹配长度(ARMED 推进用)
        self._buf = ""
        self._last_gate = 0.0  # gate 节流时钟(monotonic)

    def set_table(self, matcher: Matcher) -> None:
        """匹配表热替换(别名编辑后立即生效,FR3.5)。"""
        self._matcher = matcher

    def set_prefix(self, prefix: str) -> None:
        self._prefix = prefix or "::"
        self.reset()

    def reset(self) -> None:
        self._state = IDLE
        self._matched = 0
        self._buf = ""

    def _gate_ok(self, now: float) -> bool:
        """门禁咨询:IDLE→ARMED 必查;REC 中 500ms 节流复查。"""
        if self._state == IDLE:
            self._last_gate = now
            return self._gate()
        if now - self._last_gate >= 0.5:
            self._last_gate = now
            if not self._gate():
                self.reset()
                return False
        return True

    def on_key(self, name: str, now: float | None = None) -> tuple[bool, dict | None]:
        """处理一个按键;返回 (suppress, task)。

        task = {"back": 前缀+缓冲长度, "text": emoji 字符},由主线程执行。
        """
        now = now if now is not None else time.monotonic()
        try:
            return self._step(name, now)
        except Exception:  # noqa: BLE001 — 状态机 bug 不得卡键盘
            self.reset()
            return (False, None)

    def _step(self, name: str, now: float) -> tuple[bool, dict | None]:
        if not name:
            return (False, None)

        if self._state == IDLE:
            if name == self._prefix[0] and self._gate_ok(now):
                self._state = ARMED
                self._matched = 1
            return (False, None)

        if self._state == ARMED:
            want = self._prefix[self._matched] if self._matched < len(self._prefix) else None
            if want is not None and name == want:
                self._matched += 1
                if self._matched >= len(self._prefix):
                    self._state = REC
                    self._buf = ""
                    self._last_gate = now
            else:
                self.reset()
            return (False, None)

        # REC
        if not self._gate_ok(now):
            return (False, None)
        if name == "space":
            char = self._matcher(self._buf)
            back = len(self._prefix) + len(self._buf)  # reset 前先记长度
            self.reset()
            if char:
                # 吞触发键 + 回删「前缀+缓冲」再注入(§6.6)
                return (True, {"back": back, "text": char})
            return (False, None)  # 未命中原样放行
        if name == "esc" or not (name.isalnum() and name.isascii() and len(name) == 1):
            self.reset()  # 非录制字符:放行全部缓冲
            return (False, None)
        if len(self._buf) >= _MAX_BUF:
            self.reset()
            return (False, None)
        self._buf += name
        return (False, None)


class ExpandBridge(QObject):
    """钩子线程 → 主线程:回删注入任务(queued,同 §3 线程约定)。"""

    action = Signal(dict)  # {"back": int, "text": str}


class ExpanderHook:
    """keyboard 库 suppress 钩子包装:事件 → 状态机;任务 → 信号。

    回调只做 O(1) 决策(查表 + 状态转移),异常全吞默认放行。
    返回值语义:True=放行 / False=拦截(_winkeyboard 约定,勿再弄反 —— M3 E2E 实测踩坑)。
    """

    def __init__(self, machine: Expander, bridge: ExpandBridge) -> None:
        self._machine = machine
        self._bridge = bridge
        self._hooked = False

    def start(self) -> None:
        if self._hooked:
            return
        keyboard.hook(self._on_event, suppress=True)
        self._hooked = True

    def stop(self) -> None:
        if not self._hooked:
            return
        try:
            keyboard.unhook(self._on_event)
        except (KeyError, ValueError):
            pass  # 库状态异常不抛出
        self._hooked = False

    def _on_event(self, event) -> bool:
        """低级钩子回调(keyboard 库线程)。

        返回值遵循 _winkeyboard.prepare_intercept 约定(与直觉相反):
        True = 放行给下一个程序,False = 拦截。即「不吞」返回 True。
        """
        try:
            if getattr(event, "event_type", None) != "down":
                return True  # 只决策按下;抬起一律放行
            suppress, task = self._machine.on_key(
                str(getattr(event, "name", "") or ""))
            if task:
                self._bridge.action.emit(task)
            return not suppress
        except Exception:  # noqa: BLE001 — 键盘安全 > 功能完整
            return True
