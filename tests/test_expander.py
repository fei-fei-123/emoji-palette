"""文本扩展状态机转换测试(表驱动)。

覆盖:IDLE→ARMED→REC、REC 按键规则全分支、缓冲超限、
门禁进出复位、has_candidates 回写联动、候选源、
别名热更、config 读写往返、钩子返回值语义。
"""

from pathlib import Path

import pytest

from emoji_palette import config
from emoji_palette.expander import Expander
from emoji_palette.search import SearchIndex

POO = "💩"
_T = 1000.0  # 固定时基:gate 复查节流(500ms)在测试中可控穿越


def _machine(gate=lambda: True, prefix: str = "::") -> Expander:
    return Expander(gate, prefix)


def _type(machine: Expander, keys: str) -> tuple[bool, dict | None]:
    """逐字符喂键(空格→space);返回最后一个键的 (suppress, 事件)。"""
    result = (False, None)
    for ch in keys:
        name = {" ": "space", "\r": "enter"}.get(ch, ch)
        result = machine.on_key(name, now=_T)
    return result


def _ev(kind: str, **kw) -> dict:
    base = {"event": kind, "buf": "", "n": 0, "back": 0}
    base.update(kw)
    return base


def _rec(machine: Expander, buf: str = "") -> None:
    """喂前缀进入 REC(可选预填缓冲,返回事件忽略)。"""
    for ch in machine._prefix + buf:
        machine.on_key(ch, now=_T)


# ── 状态转换:武装与事件流 ─────────────────────────────────


def test_prefix_arms_and_emits_show():
    m = _machine()
    assert m.on_key(":", now=_T) == (False, None)   # ARMED 无事件
    assert m.on_key(":", now=_T) == (False, _ev("show", buf=""))
    assert m.on_key("x", now=_T) == (False, _ev("update", buf="x"))
    assert m.on_key("y", now=_T) == (False, _ev("update", buf="xy"))


@pytest.mark.parametrize("keys,suppress,event", [
    ("::", False, {"event": "show", "buf": "", "n": 0, "back": 0}),
    (":x", False, None),                    # 单冒号后他键 → IDLE
    ("::shi!", False, {"event": "close", "buf": "", "n": 0, "back": 0}),
])
def test_arming(keys, suppress, event):
    assert _type(_machine(), keys) == (suppress, event)


# ── REC 抑制矩阵 ───────────────────────────────────────────────


def test_letters_pass_through_and_update():
    """字母放行入缓冲,逐键发 update(真实文本留在目标窗口)。"""
    m = _machine()
    _rec(m)
    for i, ch in enumerate("shit", 1):
        assert m.on_key(ch, now=_T) == (False, _ev("update", buf="shit"[:i]))


def test_digit_with_candidates_commits():
    m = _machine()
    m.set_has_candidates(True)
    _rec(m, "shi")
    assert m.on_key("3", now=_T) == (True, _ev("digit", buf="shi", n=3, back=5))
    assert m.on_key("space", now=_T) == (False, None)  # 已复位(空格归 IDLE)


def test_digit_without_candidates_buffers():
    m = _machine()
    m.set_has_candidates(False)
    _rec(m, "1")
    assert m.on_key("0", now=_T) == (False, _ev("update", buf="10"))  # 0 无格照常入缓冲
    assert m.on_key("2", now=_T) == (False, _ev("update", buf="102"))


def test_space_enter_commit_with_candidates():
    for trig in ("space", "enter"):
        m = _machine()
        m.set_has_candidates(True)
        _rec(m, "shit")
        assert m.on_key(trig, now=_T) == (
            True, _ev("commit", buf="shit", back=6))
        assert m.on_key("a", now=_T) == (False, None)  # 已复位:字母在 IDLE 不武装


def test_space_without_candidates_passes_and_closes():
    m = _machine()
    m.set_has_candidates(False)
    _rec(m, "zzz")
    assert m.on_key("space", now=_T) == (False, _ev("close"))
    assert m.on_key("a", now=_T) == (False, None)  # 已复位


def test_esc_swallow_and_close():
    m = _machine()
    m.set_has_candidates(True)
    _rec(m, "shi")
    assert m.on_key("esc", now=_T) == (True, _ev("close"))


def test_up_down_close_bar():
    for k in ("up", "down"):
        m = _machine()
        m.set_has_candidates(True)
        _rec(m, "shi")
        assert m.on_key(k, now=_T) == (True, _ev("close"))


def test_left_right_hijacked_with_candidates():
    m = _machine()
    m.set_has_candidates(True)
    _rec(m, "shi")
    assert m.on_key("left", now=_T) == (True, _ev("left", buf="shi"))
    assert m.on_key("right", now=_T) == (True, _ev("right", buf="shi"))
    assert m.on_key("space", now=_T)[0] is True  # 仍 REC:提交


def test_left_right_pass_without_candidates():
    """无候选时方向键放行关条(用户可离开;回删镜像也不允许光标左移)。"""
    m = _machine()
    m.set_has_candidates(False)
    _rec(m, "zz")
    assert m.on_key("left", now=_T) == (False, _ev("close"))
    assert m.on_key("a", now=_T) == (False, None)


def test_backspace_mirrors_app_deletion():
    m = _machine()
    _rec(m, "shi")
    assert m.on_key("backspace", now=_T) == (False, _ev("update", buf="sh"))
    assert m.on_key("backspace", now=_T) == (False, _ev("update", buf="s"))
    assert m.on_key("backspace", now=_T) == (False, _ev("update", buf=""))
    assert m.on_key("backspace", now=_T) == (False, _ev("close"))  # 退空前缀 → 复位收条


def test_modifier_and_other_keys_close():
    for k in ("tab", "f5", "caps lock"):
        m = _machine()
        _rec(m, "sh")
        assert m.on_key(k, now=_T) == (False, _ev("close")), k


def test_modifier_streams_do_not_break_state():
    """回归:`:` 需按住 Shift 输入,两个前缀键之间的 shift 事件
    (松开重按 / 系统自动重复)不得打断武装;REC 中修饰键放行且不收条。"""
    m = _machine()
    assert m.on_key(":", now=_T) == (False, None)
    assert m.on_key("shift", now=_T) == (False, None)      # 不回 IDLE
    assert m.on_key(":", now=_T) == (False, _ev("show"))   # 仍能入 REC
    m.set_has_candidates(True)
    for k in ("shift", "left ctrl", "right alt", "windows", "alt gr"):
        assert m.on_key(k, now=_T) == (False, None), k     # 条不收、不吞
    assert m.on_key("space", now=_T) == (True, _ev("commit", back=2))


def test_buffer_overflow_resets():
    m = _machine()
    _rec(m)
    for _ in range(24):
        m.on_key("a", now=_T)
    assert m.on_key("a", now=_T) == (False, _ev("close"))  # 第 25 键:超长复位
    assert m.on_key("space", now=_T) == (False, None)


def test_custom_prefix():
    m = _machine(prefix=";;")
    assert _type(m, ";;x") == (False, _ev("update", buf="x"))
    m2 = _machine(prefix=";;")
    assert _type(m2, "::x") == (False, None)  # 旧前缀不再武装


def test_set_prefix_resets():
    m = _machine()
    _rec(m, "ab")
    m.set_prefix("++")
    assert m.on_key("c", now=_T) == (False, None)  # 已复位回 IDLE


def test_machine_exception_passes_through():
    """状态机内异常默认放行,不卡键盘。"""
    def boom() -> bool:
        raise RuntimeError("gate 崩了")
    m = Expander(boom, "::")
    assert m.on_key(":", now=_T) == (False, None)
    assert m.on_key(":", now=_T) == (False, None)
    assert m.on_key("space", now=_T) == (False, None)


# ── 门禁(IME / 黑名单 / 总开关)──────────────────────────


def test_gate_blocks_arming():
    m = _machine(gate=lambda: False)
    assert _type(m, "::shi") == (False, None)


def test_gate_recheck_during_rec():
    """录制中复查(500ms 节流):门禁转关 → 丢缓冲复位,发 close 放行。"""
    states = iter([True, True, False])
    m = _machine(gate=lambda: next(states))
    assert m.on_key(":", now=_T) == (False, None)          # 武装(查门禁#1)
    assert m.on_key(":", now=_T) == (False, _ev("show"))   # 入 REC
    assert m.on_key("s", now=_T) == (False, _ev("update", buf="s"))
    assert m.on_key("h", now=_T + 0.6) == (False, _ev("update", buf="sh"))  # 复查#2 仍开
    assert m.on_key("i", now=_T + 1.2) == (False, _ev("close"))  # 复查#3:关 → 复位
    assert m.on_key("space", now=_T + 1.2) == (False, None)  # 已 IDLE,放行


def test_gate_recheck_throttled():
    """500ms 内不重复查门禁(syscall 节流)。"""
    calls: list[int] = []

    def gate() -> bool:
        calls.append(1)
        return True

    m = _machine(gate=gate)
    m.set_has_candidates(True)
    for k in "::shit":
        m.on_key(k, now=_T)
    assert m.on_key("space", now=_T + 0.02) == (True, _ev("commit", buf="shit", back=6))
    assert len(calls) == 1  # 仅武装时查询;REC 内未到复查窗口


# ── 候选数据源(search.prefix_candidates)──────────────────


def _mini_entries() -> list[dict]:
    return [
        {"char": POO, "cp": "1F4A9", "kw_en": ["shit"], "kw_abbr": ["bb"],
         "kw_py": ["shi"], "kw_zh": ["屎"]},
        {"char": "😀", "cp": "1F600", "kw_en": ["grin"], "kw_abbr": ["smile"],
         "kw_py": ["xiao"], "kw_zh": ["笑"]},
    ]


def test_prefix_candidates_pinyin_shi_hits_poo():
    """``shi``(kw_py)必须命中 💩。"""
    idx = SearchIndex(_mini_entries(), {})
    cands = idx.prefix_candidates("shi")
    chars = [e["char"] for e, _t in cands]
    assert POO in chars
    assert ("shi", ) == tuple(t for e, t in cands if e["char"] == POO)


def test_prefix_candidates_exact_short_priority():
    idx = SearchIndex(_mini_entries(), {}, {POO: ["shit2"]})
    # exact 全等词优先于更长词;同 emoji 取最优词
    cands = idx.prefix_candidates("shit")
    assert cands[0][0]["char"] == POO
    assert cands[0][1] == "shit"


def test_prefix_candidates_alias_weight_and_switch():
    idx = SearchIndex(_mini_entries(), {}, {POO: ["xx"]})
    assert [e["char"] for e, _t in idx.prefix_candidates("xx")] == [POO]
    # 关内置:仅别名段
    assert idx.prefix_candidates("shit", use_builtin=False) == []
    assert [e["char"] for e, _t in idx.prefix_candidates("xx", use_builtin=False)] == [POO]


def test_prefix_candidates_limit_and_empty():
    idx = SearchIndex(_mini_entries(), {})
    assert idx.prefix_candidates("") == []
    assert len(idx.prefix_candidates("s", limit=1)) == 1


def test_prefix_candidates_frequency_weighting():
    idx = SearchIndex(_mini_entries(), {POO: 100})
    # 同为 "s" 前缀命中(shit/shi vs smile),高频 💩 在前
    assert idx.prefix_candidates("s")[0][0]["char"] == POO


def test_set_aliases_updates_search():
    """set_aliases 后搜索立即命中新别名。"""
    idx = SearchIndex(_mini_entries(), {})
    assert idx.query("翔") == []
    idx.set_aliases({POO: ["翔", "py"]})
    assert [e["char"] for e in idx.query("翔")] == [POO]
    assert [e["char"] for e, _t in idx.prefix_candidates("py")] == [POO]


# ── 钩子适配层返回值语义(真机踩坑回归锁)────────────────────────


def test_hook_return_semantics():
    """_on_event 返回 True=放行 / False=拦截(_winkeyboard 约定,
    与直觉相反;按「True=吞」实现会吞掉所有键)。"""
    from types import SimpleNamespace

    from emoji_palette.expander import ExpandBridge, ExpanderHook

    events: list[dict] = []
    bridge = ExpandBridge()
    bridge.compose.connect(events.append)
    hook = ExpanderHook(_machine(), bridge)

    def ev(name: str, etype: str = "down"):
        return SimpleNamespace(event_type=etype, name=name)

    assert hook._on_event(ev(":")) is True        # 前缀放行
    assert hook._on_event(ev(":")) is True        # 入 REC,发 show
    for k in "shi":
        assert hook._on_event(ev(k)) is True     # 缓冲放行
    assert hook._on_event(ev("space", "up")) is True  # 抬键一律放行
    m = hook._machine
    m.set_has_candidates(True)
    assert hook._on_event(ev("space")) is False   # 有候选 → 拦截触发键
    kinds = [e["event"] for e in events]
    assert kinds == ["show", "update", "update", "update", "commit"], kinds


# ── config.aliases 读写往返 ────────────────────────────────


def test_alias_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "ALIAS_PATH", tmp_path / "aliases.json")
    assert config.load_aliases() == {}                  # 缺失 → {}
    config.save_aliases({POO: ["翔", "xx"], "😀": []})   # 空列表条目剔除
    assert config.load_aliases() == {POO: ["翔", "xx"]}


def test_alias_load_normalizes_and_filters(tmp_path: Path, monkeypatch):
    """读取时 strip 空白、剔空串;结构不符条目整条跳过。"""
    p = tmp_path / "aliases.json"
    monkeypatch.setattr(config, "ALIAS_PATH", p)
    p.write_text('[{"char": "💩", "aliases": [" 翔 ", "xx", ""]},'
                 ' {"char": 1, "aliases": "x"}, "junk", 42]',
                 encoding="utf-8")
    assert config.load_aliases() == {POO: ["翔", "xx"]}


def test_alias_malformed(tmp_path: Path, monkeypatch):
    p = tmp_path / "aliases.json"
    monkeypatch.setattr(config, "ALIAS_PATH", p)
    p.write_text("{bad json", encoding="utf-8")
    assert config.load_aliases() == {}
    p.write_text('{"dict": "not a list"}', encoding="utf-8")
    assert config.load_aliases() == {}
