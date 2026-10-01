"""QKeySequence ↔ keyboard 库热键串换算测试。

裸字符键必须换算失败(否则全局抑制会吞掉正常打字);
windows 修饰键双向映射;未知/空序列 → ""。
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QKeySequence

from emoji_palette.settings_ui import (
    keyboard_to_qt,
    qt_to_keyboard_hotkey,
)


def test_normal_combo():
    assert qt_to_keyboard_hotkey(QKeySequence("Ctrl+Alt+E")) == "ctrl+alt+e"
    assert qt_to_keyboard_hotkey(QKeySequence("Shift+Ctrl+Tab")) == "ctrl+shift+tab"


def test_bare_key_rejected():
    # 无修饰裸键会吞掉正常打字,必须拒绝
    assert qt_to_keyboard_hotkey(QKeySequence("E")) == ""
    assert qt_to_keyboard_hotkey(QKeySequence("Space")) == ""


def test_pure_modifier_rejected():
    assert qt_to_keyboard_hotkey(QKeySequence("Ctrl")) == ""
    assert qt_to_keyboard_hotkey(QKeySequence("Ctrl+Alt")) == ""


def test_meta_maps_to_windows():
    assert qt_to_keyboard_hotkey(QKeySequence("Meta+K")) == "windows+k"
    assert keyboard_to_qt("windows+k") == "Meta+K"


def test_function_key_ok():
    assert qt_to_keyboard_hotkey(QKeySequence("Ctrl+F1")) == "ctrl+f1"


def test_empty_sequence():
    assert qt_to_keyboard_hotkey(QKeySequence()) == ""
    assert keyboard_to_qt("") == ""


def test_roundtrip():
    for hotkey in ("ctrl+alt+e", "alt+shift+p", "windows+k"):
        assert qt_to_keyboard_hotkey(QKeySequence(keyboard_to_qt(hotkey))) == hotkey
