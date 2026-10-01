"""QApplication 装配、单实例锁、托盘(DESIGN.md §3/§9,FR5.1)。

M4 装配链:单实例 → 配置 → 索引(+别名)→ 面板 → 热键桥 → 文本扩展
→ 托盘 + 设置窗 + 钩子看护。退出 = 托盘「退出」或终端 Ctrl+C。
单实例:命名互斥体 —— DESIGN §9 原定 QLocalServer.listen 失败检测,
但 PySide6 6.11 Windows 下 listen 不再互斥(同进程双 listen 实测均成功),
改为 Local 命名空间互斥体,进程退出系统自动回收。
"""

import ctypes
import ctypes.wintypes as wt
import gc
import json
import signal
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication, QIcon, QPainter, QPixmap, QRawFont
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from emoji_palette import config, ime, sender
from emoji_palette.candidate import CandidateBar
from emoji_palette.expander import ExpandBridge, Expander, ExpanderHook
from emoji_palette.hotkey import HookWatchdog, HotkeyBridge, HotkeyManager
from emoji_palette.panel import EmojiPanel
from emoji_palette.search import SearchIndex
from emoji_palette.settings_ui import SettingsDialog

APP_NAME = "EmojiPalette"
# PyInstaller onefile 解包目录 _MEIPASS;开发态 = 仓库根(§9 目录结构)
_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
INDEX_PATH = _BASE / "data" / "index.json"

ERROR_ALREADY_EXISTS = 183
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wt.BOOL, wt.LPCWSTR)
_kernel32.CreateMutexW.restype = wt.HANDLE


def _unsupported_filter():
    """按本机 Segoe UI Emoji 实际字形覆盖过滤(坑 #12)。

    QRawFont.glyphIndexesForString 返回 [0](.notdef)即该字体无此码点 →
    必然渲染豆腐块。比按 ver 字段猜版本精确(逐机实测);
    offscreen 平台下 QRawFont 会崩,非 windows 平台不过滤。
    返回 None 表示无法检测(字体缺失等),宁可显示豆腐也不误删。
    """

    if QGuiApplication.platformName() != "windows":
        return None
    try:
        raw = QRawFont.fromFont(QFont("Segoe UI Emoji"))
        if not raw.familyName().startswith("Segoe UI Emoji"):
            return None
    except Exception:  # noqa: BLE001 — 检测失败即放弃过滤
        return None
    cache: dict[int, bool] = {}

    def supported(entry: dict) -> bool:
        cp0 = int(entry["cp"].split()[0], 16)
        if cp0 not in cache:
            cache[cp0] = raw.glyphIndexesForString(chr(cp0)) != [0]
        return cache[cp0]

    return supported


def _acquire_single_instance() -> int:
    """取单实例互斥体;已被占返回 0,取到返回句柄(进程存活期间持有)。"""
    handle = _kernel32.CreateMutexW(None, False, f"Local\\{APP_NAME}")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return 0
    return handle or 0


def _make_tray_icon() -> QIcon:
    """程序化生成托盘图标:透明底 + 😀(免资源文件依赖)。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    font = QFont("Segoe UI Emoji")
    font.setPixelSize(52)
    painter.setFont(font)
    painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "😀")
    painter.end()
    return QIcon(pm)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(_make_tray_icon())

    # 单实例锁(仅提示,不激活既有实例;互斥体存于局部变量活到 exec 结束)
    mutex = _acquire_single_instance()
    if not mutex:
        QMessageBox.information(None, APP_NAME, "Emoji Palette 已在运行。")
        return 0

    cfg = config.load_config()
    if cfg["autostart"] != config.is_autostart():
        config.set_autostart(cfg["autostart"])  # json 意图 → 注册表(§8 默认 true)

    if not INDEX_PATH.exists():
        QMessageBox.critical(
            None, APP_NAME,
            "缺少数据索引 data/index.json。\n请先运行:python build_data.py")
        return 2

    freq = config.load_frequencies()
    aliases = config.load_aliases()
    emojis = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["emojis"]
    if cfg["advanced"].get("hide_unsupported", True):
        supported = _unsupported_filter()
        if supported:
            kept = [e for e in emojis if supported(e)]
            print(f"[app] 已隐藏 {len(emojis) - len(kept)} 个本机字体不支持的 emoji",
                  file=sys.stderr)
            emojis = kept
    index = SearchIndex(emojis, freq, aliases)
    panel = EmojiPanel(cfg, index, aliases)

    bridge = HotkeyBridge()
    manager = HotkeyManager(bridge)

    def toggle(hwnd: int) -> None:
        if panel.isVisible():
            panel.dismiss()  # 再按一次热键 = 收起
        else:
            panel.popup(hwnd)

    bridge.activated.connect(toggle)
    manager.start(cfg["hotkey"])

    # ── 文本扩展(M5/§6.6)::: 前缀录制 → 候选条;匹配在主线程 ──
    expansion = cfg["expansion"]
    blacklist = set(expansion["process_blacklist"])

    def gate() -> bool:
        """扩展活跃门禁:总开关 ∧ 面板不可见 ∧ 非黑名单进程 ∧ IME 关闭。

        面板可见时按键属于面板搜索框,必须让路(扩展全局 suppress 钩子
        会吞掉面板内的空格);IME 开启时按键归输入法(FR4.3 硬性要求)。
        """
        if not expansion["enabled"] or panel.isVisible():
            return False
        if ime.foreground_process_name() in blacklist:
            return False
        return not ime.ime_transcribing()

    machine = Expander(gate, expansion["prefix"])
    bar = CandidateBar(cfg)

    def _bar_defaults() -> list[tuple[dict, str]]:
        """空缓冲默认候选:常用 top 优先,不足以面板固定常用条补足。"""
        p = cfg["panel"]
        recents = (index.top_frequent(9) if p.get("show_recent", True) else [])
        seen = {e["char"] for e in recents}
        extra = [e for e in panel._default_entries if e["char"] not in seen]
        return [(e, "常用") for e in (recents + extra)[:9]]

    def _commit_candidate(entry: dict, back: int) -> None:
        """候选条提交(键盘/点选共用):收条 → 回删注入;失败剪贴板降级。"""
        bar.close_bar()
        hwnd = sender.get_foreground_window()
        ok = bool(hwnd) and sender.type_text(hwnd, entry["char"], backspaces=back)
        if not ok and cfg["advanced"].get("fallback_to_clipboard", True):
            ok = sender.clipboard_fallback(entry["char"])
            if ok:
                on_fallback(entry["char"])  # 托盘气泡(修 M3 起扩展路径无降级的不对称)
        if ok:
            config.bump_frequency(entry["char"])

    def on_compose(ev: dict) -> None:
        """compose 事件(主线程):show/update 刷新条;left/right 移动;
        digit/commit 提交;close 收条。条内有无候选回写状态机(吞键依据)。"""
        kind = ev.get("event")
        buf = ev.get("buf", "")
        if kind in ("show", "update"):
            if kind == "show":
                bar.set_default_items(_bar_defaults())
            items = (index.prefix_candidates(
                buf, use_builtin=expansion["builtin_keywords"]) if buf else None)
            bar.update_candidates(items, buf)
            machine.set_has_candidates(bool(bar.selected()))
        elif kind == "left":
            bar.move_selection(-1)
        elif kind == "right":
            bar.move_selection(1)
        elif kind == "close":
            bar.close_bar()
        elif kind in ("digit", "commit"):
            item = (bar.item_at_index(int(ev.get("n", 0)) - 1)
                    if kind == "digit" else bar.selected())
            if item:
                _commit_candidate(item[0], int(ev.get("back", 0)))
            else:
                bar.close_bar()  # 数字越界:安静收条(键已吞)

    expand_bridge = ExpandBridge()
    expand_hook = ExpanderHook(machine, expand_bridge)
    expand_bridge.compose.connect(on_compose)
    bar.committed.connect(
        lambda ev: _commit_candidate(ev["entry"],
                                      len(expansion["prefix"]) + len(ev["buf"])))
    if expansion["enabled"]:
        expand_hook.start()

    # ── 运行态再应用(设置保存 / 看护重挂共用)────────────────────
    def reapply_runtime() -> None:
        manager.rebind(cfg["hotkey"])
        machine.set_prefix(expansion["prefix"])
        blacklist.clear()
        blacklist.update(expansion["process_blacklist"])
        if expansion["enabled"]:
            expand_hook.start()
        else:
            expand_hook.stop()
        panel.apply_cfg()

    # ── 托盘(FR5.1)──────────────────────────────────────────────
    tray = QSystemTrayIcon(_make_tray_icon(), app)
    tray.setToolTip("Emoji Palette(热键呼出 / :: 扩展)")
    menu = QMenu()
    act_show = menu.addAction("显示面板")
    menu.addSeparator()
    act_hotkey = menu.addAction("暂停全局热键")
    act_hotkey.setCheckable(True)
    act_expand = menu.addAction("暂停文本扩展")
    act_expand.setCheckable(True)
    act_settings = menu.addAction("设置…")
    act_autostart = menu.addAction("开机自启")
    act_autostart.setCheckable(True)
    act_autostart.setChecked(config.is_autostart())
    menu.addSeparator()
    act_quit = menu.addAction("退出")
    tray.setContextMenu(menu)
    tray.show()

    def show_panel() -> None:
        panel.popup(sender.get_foreground_window(), from_hotkey=False)

    def toggle_hotkey(checked: bool) -> None:
        if checked:
            manager.stop()
        else:
            manager.start(cfg["hotkey"])

    def toggle_expand(checked: bool) -> None:
        expansion["enabled"] = not checked
        config.save_config(cfg)
        if checked:
            expand_hook.stop()
        else:
            expand_hook.start()

    def toggle_autostart(checked: bool) -> None:
        cfg["autostart"] = checked
        config.save_config(cfg)
        if not config.set_autostart(checked):
            act_autostart.setChecked(not checked)  # 写注册表失败回滚视觉态

    def open_settings() -> None:
        dialog = SettingsDialog(cfg, index, aliases, parent=None)
        dialog.applied.connect(reapply_runtime)
        dialog.exec()

    act_show.triggered.connect(show_panel)
    act_hotkey.toggled.connect(toggle_hotkey)
    act_expand.toggled.connect(toggle_expand)
    act_autostart.toggled.connect(toggle_autostart)
    act_settings.triggered.connect(open_settings)
    act_quit.triggered.connect(app.quit)

    # FR6.4:剪贴板降级托盘气泡,每会话至多一次(不反复打扰)
    bubble_state = {"last": 0.0}

    def on_fallback(char: str) -> None:
        now = time.monotonic()
        if now - bubble_state["last"] < 3600:
            return
        bubble_state["last"] = now
        tray.showMessage(APP_NAME, f"上屏失败,已复制 {char} 到剪贴板(Ctrl+V 粘贴)")

    panel.fallback_notice.connect(on_fallback)

    # ── 钩子看护(§6.7,偏差见 hotkey.py docstring)───────────────
    def rehook_all() -> None:
        reapply_runtime()

    watchdog = HookWatchdog(rehook_all, app)
    watchdog.rehooked.connect(lambda: tray.showMessage(APP_NAME, "键盘钩子失活已自动恢复"))
    watchdog.start()

    # Ctrl+C 退出:Windows 下 Qt exec() 阻塞 Python 信号检查,
    # 必须以周期性空转 QTimer 强制回到解释器,否则 SIGINT 永远不触发
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    keepalive = QTimer(app)
    keepalive.setInterval(100)
    keepalive.timeout.connect(lambda: None)
    keepalive.start()

    gc.freeze()  # §6.7:启动完成,冻结当前对象集,减少全代回收停顿

    def cleanup() -> None:
        watchdog.stop()
        expand_hook.stop()  # suppress 钩子必须先卸,任何残留都卡键盘
        manager.stop()
        import keyboard
        keyboard.unhook_all()
        config.flush_frequencies()

    app.aboutToQuit.connect(cleanup)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
