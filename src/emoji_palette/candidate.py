"""``::`` 候选条:输入法形态的叠加横条(不抢焦点,跟随光标)。

非激活窗口(WA_ShowWithoutActivating)+ paintEvent 自绘背景
(半透明窗 alpha=0 区域会点击穿透,QSS 背景不绘制)。
定位:前台 caret 下方,无 caret 回退鼠标位置,屏幕边缘收拢。
点击外部关闭:非激活窗口收不到跨进程点击,以 20ms 轮询左键状态实现。
"""

import ctypes
import ctypes.wintypes as wt

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
)
from PySide6.QtWidgets import QWidget

from emoji_palette import sender

user32 = ctypes.windll.user32

VK_LBUTTON = 0x01

_CELL_W = 56
_ROW_H = 64
_EMOJI_PX = 26
_TERM_PX = 11
_PAD = 6

_BAR_BG = {"dark": (30, 30, 30, 235), "light": (245, 245, 245, 242)}
_BAR_BORDER = {"dark": (95, 95, 95, 200), "light": (160, 160, 160, 220)}
_BAR_SEL = {"dark": (10, 108, 255, 255), "light": (10, 108, 255, 255)}
_BAR_FG = {"dark": (232, 232, 232, 255), "light": (34, 34, 34, 255)}
_BAR_FG_DIM = {"dark": (150, 150, 150, 255), "light": (120, 120, 120, 255)}
_BAR_RADIUS = 6.0


# GetGUIThreadInfo / GetAsyncKeyState 复用 sender 的声明与结构体
# (user32 进程级共享,自设 argtypes 曾排斥 sender 调用 + caret 错位)。
# 仅声明本模块独有的 ClientToScreen。
user32.ClientToScreen.argtypes = (wt.HWND, ctypes.POINTER(wt.POINT))
user32.ClientToScreen.restype = wt.BOOL


class CandidateBar(QWidget):
    """候选条:状态由主线程 compose 事件驱动,只负责显示与点选。"""

    fallback_notice = Signal(str)  # 剪贴板降级发生(托盘气泡用)
    committed = Signal(dict)  # 点选提交 {"entry", "buf"}

    def __init__(self, cfg: dict) -> None:
        super().__init__()
        self._cfg = cfg
        self._items: list[tuple[dict, str]] = []  # (entry, 匹配词)
        self._sel = 0
        self._buf = ""  # 当前组合缓冲(点选提交时算回删数用)
        self._no_match = False
        self._default_items: list[tuple[dict, str]] = []  # 空缓冲常用(app 维护)
        self._btn_down = False  # 轮询边沿记忆

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        # 绝不抢焦点(用户正在目标应用打字)+ 半透明圆角自绘背景
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._poll = QTimer(self)
        self._poll.setInterval(20)  # 点击外部检测周期
        self._poll.timeout.connect(self._check_click_outside)

    # ── 状态驱动(app.on_compose 调用)──────────────────────────

    def set_default_items(self, items: list[tuple[dict, str]]) -> None:
        self._default_items = items

    def update_candidates(self, items: list[tuple[dict, str]] | None,
                          buf: str = "") -> None:
        """刷新条内容并重定位。items=None 且 buf 空 → 默认常用;
        空 items 且 buf 非空 → 「无匹配」灰暗态(条不关)。"""
        self._buf = buf
        if not buf:
            items = self._default_items
        self._items = items or []
        self._no_match = not self._items
        self._sel = 0 if not self._no_match else -1
        self._relayout()
        self._reposition()
        if not self.isVisible():
            self.show()
            self.raise_()
            self._btn_down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            self._poll.start()
        # 自绘内容变更必须显式调度重绘:条宽不变时 setFixedSize 同值不触发
        # resize,layered 窗 move() 也不重绘 —— 数据换了画面会停在旧候选
        self.update()

    def close_bar(self) -> None:
        self._poll.stop()
        self.hide()

    def move_selection(self, delta: int) -> None:
        if not self._items:
            return
        self._sel = (self._sel + delta) % len(self._items)
        self.update()

    def selected(self) -> tuple[dict, str] | None:
        if 0 <= self._sel < len(self._items):
            return self._items[self._sel]
        return None

    def item_at_index(self, i: int) -> tuple[dict, str] | None:
        return self._items[i] if 0 <= i < len(self._items) else None

    # ── 布局 / 绘制 ────────────────────────────────────────────

    def _relayout(self) -> None:
        n = max(len(self._items), 1)
        self.setFixedSize(QSize(n * _CELL_W + 2 * _PAD, _ROW_H))

    def _themed(self, table: dict) -> tuple:
        theme = self._cfg["panel"].get("theme")
        return table.get(theme, table["dark"])

    def paintEvent(self, _ev) -> None:
        """根背景自绘 + 每格 emoji/匹配词/序号;无匹配态整体灰暗。"""
        bg = QColor(*self._themed(_BAR_BG))
        border = QColor(*self._themed(_BAR_BORDER))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                            _BAR_RADIUS, _BAR_RADIUS)
        painter.fillPath(path, bg)
        painter.setPen(border)
        painter.drawPath(path)

        if self._no_match:  # 无匹配:条不关,灰暗提示
            painter.setPen(QColor(*self._themed(_BAR_FG_DIM)))
            hint = QFont()
            hint.setPixelSize(_TERM_PX + 1)
            painter.setFont(hint)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "无匹配")
            return

        fg = QColor(*self._themed(_BAR_FG))
        emoji_font = QFont("Segoe UI Emoji")
        emoji_font.setPixelSize(_EMOJI_PX)
        term_font = QFont()
        term_font.setPixelSize(_TERM_PX)
        emoji_top = _PAD + 2
        emoji_rect_h = _EMOJI_PX + 8
        term_top = _PAD + emoji_rect_h
        for i, (entry, term) in enumerate(self._items):
            x = _PAD + i * _CELL_W
            if i == self._sel:  # 选中格描边高亮
                sel = QPainterPath()
                sel.addRoundedRect(QRectF(x + 1, _PAD + 1,
                                          _CELL_W - 2, _ROW_H - 2 * _PAD - 2), 4, 4)
                painter.fillPath(sel, QColor(*self._themed(_BAR_SEL)))
            painter.setFont(emoji_font)
            painter.setPen(fg)
            painter.drawText(QRect(x, emoji_top, _CELL_W, emoji_rect_h),
                             Qt.AlignmentFlag.AlignCenter, entry["char"])
            painter.setFont(term_font)
            label = f"{i + 1} {term}" if i < 9 else term
            painter.drawText(QRect(x, term_top, _CELL_W, _TERM_PX + 6),
                             Qt.AlignmentFlag.AlignCenter, label)

    # ── 定位(光标跟随)────────────────────────────────────────

    def _caret_screen_pos(self) -> QPoint | None:
        """前台窗口 caret 屏幕坐标;无 caret → None。"""
        info = sender.GUITHREADINFO()
        info.cbSize = ctypes.sizeof(sender.GUITHREADINFO)
        if not user32.GetGUIThreadInfo(0, ctypes.byref(info)):
            return None
        if not info.hwndCaret:
            return None
        pt = wt.POINT(info.rcCaret.left, info.rcCaret.bottom)
        if not user32.ClientToScreen(info.hwndCaret, ctypes.byref(pt)):
            return None
        return QPoint(pt.x, pt.y)

    def _reposition(self) -> None:
        pos = self._caret_screen_pos() or QCursor.pos()
        scr = (QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen())
        geo = scr.availableGeometry()
        x = min(max(pos.x() - _CELL_W // 2, geo.left() + 4),
                geo.right() - self.width() - 4)
        y = pos.y() + 20
        if y + self.height() > geo.bottom() - 4:  # 底部放不下 → 翻到光标上方
            y = max(pos.y() - 20 - self.height(), geo.top() + 4)
        self.move(x, y)

    # ── 点击外部关闭(轮询)+ 条内点选 ──────────────────────────

    def _check_click_outside(self) -> None:
        pressed = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        edge = pressed and not self._btn_down  # 上升沿
        self._btn_down = pressed
        if not edge:
            return
        bar = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
        if QCursor.pos() not in bar:
            self.close_bar()  # 点外即关(组合文本保留原样,不打扰)

    def mousePressEvent(self, ev) -> None:
        if not self._items:
            return
        i = (ev.position().x() - _PAD) // _CELL_W
        item = self.item_at_index(int(i))
        if item:
            self.committed.emit({"entry": item[0], "buf": self._buf})
