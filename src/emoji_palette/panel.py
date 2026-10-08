"""表情面板 UI:搜索框 + 分类栏 + 网格 + 信息栏;预创建、show/hide 切换。

输入模型:默认焦点在面板自身(导航模式:←→ 横移 / ↑↓ 纵移 / +− 切类),
打字自动进搜索框(输入模式);搜索模式下数字 1-9 直选前 9 项。
"""

import time

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPalette,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from emoji_palette import config, sender
from emoji_palette.groups import GROUP_ZH
from emoji_palette.settings_ui import keyboard_to_qt

# 空查询时的固定常用条(常用栏冷启动底料)。
# 用元组而非字符串:❤️ 等含变体选择符的序列不能按码点拆开迭代
_STRIP = ("😀", "😁", "😂", "🤣", "😊", "😍", "🥰", "😘", "😜", "🤔",
          "😎", "😭", "😡", "👍", "👏", "🙏", "💪", "🎉", "❤️", "🔥",
          "✨", "💯", "💩")

# delegate 主题色:(选中块色, 回退文字色)——浅色主题回退文字须用深色
_DELEGATE_COLORS: dict[str, tuple[str, str]] = {
    "dark": ("#0a6cff", "#e8e8e8"),
    "light": ("#0a6cff", "#222222"),
}

DARK_QSS = """
#searchEdit {
    background: rgba(50, 50, 50, 215);
    border: 1px solid rgba(63, 63, 63, 220);
    border-radius: 6px;
    padding: 4px 10px;
    color: #e8e8e8;
    font-size: 14px;
}
#catList {
    background: rgba(42, 42, 42, 210);
    border-radius: 6px;
    font-size: 12px;
    color: #c8c8c8;
    outline: none;
}
#catList::item { padding: 6px 4px 6px 10px; border-radius: 6px; }
#catList::item:hover { background: rgba(56, 56, 56, 220); }
#catList::item:selected { background: #0a6cff; color: #ffffff; }
#catList:disabled { color: #565656; }
#catList:disabled::item { color: #565656; }
#infoBar {
    background: rgba(42, 42, 42, 210);
    border-radius: 6px;
}
#infoLabel {
    background: transparent;
    color: #9a9a9a;
    font-size: 12px;
}
QListWidget {
    border: none;
}
QScrollBar:vertical {
    background: transparent; width: 6px; margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(74, 74, 74, 210); border-radius: 3px; min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""

# 浅色主题(彩色 emoji 字形不受前景色影响,仅容器换肤)
LIGHT_QSS = """
#searchEdit {
    background: rgba(255, 255, 255, 230);
    border: 1px solid rgba(204, 204, 204, 230);
    border-radius: 6px;
    padding: 4px 10px;
    color: #222222;
    font-size: 14px;
}
#catList {
    background: rgba(236, 236, 236, 225);
    border-radius: 6px;
    font-size: 12px;
    color: #333333;
    outline: none;
}
#catList::item { padding: 6px 4px 6px 10px; border-radius: 6px; }
#catList::item:hover { background: rgba(224, 224, 224, 230); }
#catList::item:selected { background: #0a6cff; color: #ffffff; }
#catList:disabled { color: #9a9a9a; }
#catList:disabled::item { color: #9a9a9a; }
#infoBar {
    background: rgba(236, 236, 236, 225);
    border-radius: 6px;
}
#infoLabel {
    background: transparent;
    color: #666666;
    font-size: 12px;
}
QListWidget {
    border: none;
}
QScrollBar:vertical {
    background: transparent; width: 6px; margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(192, 192, 192, 230); border-radius: 3px; min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""

# 根容器绘制色(paintEvent 自绘):顶层 WA_TranslucentBackground 窗口
# 的 QSS 背景不绘制,且 alpha=0 区域会点击穿透 —— 必须真的画出来
_PANEL_BG: dict[str, tuple[int, int, int, int]] = {
    "dark": (30, 30, 30, 235),
    "light": (245, 245, 245, 242),
}
_PANEL_BORDER: dict[str, tuple[int, int, int, int]] = {
    "dark": (95, 95, 95, 200),
    "light": (160, 160, 160, 220),
}
_PANEL_RADIUS = 8.0
# keep-open 提交后延迟抢回前台(ms):SendInput 字符按出队时刻的前台窗口路由,
# 立即抢回会与字符路由竞态导致丢失(实测复现);需留足路由时间
_REGRAB_DELAY_MS = 120


class _EmojiDelegate(QStyledItemDelegate):
    """网格项绘制:emoji 字符居中 + 圆角选中高亮。"""

    def __init__(self, font: QFont, sel_color: QColor, fg_color: QColor,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._font = font
        self._sel = sel_color
        self._fg = fg_color

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            path = QPainterPath()
            path.addRoundedRect(QRectF(option.rect).adjusted(2, 2, -2, -2), 6, 6)
            painter.fillPath(path, self._sel)
        painter.setFont(self._font)
        painter.setPen(self._fg)
        char = index.data(Qt.ItemDataRole.DisplayRole) or ""
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, char)
        painter.restore()


class EmojiPanel(QWidget):
    """表情面板:预创建、show/hide 切换;popup 记录注入目标窗口。"""

    aliases_changed = Signal()  # 别名编辑落盘后通知(app 重建扩展匹配表)
    fallback_notice = Signal(str)  # 剪贴板降级发生(托盘气泡用)

    def __init__(self, cfg: dict, index,
                 aliases: dict[str, list[str]] | None = None) -> None:
        super().__init__()
        self.setObjectName("EmojiPanel")
        self._cfg = cfg
        self._index = index
        self._aliases = aliases if aliases is not None else {}  # 共享引用,编辑即改
        self._target_hwnd = 0
        # keep-open WM_CHAR 直投的目标焦点子窗口;popup 抓拍(见 popup)
        self._target_focus = 0
        self._popup_ts = 0.0  # 呼出时刻(monotonic),失活宽限用
        self._hold_grace = 0.0  # keep-open 提交的失活豁免截止
        self._tail: dict | None = None  # 热键末键残留过滤状态
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 默认焦点 = 面板自身(导航模式)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        # 半透明 + 圆角根背景走 paintEvent 自绘(见 _PANEL_BG 说明)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        p = cfg["panel"]
        self.setFixedSize(QSize(int(p["width"]), int(p.get("height", 440))))
        self.setStyleSheet(LIGHT_QSS if p.get("theme") == "light" else DARK_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchEdit")
        self.search_edit.setPlaceholderText("搜索 emoji(中文 / 拼音 / 缩写)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedHeight(40)
        pal = self.search_edit.palette()
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText,
                     QColor("#7a7a7a"))
        pal.setColor(QPalette.ColorGroup.Normal, QPalette.ColorRole.PlaceholderText,
                     QColor("#7a7a7a"))
        self.search_edit.setPalette(pal)
        self.search_edit.installEventFilter(self)
        root.addWidget(self.search_edit)

        # ── 主体:左分类栏 + 右网格 ────────────────────────────────
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setResizeMode(QListWidget.ResizeMode.Fixed)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setWordWrap(False)
        self.grid.setWrapping(True)
        self.grid.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # 网格自身不画底(根背景透出;QSS transparent 会把下层像素 alpha 抹零)
        self.grid.setAutoFillBackground(False)
        self.grid.viewport().setAutoFillBackground(False)
        self.grid.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._apply_grid_metrics()
        self.grid.itemClicked.connect(self._on_item_clicked)
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._on_context_menu)

        self.cat_list = QListWidget()
        self.cat_list.setObjectName("catList")
        self.cat_list.setFixedWidth(88)
        self.cat_list.setFrameShape(QFrame.Shape.NoFrame)
        self.cat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # StrongFocus:Tab 可达;点击选中后打字会被 eventFilter 转回搜索框
        self.cat_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.cat_list.installEventFilter(self)
        for key, zh in [("", "常用")] + list(GROUP_ZH.items()):
            item = QListWidgetItem(zh)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setToolTip(zh)
            self.cat_list.addItem(item)

        body = QHBoxLayout()
        body.setSpacing(8)
        body.addWidget(self.cat_list)
        body.addWidget(self.grid, 1)
        root.addLayout(body)

        # ── 底部信息栏:当前项大图 + 中文名·英文名·码点 ─────────────
        self.preview = QLabel()
        self.preview.setObjectName("previewLabel")
        preview_font = QFont("Segoe UI Emoji")
        preview_font.setPixelSize(26)
        self.preview.setFont(preview_font)
        self.preview.setFixedSize(QSize(40, 40))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label = QLabel("")
        self.info_label.setObjectName("infoLabel")
        info_bar = QWidget()
        info_bar.setObjectName("infoBar")
        info_bar.setFixedHeight(44)
        bar = QHBoxLayout(info_bar)
        bar.setContentsMargins(10, 0, 10, 0)
        bar.setSpacing(10)
        bar.addWidget(self.preview)
        bar.addWidget(self.info_label, 1)
        root.addWidget(info_bar)

        # 固定常用条底料(索引中未收录的字符跳过)
        self._default_entries = [e for ch in _STRIP
                                 if (e := self._index.entry_by_char(ch))]

        self.search_edit.textChanged.connect(self._on_query)
        # Enter 不走 returnPressed:keyPressEvent/eventFilter 内需读 Shift 修饰
        self.cat_list.currentRowChanged.connect(self._on_category_changed)
        self.grid.currentItemChanged.connect(self._on_grid_current)
        self.cat_list.setCurrentRow(0)  # 触发首次 _load_category("")

    # ── 生命周期 ────────────────────────────────────────────────

    def popup(self, target_hwnd: int, from_hotkey: bool = True) -> None:
        """呼出:光标屏幕定位 + 边缘收拢,记录注入目标窗口。"""
        self._target_hwnd = target_hwnd
        # 此刻目标仍是前台:抓拍其焦点子窗口供 keep-open 投递 WM_CHAR。
        # 面板抢到前台后目标线程焦点清 NULL,提交时再查只会得 0
        self._target_focus = sender.focus_window(target_hwnd)
        self._popup_ts = time.monotonic()
        pt = QCursor.pos()
        scr = QGuiApplication.screenAt(pt) or QGuiApplication.primaryScreen()
        geo = scr.availableGeometry()
        w, h = self.width(), self.height()
        x = min(max(pt.x() - w // 2, geo.left() + 8), geo.right() - w - 8)
        y = min(max(pt.y() + 16, geo.top() + 8), geo.bottom() - h - 8)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        # 前台锁兜底:呼出时本进程是后台进程,activateWindow 可能被系统拦下,
        # 须以 Alt 轻敲技巧对自身原生窗口强抢焦点
        sender.restore_focus(int(self.winId()))
        if from_hotkey:
            self._arm_tail_filter()
        self.search_edit.clear()
        self.setFocus()  # 导航模式(焦点在面板,非搜索框)
        if not self.search_edit.text():
            # 原本就为空时 clear() 不触发 textChanged,手动刷新常用栏
            self._load_category(self._current_group())

    def dismiss(self) -> None:
        """立即隐藏,无动画。"""
        self.hide()

    def paintEvent(self, _ev) -> None:
        """根背景自绘:半透明圆角 + 1px 描边(见 _PANEL_BG 说明)。"""
        theme = self._cfg["panel"].get("theme")
        bg = QColor(*_PANEL_BG.get(theme, _PANEL_BG["dark"]))
        border = QColor(*_PANEL_BORDER.get(theme, _PANEL_BORDER["dark"]))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                            _PANEL_RADIUS, _PANEL_RADIUS)
        painter.fillPath(path, bg)
        painter.setPen(border)
        painter.drawPath(path)

    def event(self, e: QEvent) -> bool:
        # 点外关闭唯一可靠信号是失活(跨进程点击不产生本进程鼠标事件)。
        # 300ms 宽限:热键直通前台应用时(如 VS Code 的 Alt+E 菜单),原生
        # 菜单会在呼出瞬间抢走激活,不该据此立即关面板
        if (e.type() == QEvent.Type.ActivationChange and self.isVisible()
                and QApplication.activeWindow() is None
                and time.monotonic() - self._popup_ts > 0.3
                and time.monotonic() > self._hold_grace):
            self.dismiss()
        return super().event(e)

    # ── 分类浏览与结果填充 ───────────────────────────────────────

    def _current_group(self) -> str:
        item = self.cat_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _on_category_changed(self, row: int) -> None:
        item = self.cat_list.item(row)
        if item:
            self._load_category(item.data(Qt.ItemDataRole.UserRole))

    def _load_category(self, group: str) -> None:
        entries = (self._recent_entries() if not group
                   else self._index.entries_for_group(group))
        self._fill(entries)

    def _recent_entries(self) -> list[dict]:
        """常用栏:频率 top 在前,固定常用条补足冷启动。"""
        p = self._cfg["panel"]
        recents = (self._index.top_frequent(int(p.get("recent_count", 24)))
                   if p.get("show_recent", True) else [])
        seen = {e["char"] for e in recents}
        return recents + [e for e in self._default_entries if e["char"] not in seen]

    def _on_query(self, text: str) -> None:
        if text.strip():
            self.cat_list.setEnabled(False)  # 搜索模式:分类栏淡化
            self._fill(self._index.query(text))
        else:
            self.cat_list.setEnabled(True)  # 清空 → 回分类浏览
            self._load_category(self._current_group())

    def _fill(self, entries: list[dict]) -> None:
        self.grid.clear()
        for entry in entries:
            item = QListWidgetItem(entry["char"])
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(f"{entry.get('name_zh', '')} · {entry.get('name', '')}"
                            f" · U+{entry['cp']}")
            self.grid.addItem(item)
        if entries:
            self._select_row(0)
            self.grid.scrollTo(self.grid.model().index(0, 0),
                               QAbstractItemView.ScrollHint.PositionAtTop)

    def _select_row(self, row: int) -> None:
        """current + selected 双置:NoFocus 下 current 不绘制高亮,需 selected。"""
        self.grid.setCurrentRow(row)
        item = self.grid.item(row)
        if item:
            item.setSelected(True)

    def _on_grid_current(self, current: QListWidgetItem | None,
                         _prev: QListWidgetItem | None) -> None:
        entry = current.data(Qt.ItemDataRole.UserRole) if current else None
        if entry:
            self.preview.setText(entry["char"])
            text = (f"{entry.get('name_zh', '')} · {entry.get('name', '')}"
                    f" · U+{entry['cp']}")
            words = self._aliases.get(entry["char"])
            if words:
                text += f" · 别名: {', '.join(words)}"
            self.info_label.setText(text)
        else:
            self.preview.clear()
            self.info_label.clear()

    # ── 右键别名管理 ────────────────────────────────────────────

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self.grid.itemAt(pos)
        if not item:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        char = entry["char"]
        existing = list(self._aliases.get(char, []))

        menu = QMenu(self)
        act_add = menu.addAction("添加搜索别名…")
        act_edit = menu.addAction("编辑别名…") if existing else None
        act_del = menu.addAction("移除别名") if existing else None
        menu.addSeparator()
        act_copy = menu.addAction("复制字符")
        chosen = menu.exec(self.grid.viewport().mapToGlobal(pos))
        if chosen is act_add or (act_edit is not None and chosen is act_edit):
            words = self._ask_aliases(char, existing)
            if words is not None:
                self._save_aliases(char, words)
        elif act_del is not None and chosen is act_del:
            self._save_aliases(char, [])
        elif chosen is act_copy:
            QApplication.clipboard().setText(char)

    def _ask_aliases(self, char: str, existing: list[str]) -> list[str] | None:
        """别名输入框(预填现状,逗号分隔);取消返回 None,空输入返回 []。"""
        text, ok = QInputDialog.getText(
            self, "搜索别名",
            f"设置 {char} 的别名(多个用逗号分隔,清空 = 移除):",
            ", ".join(existing))
        if not ok:
            return None
        words: list[str] = []
        for w in text.replace("，", ",").split(","):
            w = w.strip()
            if w and w not in words:
                words.append(w)
        return words

    def _save_aliases(self, char: str, words: list[str]) -> None:
        """共享表更新 + 落盘 + 索引热更 + 扩展表重建通知 + 信息栏刷新。"""
        if words:
            self._aliases[char] = words
        else:
            self._aliases.pop(char, None)
        config.save_aliases(self._aliases)
        self._index.set_aliases(self._aliases)
        self.aliases_changed.emit()
        cur = self.grid.currentItem()  # 当前项可能就是被编辑项,刷新信息栏
        if cur:
            self._on_grid_current(cur, None)

    # ── 上屏(时序:先 hide → 再还原焦点 → 再注入)──────────────

    def _keep_open_for(self, shift: bool) -> bool:
        """keep-open 判定:配置恒开,或 Shift+提交且开关允许。"""
        p = self._cfg["panel"]
        if not p.get("close_after_submit", True):
            return True
        return bool(shift and p.get("shift_enter_keeps_open", True))

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self._submit(item.data(Qt.ItemDataRole.UserRole),
                     keep_open=self._keep_open_for(False))

    def _submit_current(self, keep_open: bool = False) -> None:
        row = max(self.grid.currentRow(), 0)
        if row < self.grid.count():
            item = self.grid.item(row)
            if item:
                self._submit(item.data(Qt.ItemDataRole.UserRole),
                             keep_open=keep_open)

    def _submit(self, entry: dict, keep_open: bool = False) -> None:
        char = entry["char"]
        if keep_open:
            # 先置失活豁免再动焦点,否则 event() 会把「面板失活」
            # 误判为点外关闭,注入中途关面板
            self._hold_grace = time.monotonic() + 0.6
        else:
            self.dismiss()
        ok = False
        regrab = True  # 走了键盘注入(切前台)路径才需要抢回
        if keep_open and self._target_focus:
            # keep-open 首选 WM_CHAR 直投:面板不失焦——无前台切换、
            # 无 120ms 盲窗,连击任意速度不掉击(实测盲窗内二击漏进
            # 目标应用);投递失败回落键盘注入
            ok = sender.post_char(self._target_focus, char)
            regrab = not ok
        if not ok:
            ok = sender.type_text(self._target_hwnd, char)
        if not ok and self._cfg["advanced"].get("fallback_to_clipboard", True):
            ok = sender.clipboard_fallback(char)
            if ok:
                self.fallback_notice.emit(char)
        if ok:
            config.bump_frequency(char)
        if keep_open and regrab and self.isVisible():
            # 回落路径专用延迟抢回:SendInput 字符按出队时刻的前台窗口
            # 路由,立即抢回会与字符路由竞态导致丢失(实测 <1ms 即丢失)
            QTimer.singleShot(_REGRAB_DELAY_MS, self._reactivate_after_submit)

    def _reactivate_after_submit(self) -> None:
        """keep-open:抢回前台与焦点,选中项保持不动。"""
        if not self.isVisible():
            return
        self._hold_grace = time.monotonic() + 0.6
        sender.restore_focus(int(self.winId()))
        if self.search_edit.text():
            self.search_edit.setFocus()
            self.search_edit.setCursorPosition(len(self.search_edit.text()))
        else:
            self.setFocus()

    def _apply_grid_metrics(self) -> None:
        """网格字体/格宽/delegate 随 icon_size 与主题重建。"""
        p = self._cfg["panel"]
        font = QFont("Segoe UI Emoji")
        font.setPixelSize(int(p["icon_size"]))
        cell = int(p["icon_size"]) + 10
        self.grid.setGridSize(QSize(cell, cell))
        self.grid.setFont(font)
        sel, fg = _DELEGATE_COLORS.get(p.get("theme"), _DELEGATE_COLORS["dark"])
        self.grid.setItemDelegate(_EmojiDelegate(font, QColor(sel), QColor(fg),
                                                 self.grid))

    def apply_cfg(self) -> None:
        """设置变更热应用:尺寸、图标大小、主题。"""
        p = self._cfg["panel"]
        self.setFixedSize(QSize(int(p["width"]), int(p.get("height", 440))))
        self._apply_grid_metrics()
        self.setStyleSheet(LIGHT_QSS if p.get("theme") == "light" else DARK_QSS)

    # ── 键盘交互 ────────────────────────────────────────────────

    @property
    def _columns(self) -> int:
        """实际可见列数(按视口/格宽算;纵向导航步长)。"""
        gw = self.grid.gridSize().width() or 46
        return max(1, self.grid.viewport().width() // gw)

    def _arm_tail_filter(self) -> None:
        """记录热键末键:呼出瞬间它常仍被按住,OS 自动重复的 KeyPress
        会落进刚拿到焦点的面板变成搜索文本;丢弃其 KeyPress 直到
        观察到 KeyRelease 或超时(1s 兜底)。"""
        try:
            seq = keyboard_to_qt(self._cfg["hotkey"])
            tail = seq.split("+")[-1].strip() if seq else ""
            # PySide6 下 QKeySequence[0] 返回 QKeyCombination,须取合并键值
            key = int(QKeySequence(tail)[0].toCombined()) if tail else 0
        except (AttributeError, KeyError, ValueError):
            return
        if key > 0:
            self._tail = {"key": int(key), "deadline": time.monotonic() + 1.0}

    def _residual_key(self, ev: QEvent) -> bool:
        """吞掉与热键末键同键值的 KeyPress(含自动重复);KeyRelease 解除过滤。"""
        t = self._tail
        if not t:
            return False
        if time.monotonic() > t["deadline"]:
            self._tail = None
            return False
        if ev.key() != t["key"]:
            return False
        if ev.type() == QEvent.Type.KeyPress:
            return True
        if ev.type() == QEvent.Type.KeyRelease:
            self._tail = None
        return False

    def _switch_category(self, delta: int) -> None:
        """+/- 切分类:先清搜索文本再切换。"""
        if self.search_edit.text():
            self.search_edit.clear()  # 触发 _on_query("") → 回浏览模式重载当前类
        count = self.cat_list.count()
        row = max(0, min(count - 1, self.cat_list.currentRow() + delta))
        if row != self.cat_list.currentRow():
            self.cat_list.setCurrentRow(row)

    def _move_selection(self, delta: int) -> None:
        """选中项相对移动(clamp 到网格范围)并滚动可见。"""
        count = self.grid.count()
        if not count:
            return
        new = max(0, min(count - 1, max(self.grid.currentRow(), 0) + delta))
        self._select_row(new)
        self.grid.scrollTo(self.grid.model().index(new, 0),
                           QAbstractItemView.ScrollHint.EnsureVisible)

    def _move_to_row(self, row: int) -> None:
        """选中项绝对移动(Home/End),clamp + 滚动。"""
        count = self.grid.count()
        if not count:
            return
        self._select_row(max(0, min(count - 1, row)))
        self.grid.scrollTo(self.grid.model().index(
            self.grid.currentRow(), 0), QAbstractItemView.ScrollHint.EnsureVisible)

    def keyPressEvent(self, ev: QEvent) -> None:
        """导航模式(焦点在面板自身,默认):←→ 横移 ±1、↑↓ 纵移 ±列;
        +/= 与 -/_ 切分类;打字自动进搜索框;Enter 上屏;Esc 关闭。"""
        if self._residual_key(ev):
            return
        key = ev.key()
        if key == Qt.Key.Key_Escape:
            self.dismiss()
            return
        if key == Qt.Key.Key_Tab:
            self.search_edit.setFocus()
            return
        if key in (Qt.Key.Key_Equal, Qt.Key.Key_Plus):
            self._switch_category(1)
            return
        if key == Qt.Key.Key_Minus:
            self._switch_category(-1)
            return
        if (self.search_edit.text() and Qt.Key.Key_1 <= key <= Qt.Key.Key_9):
            item = self.grid.item(key - Qt.Key.Key_1)
            if item:
                self._submit(item.data(Qt.ItemDataRole.UserRole),
                             keep_open=self._keep_open_for(False))
                return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._submit_current(
                keep_open=self._keep_open_for(
                    bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)))
            return
        cols = self._columns
        if key == Qt.Key.Key_Home:
            self._move_to_row(0)
            return
        if key == Qt.Key.Key_End:
            self._move_to_row(self.grid.count() - 1)
            return
        delta = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1,
                 Qt.Key.Key_Up: -cols, Qt.Key.Key_Down: cols,
                 Qt.Key.Key_PageUp: -3 * cols,
                 Qt.Key.Key_PageDown: 3 * cols}.get(key)
        if delta is not None:
            self._move_selection(delta)
            return
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and self.search_edit.text():
            # 框内有文本时退格仍作用于文本
            self.search_edit.setFocus()
            QApplication.sendEvent(self.search_edit, ev)
            return
        text = ev.text()
        if text and text.isprintable():
            # 打字自动进框:原事件转发(光标/输入法语义保留)
            self.search_edit.setFocus()
            QApplication.sendEvent(self.search_edit, ev)
            return
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev: QEvent) -> None:
        # 只为观察热键末键的 KeyRelease 以解除残留过滤
        self._residual_key(ev)
        super().keyReleaseEvent(ev)

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if ev.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return super().eventFilter(obj, ev)
        if self._residual_key(ev):  # 末键残留(Press 吞 / Release 解除)
            return True
        if ev.type() == QEvent.Type.KeyRelease:
            return super().eventFilter(obj, ev)
        key = ev.key()

        if obj is self.search_edit:
            if key == Qt.Key.Key_Escape:  # Esc 即走
                self.dismiss()
                return True
            if key == Qt.Key.Key_Tab:  # Tab:框↔面板互换
                self.setFocus()
                return True
            if key in (Qt.Key.Key_Equal, Qt.Key.Key_Plus):
                self._switch_category(1)
                return True
            if key == Qt.Key.Key_Minus:
                self._switch_category(-1)
                return True
            # 搜索模式下数字 1-9 直选前 9 项(浏览模式下数字照常入框搜索)
            if (self.search_edit.text() and Qt.Key.Key_1 <= key <= Qt.Key.Key_9):
                item = self.grid.item(key - Qt.Key.Key_1)
                if item:
                    self._submit(item.data(Qt.ItemDataRole.UserRole),
                                 keep_open=self._keep_open_for(False))
                    return True
            cols = self._columns
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                # ↑↓:离开搜索框回面板导航(此后 ←→ 变横移),并纵向移动一行
                self.setFocus()
                self._move_selection(-cols if key == Qt.Key.Key_Up else cols)
                return True
            if (key in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                        Qt.Key.Key_Home, Qt.Key.Key_End) and self.grid.count()):
                if key == Qt.Key.Key_Home:
                    self._move_to_row(0)
                elif key == Qt.Key.Key_End:
                    self._move_to_row(self.grid.count() - 1)
                else:
                    self._move_selection(-3 * cols if key == Qt.Key.Key_PageUp
                                         else 3 * cols)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._submit_current(
                    keep_open=self._keep_open_for(
                        bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)))
                return True
            # 其余(含 ←→ 文本光标)交 QLineEdit 默认
        elif obj is self.cat_list:
            if key == Qt.Key.Key_Escape:
                self.dismiss()
                return True
            if key == Qt.Key.Key_Tab:  # Tab → 搜索框
                self.search_edit.setFocus()
                return True
            if key in (Qt.Key.Key_Equal, Qt.Key.Key_Plus):
                self._switch_category(1)
                return True
            if key == Qt.Key.Key_Minus:
                self._switch_category(-1)
                return True
            text = ev.text()
            if text and text.isprintable():  # 打字从分类栏跳回搜索
                self.search_edit.setFocus()
                self.search_edit.setText(text)
                return True
        return super().eventFilter(obj, ev)
