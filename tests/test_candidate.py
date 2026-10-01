"""候选条 CandidateBar 状态机测试(offscreen)。

不测真实激活/点击穿透,测状态驱动与布局尺寸;点击外部检测
只验证定时器启停,GetAsyncKeyState 读数不参与断言。
"""

import copy
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize  # noqa: F401 — 保证插件加载
from PySide6.QtWidgets import QApplication

from emoji_palette import config
from emoji_palette.candidate import CandidateBar


def _bar(**overrides) -> CandidateBar:
    QApplication.instance() or QApplication(sys.argv)
    cfg = copy.deepcopy(config.DEFAULT_CONFIG)
    cfg["panel"].update(overrides)
    return CandidateBar(cfg)


def _items(*chars: str) -> list[tuple[dict, str]]:
    return [({"char": c, "cp": "1F600"}, f"term{i}") for i, c in enumerate(chars)]


def test_update_defaults_when_buf_empty():
    bar = _bar()
    bar.set_default_items(_items("😀", "😁"))
    bar.update_candidates(None, "")
    assert [e["char"] for e, _t in bar._items] == ["😀", "😁"]
    assert bar.selected() is not None and bar.selected()[0]["char"] == "😀"


def test_update_no_match_keeps_bar_open():
    """无命中:条不关,进入无匹配态。"""
    bar = _bar()
    bar.set_default_items(_items("😀"))
    bar.update_candidates([], "zzz")
    assert bar._no_match and bar._items == []
    assert bar.selected() is None
    assert bar.isVisible()  # 条仍开着
    assert bar._poll.isActive()  # 点击外部检测在跑


def test_move_selection_wraps():
    bar = _bar()
    bar.set_default_items(_items("😀", "😁", "😂"))
    bar.update_candidates(None, "")
    bar.move_selection(1)
    assert bar.selected()[0]["char"] == "😁"
    bar.move_selection(1)
    bar.move_selection(1)
    assert bar.selected()[0]["char"] == "😀"  # 循环
    bar.move_selection(-1)
    assert bar.selected()[0]["char"] == "😂"  # 负向也循环


def test_item_at_index_bounds():
    bar = _bar()
    bar.set_default_items(_items("😀", "😁"))
    bar.update_candidates(None, "")
    assert bar.item_at_index(0)[0]["char"] == "😀"
    assert bar.item_at_index(1)[0]["char"] == "😁"
    assert bar.item_at_index(2) is None
    assert bar.item_at_index(-1) is None


def test_layout_scales_with_items():
    bar = _bar()
    bar.set_default_items(_items(*"abcde"))
    bar.update_candidates(None, "")
    w5 = bar.width()
    bar.update_candidates(_items(*"ab"), "a")  # 非空 buf:用显式候选
    assert bar.width() < w5
    bar.update_candidates(_items(*"abcdefghij"), "a")  # 10 项(>9 只显词不显序号)
    assert bar.width() > w5


def test_close_bar_stops_polling():
    bar = _bar()
    bar.set_default_items(_items("😀"))
    bar.update_candidates(None, "")
    assert bar._poll.isActive()
    bar.close_bar()
    assert not bar._poll.isActive()
    assert not bar.isVisible()


def test_update_candidates_schedules_repaint():
    """回归:逐键 update 只改数据不重绘(条宽不变时无 resize,layered 窗
    move 不重绘),必须显式调度 update()。实例级遮蔽捕获调用。"""
    bar = _bar()
    bar.set_default_items(_items("😀"))
    bar.update_candidates(None, "")
    called: list[int] = []
    bar.update = lambda: called.append(1)  # type: ignore[method-assign]
    bar.update_candidates(_items(*"ab"), "a")  # 等宽刷新(2 格 → 2 格)
    bar.update_candidates(_items("😀"), "ab")
    assert len(called) == 2


def test_reposition_falls_back_to_cursor():
    """offscreen 无前台 caret → 回退鼠标坐标,不抛错且落屏内。"""
    bar = _bar()
    bar.set_default_items(_items("😀"))
    bar.update_candidates(None, "")
    scr = QApplication.primaryScreen().availableGeometry()
    assert scr.contains(bar.pos())
