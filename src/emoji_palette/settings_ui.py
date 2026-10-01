"""设置窗 + 别名管理表格(DESIGN.md FR5.2)。

热键录制用 QKeySequenceEdit(Qt 原生,无全局拦截),保存时转
keyboard 库语法;别名表格 QTableWidget 两列(emoji / 逗号分隔别名)。
保存 = 就地改共享 cfg/aliases → 落盘 → 发 applied 信号,由 app 负责
热改绑 / 扩展重建 / 面板热应用(设置窗不自作主张碰运行态)。
"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from emoji_palette import config

# Qt 修饰键名 → keyboard 库语法
_KB_MODS = {"ctrl": "ctrl", "alt": "alt", "shift": "shift", "meta": "windows"}


def qt_to_keyboard_hotkey(seq: QKeySequence) -> str:
    """QKeySequenceEdit 内容 → keyboard 库 hotkey 串(如 ctrl+alt+e)。

    只取第一个组合;无修饰的裸字符键不允许(会吞掉正常打字),返回 ""。
    """
    parts = [p.strip().lower() for p in seq.toString().split("+") if p.strip()]
    if not parts:
        return ""
    mods = [_KB_MODS.get(p) for p in parts[:-1]]
    if not mods or any(m is None for m in mods):
        return ""  # 未知修饰键
    key = parts[-1]
    if key in _KB_MODS or len(key) > 3:  # 末位必须是键名(F1..F24 ≤3 字符)
        return ""
    return "+".join([*filter(None, mods), key])


def keyboard_to_qt(hotkey: str) -> str:
    """keyboard 库串 → QKeySequenceEdit 可显示串(ctrl+alt+e → Ctrl+Alt+E)。"""
    parts = [p.strip() for p in hotkey.split("+") if p.strip()]
    if not parts:
        return ""
    out = []
    for p in parts:
        p = {"windows": "Meta"}.get(p.lower(), p)
        out.append(p if len(p) > 1 else p.upper())
    return "+".join(out)


class SettingsDialog(QDialog):
    """设置窗:热键 / 扩展 / 别名 / 外观 / 自启(FR5.2)。"""

    applied = Signal()  # 保存成功后发射(app 执行运行态变更)

    def __init__(self, cfg: dict, index, aliases: dict[str, list[str]],
                 parent=None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._index = index
        self._aliases = aliases
        self.setWindowTitle("Emoji Palette 设置")
        self.setModal(True)
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ── 全局热键(热键可改 = M4 验收)─────────────────────────
        g_hot = QGroupBox("全局热键")
        f_hot = QFormLayout(g_hot)
        self.hotkey_edit = QKeySequenceEdit(
            QKeySequence(keyboard_to_qt(cfg["hotkey"])))
        f_hot.addRow("呼出热键:", self.hotkey_edit)
        f_hot.addRow(QLabel("需含 Ctrl/Alt/Shift/Win 修饰键;保存后即时生效"))

        # ── 文本扩展(§6.6)──────────────────────────────────────
        g_exp = QGroupBox("文本扩展")
        f_exp = QFormLayout(g_exp)
        ex = cfg["expansion"]
        self.exp_enabled = QCheckBox("启用(:: 前缀 → emoji)")
        self.exp_enabled.setChecked(bool(ex["enabled"]))
        self.exp_builtin = QCheckBox("内置英文词参与匹配(kw_en/kw_abbr)")
        self.exp_builtin.setChecked(bool(ex["builtin_keywords"]))
        self.exp_prefix = QLineEdit(str(ex["prefix"]))
        self.exp_prefix.setMaxLength(4)
        self.exp_blacklist = QPlainTextEdit()
        self.exp_blacklist.setPlainText("\n".join(ex["process_blacklist"]))
        self.exp_blacklist.setFixedHeight(72)
        f_exp.addRow(self.exp_enabled)
        f_exp.addRow("触发前缀:", self.exp_prefix)
        f_exp.addRow(self.exp_builtin)
        f_exp.addRow("进程黑名单(每行一个 .exe):", self.exp_blacklist)

        # ── 外观(FR5.2)─────────────────────────────────────────
        g_ui = QGroupBox("外观")
        f_ui = QFormLayout(g_ui)
        p = cfg["panel"]
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["深色", "浅色"])
        self.theme_combo.setCurrentIndex(1 if p.get("theme") == "light" else 0)
        self.icon_spin = QSpinBox()
        self.icon_spin.setRange(24, 48)
        self.icon_spin.setValue(int(p["icon_size"]))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(360, 1000)
        self.width_spin.setSingleStep(20)
        self.width_spin.setValue(int(p["width"]))
        f_ui.addRow("主题:", self.theme_combo)
        f_ui.addRow("图标尺寸(px):", self.icon_spin)
        f_ui.addRow("面板宽度(px):", self.width_spin)

        # ── 开机自启(§6.8)──────────────────────────────────────
        g_auto = QGroupBox("系统")
        f_auto = QFormLayout(g_auto)
        self.autostart_check = QCheckBox("开机自动启动(注册表 HKCU Run)")
        self.autostart_check.setChecked(config.is_autostart())
        f_auto.addRow(self.autostart_check)

        # ── 别名管理表格(FR5.2/FR3.5)───────────────────────────
        g_alias = QGroupBox("搜索别名(第二列逗号分隔;emoji 列直接粘贴字符)")
        v_alias = QVBoxLayout(g_alias)
        self.alias_table = QTableWidget(0, 2)
        self.alias_table.setHorizontalHeaderLabels(["emoji", "别名"])
        self.alias_table.horizontalHeader().setStretchLastSection(True)
        for char, words in aliases.items():
            self._append_row(char, ", ".join(words))
        v_alias.addWidget(self.alias_table)
        btns = QHBoxLayout()
        btn_add = QPushButton("加行")
        btn_del = QPushButton("删选中行")
        btns.addWidget(btn_add)
        btns.addWidget(btn_del)
        btns.addStretch(1)
        v_alias.addLayout(btns)
        btn_add.clicked.connect(lambda: self._append_row("", ""))
        btn_del.clicked.connect(self._remove_selected)

        # ── 保存/取消 ────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        for w in (g_hot, g_exp, g_ui, g_auto, g_alias):
            root.addWidget(w)
        root.addWidget(buttons)

    def _append_row(self, char: str, words: str) -> None:
        r = self.alias_table.rowCount()
        self.alias_table.insertRow(r)
        self.alias_table.setItem(r, 0, QTableWidgetItem(char))
        self.alias_table.setItem(r, 1, QTableWidgetItem(words))

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.alias_table.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self.alias_table.removeRow(r)

    def _on_save(self) -> None:
        hotkey = qt_to_keyboard_hotkey(self.hotkey_edit.keySequence())
        if not hotkey:
            self.hotkey_edit.setStyleSheet("border: 1px solid #e05555;")
            return  # 热键非法不保存(提示样式),其余字段待用户修正后一并存
        self.hotkey_edit.setStyleSheet("")

        self._cfg["hotkey"] = hotkey
        ex = self._cfg["expansion"]
        ex["enabled"] = self.exp_enabled.isChecked()
        ex["builtin_keywords"] = self.exp_builtin.isChecked()
        prefix = self.exp_prefix.text().strip()
        ex["prefix"] = prefix if prefix else "::"
        ex["process_blacklist"] = [
            ln.strip() for ln in self.exp_blacklist.toPlainText().splitlines()
            if ln.strip()]
        p = self._cfg["panel"]
        p["theme"] = "light" if self.theme_combo.currentIndex() == 1 else "dark"
        p["icon_size"] = self.icon_spin.value()
        p["width"] = self.width_spin.value()
        self._cfg["autostart"] = self.autostart_check.isChecked()

        # 别名表 → 共享 dict(就地清空重填,保持引用)
        self._aliases.clear()
        for r in range(self.alias_table.rowCount()):
            char_item = self.alias_table.item(r, 0)
            words_item = self.alias_table.item(r, 1)
            char = (char_item.text().strip() if char_item else "")
            words = [w.strip() for w in (words_item.text() if words_item else "")
                     .replace("，", ",").split(",") if w.strip()]
            if char and words:
                self._aliases[char] = words

        config.save_config(self._cfg)
        config.set_autostart(self.autostart_check.isChecked())
        config.save_aliases(self._aliases)
        self._index.set_aliases(self._aliases)
        self.applied.emit()
        self.accept()
