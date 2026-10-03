"""type_text 注入序列构造回归:修饰键夹逼(批头松开/批尾重压)、
UTF-16 拆分、前置退格。

只测纯构造函数 _build_keystrokes(不 SendInput,不骚扰桌面);
修饰键采样 _held_modifiers 以 monkeypatch GetAsyncKeyState 驱动。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from emoji_palette import sender
from emoji_palette.sender import (
    INPUT_KEYBOARD,
    KEYEVENTF_KEYUP,
    KEYEVENTF_UNICODE,
    VK_BACK,
    VK_LCONTROL,
    VK_LMENU,
    VK_LSHIFT,
    VK_RSHIFT,
    _build_keystrokes,
    _held_modifiers,
)


def _units(arr, n):
    """展开为 (type, vk, scan, flags) 元组序列,便于整批断言。"""
    return [(arr[i].type, arr[i].ki.wVk, arr[i].ki.wScan, arr[i].ki.dwFlags)
            for i in range(n)]


def _pair(scan):
    """一个 code unit 的 [down, up] 期望值(列表,便于整批拼接)。"""
    return [(INPUT_KEYBOARD, 0, scan, KEYEVENTF_UNICODE),
            (INPUT_KEYBOARD, 0, scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]


def test_plain_ascii():
    arr, total = _build_keystrokes("a", 0, [])
    assert total == 2
    assert _units(arr, total) == _pair(0x61)


def test_surrogate_pair_split():
    # 😀 U+1F600 → UTF-16 代理对 D83D DE00,逐 code unit down/up
    arr, total = _build_keystrokes("😀", 0, [])
    assert total == 4
    assert _units(arr, total) == _pair(0xD83D) + _pair(0xDE00)


def test_backspaces_precede_text():
    arr, total = _build_keystrokes("x", 2, [])
    assert total == 6
    units = _units(arr, total)
    assert units[:4] == [(INPUT_KEYBOARD, VK_BACK, 0, 0),
                         (INPUT_KEYBOARD, VK_BACK, 0, KEYEVENTF_KEYUP)] * 2
    assert units[4:] == _pair(0x78)


def test_modifiers_clamped_then_repressed():
    # Shift+Enter 提交场景:批头合成松开先于字符;批尾按原键重压恢复
    # OS 修饰键状态(keep-open 连击不断),重压必须带物理扫描码
    arr, total = _build_keystrokes("😀", 0, [VK_LSHIFT])
    units = _units(arr, total)
    assert units[0] == (INPUT_KEYBOARD, VK_LSHIFT, 0, KEYEVENTF_KEYUP)
    assert units[1:-1] == _pair(0xD83D) + _pair(0xDE00)
    assert units[-1] == (INPUT_KEYBOARD, VK_LSHIFT, 0x2A, 0)


def test_modifier_order_and_multi_mods():
    arr, total = _build_keystrokes("a", 0, [VK_LSHIFT, VK_LCONTROL, VK_LMENU])
    units = _units(arr, total)
    assert [u[1] for u in units[:3]] == [VK_LSHIFT, VK_LCONTROL, VK_LMENU]
    assert all(u[3] == KEYEVENTF_KEYUP for u in units[:3])
    assert units[3:5] == _pair(0x61)
    # 批尾重压顺序与批头一致,各带物理扫描码
    assert [u[1] for u in units[5:]] == [VK_LSHIFT, VK_LCONTROL, VK_LMENU]
    assert [u[2] for u in units[5:]] == [0x2A, 0x1D, 0x38]
    assert all(u[3] == 0 for u in units[5:])


def test_held_modifiers_samples_only_pressed(monkeypatch):
    # GetAsyncKeyState 高位 0x8000 = 按下;左右修饰键区分采样
    pressed = {VK_LSHIFT: 0x8000}
    monkeypatch.setattr(
        sender.user32, "GetAsyncKeyState",
        lambda vk: pressed.get(vk, 0))
    assert _held_modifiers() == [VK_LSHIFT]
    pressed = {VK_RSHIFT: 0x8000}  # 右 Shift → 采到右键
    assert _held_modifiers() == [VK_RSHIFT]
    # 全松开 → 空表,注入序列不夹带修饰键事件
    monkeypatch.setattr(sender.user32, "GetAsyncKeyState", lambda vk: 0)
    assert _held_modifiers() == []


def test_gui_threadinfo_shared_declaration():
    # 回归:user32 进程级共享,自设 argtypes 会排斥他处结构体
    # (ArgumentError);约定不设,结构体统一复用 sender.GUITHREADINFO
    from emoji_palette import candidate  # noqa: F401 — 导入即应用模块级声明

    assert sender.user32.GetGUIThreadInfo.argtypes is None
    # 布局完整:缺 hwndMenuOwner/hwndMoveSize 会让 hwndCaret/rcCaret 错位
    names = [f[0] for f in sender.GUITHREADINFO._fields_]
    assert names == ["cbSize", "flags", "hwndActive", "hwndFocus",
                     "hwndCapture", "hwndMenuOwner", "hwndMoveSize",
                     "hwndCaret", "rcCaret"]
