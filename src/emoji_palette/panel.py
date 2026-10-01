"""表情面板 UI(DESIGN.md §5)。

M2 形态:搜索框 + 左侧分类栏(常用 + 9 组)+ 网格 + 底部信息栏。
搜索框有文字 = 搜索模式(分类栏淡化,§5 允许隐藏或淡化);
清空 = 回分类浏览;Tab 在搜索/分类间切换;搜索模式下数字 1-9 直选
前 9 项(高频加速 —— 直选与「数字是搜索文本」的消歧:仅搜索模式占用)。
常用栏 = 频率 top(recent_count)+ 固定常用条补足,每次呼出刷新。
M3 增:右键菜单管理别名(FR3.5,即时生效)、信息栏显示已配别名。
预创建、仅 show/hide 切换(FR1.3);emoji 字体显式 Segoe UI Emoji(坑 #5)。
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
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
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

# 空查询时的固定常用条(常用栏冷启动底料,频率 top 排其前);
# 用元组而非字符串:❤️ 等含变体选择符的序列不能按码点拆开迭代
_STRIP = ("😀", "😁", "😂", "🤣", "😊", "😍", "🥰", "😘", "😜", "🤔",
          "😎", "😭", "😡", "👍", "👏", "🙏", "💪", "🎉", "❤️", "🔥",
          "✨", "💯", "💩")

DARK_QSS = """
#EmojiPanel {
    background: #1e1e1e;
    border: 1px solid #3f3f3f;
    border-radius: 8px;
}
#searchEdit {
    background: #2a2a2a;
    border: 1px solid #3f3f3f;
    border-radius: 6px;
    padding: 4px 10px;
    color: #e8e8e8;
    font-size: 14px;
}
#catList {
    background: #242424;
    border-radius: 6px;
    font-size: 12px;
    color: #c8c8c8;
    outline: none;
}
#catList::item { padding: 6px 4px 6px 10px; border-radius: 6px; }
#catList::item:hover { background: #2f2f2f; }
#catList::item:selected { background: #0a6cff; color: #ffffff; }
#catList:disabled { color: #565656; }
#catList:disabled::item { color: #565656; }
#infoBar {
    background: #242424;
    border-radius: 6px;
}
#infoLabel {
    background: transparent;
    color: #9a9a9a;
    font-size: 12px;
}
QListWidget {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent; width: 6px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #4a4a4a; border-radius: 3px; min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""

# 浅色主题(FR5.2 外观设置;彩色 emoji 字形不受前景色影响,仅容器换肤)
LIGHT_QSS = """
#EmojiPanel {
    background: #f5f5f5;
    border: 1px solid #d0d0d0;
    border-radius: 8px;
}
#searchEdit {
    background: #ffffff;
    border: 1px solid #cccccc;
    border-radius: 6px;
    padding: 4px 10px;
    color: #222222;
    font-size: 14px;
}
#catList {
    background: #ececec;
    border-radius: 6px;
    font-size: 12px;
    color: #333333;
    outline: none;
}
#catList::item { padding: 6px 4px 6px 10px; border-radius: 6px; }
#catList::item:hover { background: #e0e0e0; }
#catList::item:selected { background: #0a6cff; color: #ffffff; }
#catList:disabled { color: #9a9a9a; }
#catList:disabled::item { color: #9a9a9a; }
#infoBar {
    background: #ececec;
    border-radius: 6px;
}
#infoLabel {
    background: transparent;
    color: #666666;
    font-size: 12px;
}
QListWidget {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent; width: 6px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #c0c0c0; border-radius: 3px; min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


class _EmojiDelegate(QStyledItemDelegate):
    """网格项绘制:emoji 字符居中 + 圆角选中高亮(不用默认文本渲染)。"""

    def __init__(self, font: QFont, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._font = font

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            path = QPainterPath()
            path.addRoundedRect(QRectF(option.rect).adjusted(2, 2, -2, -2), 6, 6)
            painter.fillPath(path, QColor("#0a6cff"))
        painter.setFont(self._font)
        painter.setPen(QColor("#e8e8e8"))
        char = index.data(Qt.ItemDataRole.DisplayRole) or ""
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, char)
        painter.restore()


class EmojiPanel(QWidget):
    """表情面板:预创建、show/hide 切换;popup 记录注入目标窗口。"""

    aliases_changed = Signal()  # 别名编辑落盘后通知(app 重建扩展匹配表)
    fallback_notice = Signal(str)  # 剪贴板降级发生(托盘气泡一次,FR6.4)

    def __init__(self, cfg: dict, index,
                 aliases: dict[str, list[str]] | None = None) -> None:
        super().__init__()
        self.setObjectName("EmojiPanel")
        self._cfg = cfg
        self._index = index
        self._aliases = aliases if aliases is not None else {}  # 共享引用,编辑即改
        self._target_hwnd = 0
        self._popup_ts = 0.0  # 呼出时刻(monotonic),失活宽限用

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        p = cfg["panel"]
        self.setFixedSize(QSize(int(p["width"]), int(p.get("height", 440))))
        self.setStyleSheet(LIGHT_QSS if p.get("theme") == "light" else DARK_QSS)

        font = QFont("Segoe UI Emoji")
        font.setPixelSize(int(p["icon_size"]))

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
        self.grid.setGridSize(QSize(46, 46))
        self.grid.setWordWrap(False)
        self.grid.setWrapping(True)
        self.grid.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.grid.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.grid.setFont(font)
        self.grid.setItemDelegate(_EmojiDelegate(font, self.grid))
        self.grid.itemClicked.connect(self._on_item_clicked)
        # 右键菜单:别名管理 + 复制(FR3.5)
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

        # ── 底部信息栏:当前项大图 + 中文名·英文名·码点(§5)───────
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

        # 固定常用条底料(索引中未收录的字符跳过;豆腐隐藏在 app 层已过滤)
        self._default_entries = [e for ch in _STRIP
                                 if (e := self._index.entry_by_char(ch))]

        self.search_edit.textChanged.connect(self._on_query)
        self.search_edit.returnPressed.connect(self._submit_current)
        self.cat_list.currentRowChanged.connect(self._on_category_changed)
        self.grid.currentItemChanged.connect(self._on_grid_current)
        self.cat_list.setCurrentRow(0)  # 触发首次 _load_category("")

    # ── 生命周期(§6.2 定位 + FR1.4 关闭)─────────────────────────

    def popup(self, target_hwnd: int) -> None:
        """呼出:光标屏幕定位 + 边缘收拢,记录注入目标窗口。"""
        self._target_hwnd = target_hwnd
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
        # 前台锁兜底(坑 #2):呼出时本进程是后台进程,Qt activateWindow 的
        # SetForegroundWindow 会被系统拦下(面板可见却拿不到 OS 焦点,
        # 按键仍进原前台窗口),须以 Alt 轻敲技巧对自身原生窗口强抢焦点
        sender.restore_focus(int(self.winId()))
        self.search_edit.clear()
        self.search_edit.setFocus()
        if not self.search_edit.text():
            # 原本就为空时 clear() 不触发 textChanged,手动刷新常用栏(频率可能已变)
            self._load_category(self._current_group())

    def dismiss(self) -> None:
        """立即隐藏,无动画(FR1.4)。"""
        self.hide()

    def event(self, e: QEvent) -> bool:
        # 跨进程点击不产生本进程鼠标事件,点外关闭唯一可靠信号是失活(§ 决议 7)。
        # 300ms 宽限:suppress=False 下热键直通前台应用(如 VS Code 的 Alt+E 菜单),
        # 原生菜单会在呼出瞬间抢走激活,不该据此立即关面板(坑 #11 副作用)
        if (e.type() == QEvent.Type.ActivationChange and self.isVisible()
                and QApplication.activeWindow() is None
                and time.monotonic() - self._popup_ts > 0.3):
            self.dismiss()
        return super().event(e)

    # ── 分类浏览与结果填充(搜索 / 分类双模式)────────────────────

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
        """常用栏:频率 top(recent_count)在前,固定常用条补足冷启动。"""
        p = self._cfg["panel"]
        recents = (self._index.top_frequent(int(p.get("recent_count", 24)))
                   if p.get("show_recent", True) else [])
        seen = {e["char"] for e in recents}
        return recents + [e for e in self._default_entries if e["char"] not in seen]

    def _on_query(self, text: str) -> None:
        if text.strip():
            # 搜索模式:结果网格 + 分类栏淡化(§5)
            self.cat_list.setEnabled(False)
            self._fill(self._index.query(text))
        else:
            # 清空 → 回分类浏览
            self.cat_list.setEnabled(True)
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
            if words:  # §5:信息栏显示已配置别名(M3)
                text += f" · 别名: {', '.join(words)}"
            self.info_label.setText(text)
        else:
            self.preview.clear()
            self.info_label.clear()

    # ── 右键别名管理(FR3.5:添加 / 编辑 / 移除,保存即生效)────────

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
        """别名输入框(预填现状,逗号分隔,兼作查看);取消 None,空输入 []。"""
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

    # ── 上屏(坑 #9 时序:先 hide → 再还原焦点 → 再注入)──────────

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self._submit(item.data(Qt.ItemDataRole.UserRole))

    def _submit_current(self) -> None:
        row = max(self.grid.currentRow(), 0)
        if row < self.grid.count():
            item = self.grid.item(row)
            if item:
                self._submit(item.data(Qt.ItemDataRole.UserRole))

    def _submit(self, entry: dict) -> None:
        char = entry["char"]
        self.dismiss()
        ok = sender.type_text(self._target_hwnd, char)
        if not ok and self._cfg["advanced"].get("fallback_to_clipboard", True):
            ok = sender.clipboard_fallback(char)
            if ok:
                self.fallback_notice.emit(char)  # FR6.4:降级提示(托盘侧节流)
        if ok:
            config.bump_frequency(char)

    def apply_cfg(self) -> None:
        """设置变更热应用(M4/FR5.2):尺寸、图标大小、主题。

        网格字体/格宽随 icon_size 重设;delegate 持字体引用需重建。
        """
        p = self._cfg["panel"]
        self.setFixedSize(QSize(int(p["width"]), int(p.get("height", 440))))
        font = QFont("Segoe UI Emoji")
        font.setPixelSize(int(p["icon_size"]))
        cell = int(p["icon_size"]) + 10
        self.grid.setGridSize(QSize(cell, cell))
        self.grid.setFont(font)
        self.grid.setItemDelegate(_EmojiDelegate(font, self.grid))
        self.setStyleSheet(LIGHT_QSS if p.get("theme") == "light" else DARK_QSS)

    # ── 键盘交互(搜索框/分类栏 eventFilter 统一处理)─────────────

    @property
    def _columns(self) -> int:
        """实际可见列数(按视口/格宽算;PgUp/PgDn 翻行步长)。"""
        gw = self.grid.gridSize().width() or 46
        return max(1, self.grid.viewport().width() // gw)

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if ev.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, ev)
        key = ev.key()

        if obj is self.search_edit:
            if key == Qt.Key.Key_Escape:  # Esc 即走(FR1.4)
                self.dismiss()
                return True
            if key == Qt.Key.Key_Tab:  # Tab → 分类浏览(清空即回浏览模式)
                self.search_edit.clear()
                self.cat_list.setFocus()
                return True
            # 搜索模式下数字 1-9 直选前 9 项(§5;浏览模式下数字照常入框搜索)
            if (self.search_edit.text() and Qt.Key.Key_1 <= key <= Qt.Key.Key_9):
                row = key - Qt.Key.Key_1
                item = self.grid.item(row)
                if item:
                    self._submit(item.data(Qt.ItemDataRole.UserRole))
                    return True
            count = self.grid.count()
            if count and key in (Qt.Key.Key_Up, Qt.Key.Key_Down,
                                 Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                                 Qt.Key.Key_Home, Qt.Key.Key_End):
                cur = max(self.grid.currentRow(), 0)
                # ↑↓ 逐项移动(结果少时比整行跳更顺手);PgUp/PgDn 整行
                if key == Qt.Key.Key_Up:
                    new = cur - 1
                elif key == Qt.Key.Key_Down:
                    new = cur + 1
                elif key == Qt.Key.Key_PageUp:
                    new = cur - self._columns
                elif key == Qt.Key.Key_PageDown:
                    new = cur + self._columns
                elif key == Qt.Key.Key_Home:
                    new = 0
                else:
                    new = count - 1
                new = max(0, min(count - 1, new))
                self._select_row(new)
                self.grid.scrollTo(self.grid.model().index(new, 0),
                                   QAbstractItemView.ScrollHint.EnsureVisible)
                return True
        elif obj is self.cat_list:
            if key == Qt.Key.Key_Escape:
                self.dismiss()
                return True
            if key == Qt.Key.Key_Tab:  # Tab → 搜索框
                self.search_edit.setFocus()
                return True
            text = ev.text()
            if text and text.isprintable():  # 打字从分类栏跳回搜索
                self.search_edit.setFocus()
                self.search_edit.setText(text)
                return True
        return super().eventFilter(obj, ev)
