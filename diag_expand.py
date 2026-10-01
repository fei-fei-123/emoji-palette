"""BUG① 诊断脚本(::shit + 空格无反应,docs/DEVTest.md)。

只读诊断 + 现场复现,不改任何用户数据。用法::

    .venv\\Scripts\\python.exe -X utf8 diag_expand.py          # 阶段 1+2:配置/候选数据源体检(无交互)
    ... diag_expand.py --gate                                 # 阶段 3:门禁现场轮询 ~4s
    ... diag_expand.py --live                                 # 阶段 4:挂真实 suppress 钩子现场复现

阶段 4 操作:启动后切到记事本,输入 ``::shit`` + 空格,观察控制台逐键输出
与记事本结果;Ctrl+C 结束(钩子在 finally/atexit 双保险卸载,不卡键盘)。
"""

import argparse
import atexit
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

try:  # 控制台代码页兼容:emoji 打不出也不许崩
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001, S110 — 旧 Python 无 reconfigure,忽略即可
    pass

from emoji_palette import config, ime
from emoji_palette.expander import ExpandBridge, Expander, ExpanderHook
from emoji_palette.search import SearchIndex

INDEX_PATH = Path(__file__).resolve().parent / "data" / "index.json"


def phase1_config() -> dict:
    """阶段 1:配置快照 —— 直接暴露 enabled/builtin 污染与黑名单。"""
    cfg = config.load_config()
    ex = cfg["expansion"]
    aliases = config.load_aliases()
    print("=" * 60)
    print("[阶段1] 配置快照(config.json / aliases.json)")
    print(f"  config 路径   : {config.CONFIG_PATH}")
    print(f"  hotkey        : {cfg['hotkey']!r}")
    print(f"  enabled       : {ex['enabled']!r}   <- False 则扩展整体停用")
    print(f"  prefix        : {ex['prefix']!r}")
    print(f"  builtin       : {ex['builtin_keywords']!r}   <- False 则表仅剩别名")
    print(f"  blacklist     : {ex['process_blacklist']!r}")
    print(f"  别名条目数    : {len(aliases)}"
          + (f"  {aliases}" if aliases else ""))
    return cfg


def phase2_table(cfg: dict) -> SearchIndex:
    """阶段 2:候选数据源体检 —— prefix_candidates 对 shit/shi 出什么。"""
    import json

    emojis = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["emojis"]
    index = SearchIndex(emojis, config.load_frequencies(), config.load_aliases())
    print("=" * 60)
    print("[阶段2] 候选数据源体检(prefix_candidates)")
    print(f"  索引条目      : {len(emojis)}")
    for q in ("shit", "shi", "sh"):
        cands = index.prefix_candidates(
            q, use_builtin=cfg["expansion"]["builtin_keywords"])
        shown = ", ".join(f"{e['char']}({t})" for e, t in cands[:3])
        print(f"  前缀 {q!r:6}  -> {len(cands)} 项: {shown or '(空)'}")
    print("  (M5 起拼音 kw_py 一并参与 —— 'shi' 应含 💩)")
    return index


def phase3_gate(cfg: dict) -> None:
    """阶段 3:门禁现场轮询 —— 暴露 IME 常开 / 前台进程进黑名单。"""
    import time

    blacklist = set(cfg["expansion"]["process_blacklist"])
    print("=" * 60)
    print("[阶段3] 门禁现场轮询(2s;切到当时出问题的窗口观察)")
    for _ in range(4):
        proc = ime.foreground_process_name()
        ime_on = ime.ime_transcribing()
        verdict = ("拦截:黑名单进程" if proc in blacklist
                   else "拦截:IME 转写(中文/全角子模式)" if ime_on else "放行")
        print(f"  前台进程={proc!r:24} IME 转写={ime_on!r:5} -> {verdict}")
        time.sleep(0.5)


def phase_ime_probe() -> None:
    """IME 模式探测:哪种 API 能区分「英文透传」与「中文转写」。

    现行门禁用 IMC_GETOPENSTATUS(方法A)——对「开着但英文透传」的中文
    输入法会误拦(::shit 也无反应的候选真因)。此处并列三个探测口,
    用户切 EN/中(通常按 Shift)观察哪个字段翻转,据此换门禁实现。
    """
    import ctypes
    import ctypes.wintypes as wt
    import time

    user32 = ctypes.windll.user32
    imm32 = ctypes.windll.imm32
    IME_CMODE_NATIVE = 0x0001  # 中文(原生)模式位
    WM_IME_CONTROL = 0x0283
    IMC_GETOPENSTATUS = 0x0005
    IMC_GETCONVERSIONMODE = 0x0001  # WinUser.h 文档值(上轮误用讹传 0x0101)

    # C 方法必须声明类型:句柄/指针按默认 int 截断会静默失败(上轮 -1 真因)
    user32.GetWindowThreadProcessId.argtypes = (wt.HWND, ctypes.POINTER(wt.DWORD))
    user32.AttachThreadInput.argtypes = (wt.DWORD, wt.DWORD, wt.BOOL)
    user32.AttachThreadInput.restype = wt.BOOL
    imm32.ImmGetContext.argtypes = (wt.HWND,)
    imm32.ImmGetContext.restype = ctypes.c_void_p
    imm32.ImmGetConversionStatus.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD))
    imm32.ImmGetConversionStatus.restype = wt.BOOL

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("flags", ctypes.c_ulong),
                    ("hwndFocus", ctypes.c_void_p), ("hwndActive", ctypes.c_void_p),
                    ("hwndCapture", ctypes.c_void_p), ("hwndMenuOwner", ctypes.c_void_p),
                    ("hwndMoveSize", ctypes.c_void_p), ("hwndCaret", ctypes.c_void_p),
                    ("rcCaret", ctypes.c_long * 4)]

    print("=" * 60)
    print("[IME 探测] 每 0.5s 采样,测试窗口保持前台,分两轮切换:")
    print("  第 1 轮:Win+Space 切「英文键盘 ↔ 中文输入法」各一次;")
    print("  第 2 轮:停在中文输入法,按 Shift 切其内部 英文↔中文 子模式各一次。")
    print("  观察第 2 轮里哪几行翻转(把输出贴回)。A=现行门禁;")
    print("  B=WM_IME_CONTROL IMC_GETCONVERSIONMODE(文档值,子模式区分的")
    print("  头号候选 —— A 同通道可用,B 若随子模式翻转则门禁可改);")
    print("  C=ImmGetConversionStatus(现代 TSF 应用拿不到上下文,预期恒 -1);")
    print("  D=布局语言位(不随子模式变)。")
    try:
        while True:
            hwnd = user32.GetForegroundWindow()
            tid = user32.GetWindowThreadProcessId(hwnd, None)
            hime = imm32.ImmGetDefaultIMEWnd(hwnd)
            a_open = user32.SendMessageW(hime, WM_IME_CONTROL,
                                         IMC_GETOPENSTATUS, 0) if hime else -1
            b_mode = user32.SendMessageW(hime, WM_IME_CONTROL,
                                         IMC_GETCONVERSIONMODE, 0) if hime else -1
            layout = user32.GetKeyboardLayout(tid) & 0xFFFF
            c_native = -1
            c_why = ""
            cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            attached = user32.AttachThreadInput(cur_tid, tid, True)
            try:
                if attached:
                    himc = imm32.ImmGetContext(hwnd)
                    if himc:
                        conv = wt.DWORD()
                        sent = wt.DWORD()
                        if imm32.ImmGetConversionStatus(himc, ctypes.byref(conv),
                                                        ctypes.byref(sent)):
                            c_native = int(conv.value) & IME_CMODE_NATIVE
                        else:
                            c_why = "conv失败"
                        imm32.ImmReleaseContext(hwnd, himc)
                    else:
                        c_why = "无上下文"
                else:
                    c_why = "attach失败"
            finally:
                if attached:
                    user32.AttachThreadInput(cur_tid, tid, False)
            print(f"  A_open={a_open!r:4} B_mode={b_mode!r:4} "
                  f"C_native={c_native!r:4}{'(' + c_why + ')' if c_native < 0 else '':10} "
                  f"D_lang={layout:#06x}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("  (IME 探测结束)")


def phase4_live(cfg: dict) -> None:
    """阶段 4:真实链路现场复现(与 app 相同的 Expander + ExpanderHook)。"""
    import keyboard

    expansion = cfg["expansion"]
    blacklist = set(expansion["process_blacklist"])

    def gate() -> bool:
        if not expansion["enabled"]:
            print("  [gate] 拦截:expansion.enabled=False")
            return False
        proc = ime.foreground_process_name()
        if proc in blacklist:
            print(f"  [gate] 拦截:黑名单进程 {proc!r}")
            return False
        if ime.ime_transcribing():
            print("  [gate] 拦截:IME 转写中(中文/全角子模式)")
            return False
        return True

    # 与 app 完全一致的新链路:Expander(gate, prefix) 无 matcher,
    # 主线程消费 compose 事件并打印(诊断不真注入,不做 UI)
    import json

    emojis = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["emojis"]
    index = SearchIndex(emojis, config.load_frequencies(), config.load_aliases())
    machine = Expander(gate, expansion["prefix"])
    _orig_on_key = machine.on_key
    _STATES = {0: "IDLE", 1: "ARMED", 2: "REC"}

    def _traced_on_key(name: str, now: float | None = None):
        """逐键打印(状态迁移 + 决策):真机「无反应」时把沉默变成证据。"""
        before = machine._state
        result = _orig_on_key(name, now)
        move = f"{_STATES[before]}->{_STATES[machine._state]}"
        shown = move if before != machine._state else _STATES[machine._state]
        print(f"  [key] {name!r:14} {shown:14} 吞={result[0]!r:5} {result[1] or ''}")
        return result

    machine.on_key = _traced_on_key  # type: ignore[method-assign]
    bridge = ExpandBridge()
    hook = ExpanderHook(machine, bridge)
    atexit.register(keyboard.unhook_all)  # M4 教训:钩子必须有兜底卸载

    def on_compose(ev: dict) -> None:
        """主线程消费(queued 信号):回写 has_candidates + 打印。"""
        buf = ev.get("buf", "")
        if ev.get("event") in ("show", "update"):
            cands = (index.prefix_candidates(
                buf, use_builtin=expansion["builtin_keywords"]) if buf else [])
            machine.set_has_candidates(bool(cands))
            shown = ", ".join(f"{e['char']}({t})" for e, t in cands[:3])
            print(f"  [条] buf={buf!r} 候选 {len(cands)}: {shown or '(无匹配)'}")
        print(f"  [compose] {ev}")

    bridge.compose.connect(on_compose)

    print("=" * 60)
    print("[阶段4] 现场复现:已挂全局 suppress 钩子(链路与 app 相同)")
    print("  1) 切到记事本  2) 输入 ::shit + 空格  3) 观察:控制台逐键打印")
    print("  ([key] 键名/状态迁移/吞键 + [条] 候选)/ 记事本是否得到 💩")
    print("  4) 本窗口 Ctrl+C 结束")
    hook.start()
    try:
        while True:
            keyboard.wait()  # 主线程挂起,钩子线程打印;Ctrl+C 触发 KeyboardInterrupt
    except KeyboardInterrupt:
        pass
    finally:
        hook.stop()
        keyboard.unhook_all()
        print("\n[阶段4] 钩子已卸载,结束。")


def main() -> int:
    ap = argparse.ArgumentParser(description=":: 扩展 BUG 诊断")
    ap.add_argument("--gate", action="store_true", help="附加阶段3 门禁轮询")
    ap.add_argument("--ime-probe", action="store_true", dest="ime_probe",
                    help="IME 模式探测(EN/中 翻转观察)")
    ap.add_argument("--live", action="store_true", help="附加阶段4 现场复现")
    args = ap.parse_args()

    cfg = phase1_config()
    phase2_table(cfg)
    if args.gate:
        phase3_gate(cfg)
    if args.ime_probe:
        phase_ime_probe()
    if args.live:
        phase4_live(cfg)
    if not (args.gate or args.ime_probe or args.live):
        print("=" * 60)
        print("提示:--gate 门禁轮询;--ime-probe IME 模式探测;"
              "--live 挂真钩子现场复现(记事本输入 ::shit ␣)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
