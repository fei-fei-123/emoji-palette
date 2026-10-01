"""M5 输入模型回归:导航模式 keyPressEvent / 输入模式 eventFilter。

沿 M2 决议:offscreen 下不断言真实 OS 焦点,断言行为效果
(搜索框文本 / 选中行 / 分类行 / 注入捕获);真焦点交真机冒烟。
Win32 副作用(restore_focus 的 Alt 轻敲 / type_text 注入 / 频率落盘)
全部 monkeypatch,测试不骚扰用户桌面。
"""

import copy
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QListWidgetItem  # noqa: F401 — 保证插件加载

import emoji_palette.panel as panel_mod
from emoji_palette import config
from emoji_palette.panel import EmojiPanel
from emoji_palette.search import SearchIndex

# 字符取自 panel._STRIP(浏览模式常用栏底料),保证构造后网格非空
_EMOJI_CHARS = "😀😁😂🤣😊😍🥰😘😜🤔😎😭"
EMOJIS = [
    {"char": ch, "name": f"e{i}", "name_zh": f"项{i}", "cp": f"1F60{i:X}",
     "group": "smileys", "kw_en": (f"kw{i}",), "kw_zh": (f"词{i}",),
     "kw_py": (f"ci{i}",), "kw_abbr": (f"a{i}",)}
    for i, ch in enumerate(_EMOJI_CHARS)
]


def _make_panel(monkeypatch, **overrides) -> EmojiPanel:
    QApplication.instance() or QApplication(sys.argv)  # 确保单例存在
    cfg = copy.deepcopy(config.DEFAULT_CONFIG)
    cfg["hotkey"] = "ctrl+alt+e"
    cfg["panel"].update(overrides)
    injected: list[tuple[str, int]] = []
    monkeypatch.setattr(panel_mod.sender, "restore_focus", lambda *a, **k: True)
    monkeypatch.setattr(panel_mod.sender, "type_text",
                        lambda hwnd, text, backspaces=0: injected.append(text) or True)
    monkeypatch.setattr(panel_mod.config, "bump_frequency", lambda *_: None)
    panel = EmojiPanel(cfg, SearchIndex(EMOJIS, {}, {}))
    panel._injected = injected  # type: ignore[attr-defined]
    return panel


def _press(widget, key: Qt.Key, text: str = "") -> None:
    QApplication.sendEvent(
        widget, QKeyEvent(QEvent.Type.KeyPress, key,
                          Qt.KeyboardModifier.NoModifier, text))


def _release(widget, key: Qt.Key, text: str = "") -> None:
    QApplication.sendEvent(
        widget, QKeyEvent(QEvent.Type.KeyRelease, key,
                          Qt.KeyboardModifier.NoModifier, text))


# ── U3:导航模式(焦点在面板)──────────────────────────────────


def test_typing_from_panel_enters_search_box(monkeypatch):
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    _press(p, Qt.Key.Key_A, "a")
    assert p.search_edit.text() == "a"  # 可打印字符 → 转发进搜索框
    assert p.cat_list.isEnabled() is False  # 进入搜索模式(分类淡化)


def test_arrows_navigate_grid(monkeypatch):
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    cols = p._columns
    _press(p, Qt.Key.Key_Right)
    assert p.grid.currentRow() == 1
    _press(p, Qt.Key.Key_Down)
    assert p.grid.currentRow() == 1 + cols
    _press(p, Qt.Key.Key_Left)
    assert p.grid.currentRow() == cols
    _press(p, Qt.Key.Key_Up)
    assert p.grid.currentRow() == 0


def test_plus_minus_switch_category_and_clear_text(monkeypatch):
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    _press(p, Qt.Key.Key_A, "a")
    assert p.search_edit.text() == "a"
    _press(p, Qt.Key.Key_Equal, "=")  # +/= → 下一分类,且先清搜索文本
    assert p.search_edit.text() == ""
    assert p.cat_list.currentRow() == 1
    _press(p, Qt.Key.Key_Minus, "-")
    assert p.cat_list.currentRow() == 0
    _press(p, Qt.Key.Key_Minus, "-")  # clamp 在首类
    assert p.cat_list.currentRow() == 0


def test_digit_quick_submit_with_text(monkeypatch):
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    p.search_edit.setText("kw")  # 搜索模式,多结果
    assert p.grid.count() > 2
    _press(p, Qt.Key.Key_2, "2")
    assert p._injected == [p.grid.item(1).data(Qt.ItemDataRole.UserRole)["char"]]


def test_esc_dismiss_from_panel(monkeypatch):
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    _press(p, Qt.Key.Key_Escape)
    assert not p.isVisible()


# ── U3:输入模式(搜索框 eventFilter)─────────────────────────


def test_search_up_down_returns_to_panel_and_moves_vertically(monkeypatch):
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    p.search_edit.setText("kw")
    cols = p._columns
    _press(p.search_edit, Qt.Key.Key_Down)
    assert p.grid.currentRow() == cols  # ↑↓ = 纵向移动一行
    _press(p.search_edit, Qt.Key.Key_Up)
    assert p.grid.currentRow() == 0


def test_search_arrows_stay_caret(monkeypatch):
    """输入模式 ←→ 交 QLineEdit(文本光标),不移动网格选中。"""
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    p.search_edit.setText("kw")
    p.search_edit.setCursorPosition(0)
    _press(p.search_edit, Qt.Key.Key_Right)
    assert p.grid.currentRow() == 0  # 选中不动
    assert p.search_edit.cursorPosition() == 1  # 光标移动(QLineEdit 默认)


def test_search_plus_minus_clears_then_switches(monkeypatch):
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    p.cat_list.setCurrentRow(2)
    p.search_edit.setText("kw")
    _press(p.search_edit, Qt.Key.Key_Plus, "+")
    assert p.search_edit.text() == ""  # 先清空(消互斥)
    assert p.cat_list.currentRow() == 3  # 再切换


def test_search_enter_submits_current(monkeypatch):
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    p.search_edit.setText("kw")
    _press(p.search_edit, Qt.Key.Key_Return, "\r")
    assert len(p._injected) == 1
    assert not p.isVisible()  # 默认 close_after_submit=True


def test_search_tab_returns_focus_to_panel(monkeypatch):
    """输入模式 Tab:框↔面板互换(行为断言:再按 ←→ 表现为面板横移)。"""
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    p.search_edit.setText("kw")
    _press(p.search_edit, Qt.Key.Key_Tab, "\t")
    assert p.search_edit.text() == "kw"  # 不清文本(仅换焦点目标)
    _press(p, Qt.Key.Key_Right)  # 经面板导航:横移一格
    assert p.grid.currentRow() == 1


# ── U2:BUG② 热键末键残留过滤 ─────────────────────────────────


def test_residual_trigger_key_swallowed(monkeypatch):
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=True)  # 热键 ctrl+alt+e → 末键 E
    assert p._tail is not None
    _press(p, Qt.Key.Key_E, "e")  # 仍按住/自动重复的 E
    assert p.search_edit.text() == ""  # 不进搜索框
    assert p.grid.currentRow() == 0
    _release(p, Qt.Key.Key_E, "e")
    assert p._tail is None  # KeyRelease 解除过滤
    _press(p, Qt.Key.Key_E, "e")
    assert p.search_edit.text() == "e"  # 之后正常打字


def test_residual_filter_search_edit_path(monkeypatch):
    """末键残留落在搜索框 eventFilter 路径同样被吞。"""
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=True)
    p.search_edit.setFocus()
    _press(p.search_edit, Qt.Key.Key_E, "e")
    assert p.search_edit.text() == ""
    _release(p.search_edit, Qt.Key.Key_E, "e")
    _press(p.search_edit, Qt.Key.Key_E, "e")
    assert p.search_edit.text() == "e"


def test_tray_popup_does_not_arm_filter(monkeypatch):
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    assert p._tail is None
    _press(p, Qt.Key.Key_E, "e")
    assert p.search_edit.text() == "e"  # 无过滤,直接入框


# ── U4:keep-open ─────────────────────────────────────────────


def test_submit_default_closes(monkeypatch):
    p = _make_panel(monkeypatch)
    p.popup(0, from_hotkey=False)
    entry = p.grid.item(0).data(Qt.ItemDataRole.UserRole)
    p._submit(entry)
    assert len(p._injected) == 1
    assert not p.isVisible()


def test_submit_keep_open_stays_visible(monkeypatch):
    p = _make_panel(monkeypatch, close_after_submit=False)
    p.popup(0, from_hotkey=False)
    entry = p.grid.item(0).data(Qt.ItemDataRole.UserRole)
    p._submit(entry, keep_open=p._keep_open_for(False))  # 走配置判定路径
    assert len(p._injected) == 1
    assert p.isVisible()  # 配置恒开:面板不关
    assert p.grid.currentRow() == 1  # 选中项下移一行(连续上屏)


class _NoActiveApp:
    """伪造 QApplication.activeWindow()→None(panel.event 失活判定用)。"""

    @staticmethod
    def activeWindow():
        return None


def test_hold_grace_blocks_deactivation_close(monkeypatch):
    """keep-open 注入瞬间面板失活(焦点去目标应用),宽限期内不得关。"""
    from PySide6.QtCore import QEvent as QEventBase

    p = _make_panel(monkeypatch, close_after_submit=False)
    p.popup(0, from_hotkey=False)
    # offscreen 下 activeWindow 恒为面板自身,失活场景须伪造静态方法;
    # _popup_ts 置旧以越过呼出 300ms 宽限(坑 #11)
    monkeypatch.setattr(panel_mod, "QApplication", _NoActiveApp)
    p._popup_ts = 0.0
    # grace 未到:失活事件被豁免
    p._hold_grace = 1e18
    p.event(QEventBase(QEventBase.Type.ActivationChange))
    assert p.isVisible()
    # grace 已过 + 呼出宽限已过:失活即关(点外关闭原语义)
    p._hold_grace = 0.0
    p.event(QEventBase(QEventBase.Type.ActivationChange))
    assert not p.isVisible()
