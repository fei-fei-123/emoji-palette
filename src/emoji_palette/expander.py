"""``::`` 前缀录制 → 候选条交互状态机。

分层:
- ``Expander``      纯状态机(on_key → (吞键?, 事件?)),表驱动单测的靶;
- ``ExpandBridge``  钩子线程 → Qt 主线程信号桥;
- ``ExpanderHook``  keyboard 库 suppress 钩子适配:状态机 + 事件排队。

字符解析/匹配在主线程完成,钩子线程只做 O(1) 状态转移;主线程每次
刷新候选后回写「有无候选」(set_has_candidates),作为吞键依据。

REC 态按键规则:字母/无候选数字放行入缓冲;空格/Enter/数字 1-9 在
有候选时吞下并提交,无候选放行复位;Esc/↑↓ 吞下并关条;←/→ 有候选
时劫持为条内移动(透传会破坏回删数假设);修饰键放行且不打断状态
(前缀 ``:`` 需按住 Shift,修饰流不得复位状态机);其余键放行复位。
异常路径一律放行 —— 键盘安全硬约束。
注入不进钩子线程:SendInput 在低级钩子回调内重入有超时/死锁风险,
事件经信号排队到主线程执行。
"""

import time
from collections.abc import Callable

import keyboard
from PySide6.QtCore import QObject, Signal

Gate = Callable[[], bool]

IDLE, ARMED, REC = 0, 1, 2
_MAX_BUF = 24
_DIGITS = "123456789"  # 0 无对应格,照常入缓冲(如 ``100`` 类词)

# 修饰键名(keyboard 库报法):放行且不打断状态
_MODIFIER_KEYS = frozenset({
    "shift", "ctrl", "alt", "alt gr", "windows",
    "left shift", "right shift", "left ctrl", "right ctrl",
    "left alt", "right alt", "left windows", "right windows",
})


class Expander:
    """``::`` 录制状态机:IDLE →(前缀首键)→ ARMED →(前缀余键)→ REC。"""

    def __init__(self, gate: Gate, prefix: str = "::") -> None:
        self._gate = gate
        self._prefix = prefix or "::"
        self._state = IDLE
        self._matched = 0  # 前缀已匹配长度(ARMED 推进用)
        self._buf = ""
        self._has_cand = False  # 主线程回写(候选条当前有无候选)
        self._last_gate = 0.0  # gate 节流时钟(monotonic)

    def set_has_candidates(self, flag: bool) -> None:
        """主线程在每次条刷新后回写(GIL 原子读写,空格/数字吞键依据)。"""
        self._has_cand = bool(flag)

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
        """处理一个按键;返回 (suppress, event)。event 为 compose 事件或 None。"""
        now = now if now is not None else time.monotonic()
        try:
            return self._step(name, now)
        except Exception:  # noqa: BLE001 — 状态机 bug 不得卡键盘
            self.reset()
            return (False, None)

    def _ev(self, kind: str, **kw) -> dict:
        ev = {"event": kind, "buf": self._buf, "n": 0, "back": 0}
        ev.update(kw)
        return ev

    def _step(self, name: str, now: float) -> tuple[bool, dict | None]:
        if not name:
            return (False, None)

        if self._state == IDLE:
            if name == self._prefix[0] and self._gate_ok(now):
                self._state = ARMED
                self._matched = 1
            return (False, None)

        if self._state == ARMED:
            if name in _MODIFIER_KEYS:
                return (False, None)  # 修饰流不打断(两个 `:` 之间的 shift)
            want = self._prefix[self._matched] if self._matched < len(self._prefix) else None
            if want is not None and name == want:
                self._matched += 1
                if self._matched >= len(self._prefix):
                    self._state = REC
                    self._buf = ""
                    self._last_gate = now
                    return (False, self._ev("show"))
            else:
                self.reset()
            return (False, None)

        # ── REC:候选条交互 ──────────────────────────────────────
        if name in _MODIFIER_KEYS:
            return (False, None)  # 修饰键放行不收条(按住 Shift 打字等场景)
        if not self._gate_ok(now):
            return (False, self._ev("close"))  # reset 已在 _gate_ok 内完成

        if name == "space" or name == "enter":
            if self._has_cand:
                ev = self._ev("commit", back=len(self._prefix) + len(self._buf))
                self.reset()
                return (True, ev)  # 吞触发键 + 回删「前缀+缓冲」再注入
            self.reset()
            return (False, self._ev("close"))  # 未命中原样放行
        if name == "esc":
            self.reset()
            return (True, self._ev("close"))
        if name in ("up", "down"):  # ↑↓ 关条(退出候选,回正常输入)
            self.reset()
            return (True, self._ev("close"))
        if name in ("left", "right") and self._has_cand:
            # 劫持为条内移动;无候选时落入「其他」分支放行关条。
            # 方向键会破坏「回删数 = 缓冲长」的镜像假设(光标移进文本中部),
            # 故 REC 态有候选时必须挡下,不能透传。
            return (True, self._ev(name))
        if name == "backspace":
            if self._buf:  # 应用侧自删(放行),状态机镜像 pop
                self._buf = self._buf[:-1]
                return (False, self._ev("update"))
            self.reset()
            return (False, self._ev("close"))  # 退到前缀首键前 → 收条复位
        if name in _DIGITS and self._has_cand:
            ev = self._ev("digit", n=int(name),
                          back=len(self._prefix) + len(self._buf))
            self.reset()
            return (True, ev)
        if not (name.isalnum() and name.isascii() and len(name) == 1):
            self.reset()  # 其他键:放行并复位收条
            return (False, self._ev("close"))
        if len(self._buf) >= _MAX_BUF:
            self.reset()
            return (False, self._ev("close"))
        self._buf += name  # 字母 / 无候选数字:放行入缓冲
        return (False, self._ev("update"))


class ExpandBridge(QObject):
    """钩子线程 → 主线程:候选条 compose 事件(queued)。"""

    compose = Signal(dict)  # {"event": show/update/close/left/right/digit/commit, ...}


class ExpanderHook:
    """keyboard 库 suppress 钩子包装:事件 → 状态机;compose → 信号。"""

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

        返回值遵循 _winkeyboard 约定(与直觉相反):
        True = 放行给下一个程序,False = 拦截。
        """
        try:
            if getattr(event, "event_type", None) != "down":
                return True  # 只决策按下;抬起一律放行
            suppress, ev = self._machine.on_key(
                str(getattr(event, "name", "") or ""))
            if ev:
                self._bridge.compose.emit(ev)
            return not suppress
        except Exception:  # noqa: BLE001 — 键盘安全 > 功能完整
            return True
