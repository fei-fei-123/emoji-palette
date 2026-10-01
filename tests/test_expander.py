"""文本扩展状态机转换测试(表驱动,DESIGN.md §6.6)。

覆盖:IDLE→ARMED→REC、空格命中/未命中、非法字符复位、
Esc 复位、缓冲超限复位、门禁(IME/黑名单/开关)进出复位、
别名热替换即时生效、expander_table 构表规则、config 别名读写往返。
"""

from pathlib import Path

import pytest

from emoji_palette import config
from emoji_palette.expander import Expander
from emoji_palette.search import SearchIndex

POO = "💩"
_T = 1000.0  # 固定时基:gate 复查节流(500ms)在测试中可控穿越


def _machine(table: dict[str, str], gate=lambda: True,
             prefix: str = "::") -> Expander:
    return Expander(dict(table).get, gate, prefix)


def _type(machine: Expander, keys: str) -> tuple[bool, dict | None]:
    """逐字符喂键(空格→space);返回最后一个键的 (suppress, task)。"""
    result = (False, None)
    for ch in keys:
        result = machine.on_key("space" if ch == " " else ch, now=_T)
    return result


# ── §6.6 状态转换(表驱动)──────────────────────────────────────

@pytest.mark.parametrize("keys,suppress,task", [
    # 命中:吞触发空格 + 回删「前缀+缓冲」再注入(back = 2+缓冲长)
    ("::shit ", True, {"back": 6, "text": POO}),
    ("::poop ", True, {"back": 6, "text": POO}),
    ("::xx ", True, {"back": 4, "text": POO}),          # 别名
    ("x::shit ", True, {"back": 6, "text": POO}),       # 前导他键不影响武装(全局流)
    # 未命中 / 打断:一律放行,无任务
    ("::xyz ", False, None),                            # 未命中原样放行
    ("::shit", False, None),                            # 未触发(无空格)
    (":x", False, None),                                # 单冒号后他键 → IDLE
    ("::shi!", False, None),                            # 非法字符 → IDLE 放行
])
def test_transitions(keys, suppress, task):
    m = _machine({"shit": POO, "poop": POO, "xx": POO})
    assert _type(m, keys) == (suppress, task)


def test_esc_resets_rec():
    """REC 中 Esc → 复位放行;其后的空格在 IDLE 照常放行。"""
    m = _machine({"shit": POO})
    for k in "::shi":
        assert m.on_key(k, now=_T) == (False, None)
    assert m.on_key("esc", now=_T) == (False, None)
    assert m.on_key("space", now=_T) == (False, None)


def test_prefix_and_buffer_pass_through():
    """前缀/缓冲键全部放行(真实文本要留在目标窗口),仅触发键可被吞。"""
    m = _machine({"shit": POO})
    for i, k in enumerate("::shit"):
        suppress, task = m.on_key(k, now=_T)
        assert not suppress and task is None, f"第{i}键 {k!r} 不应吞/触发"
    assert m.on_key("space", now=_T) == (True, {"back": 6, "text": POO})


def test_buffer_overflow_resets():
    """缓冲 >24 字符复位放行(§6.6)。"""
    m = _machine({"a" * 30: POO})
    for _ in range(24):
        assert m.on_key("a", now=_T) == (False, None)
    assert m.on_key("a", now=_T) == (False, None)      # 第 25 键:超长复位
    assert m.on_key("space", now=_T) == (False, None)  # 已 IDLE,放行


def test_digits_recorded():
    """缓冲含数字([a-z0-9]):`::bb2 ` 命中。"""
    assert _type(_machine({"bb2": POO}), "::bb2 ") == (True, {"back": 5, "text": POO})


def test_custom_prefix():
    m = _machine({"shit": POO}, prefix=";;")
    assert _type(m, ";;shit ") == (True, {"back": 6, "text": POO})
    assert _type(m, "::shit ") == (False, None)  # 旧前缀不再武装


def test_machine_exception_passes_through():
    """状态机内异常(此处:matcher 抛错)默认放行,不卡键盘(§12)。"""
    def boom(_s: str) -> str:
        raise RuntimeError("matcher 崩了")
    m = Expander(boom, lambda: True, "::")
    assert m.on_key(":", now=_T) == (False, None)
    assert m.on_key(":", now=_T) == (False, None)
    assert m.on_key("space", now=_T) == (False, None)


# ── 门禁(IME / 黑名单 / 总开关,§6.5)───────────────────────────


def test_gate_blocks_arming():
    """门禁关(如 IME 开):':' 不武装,后续整串放行。"""
    m = _machine({"shit": POO}, gate=lambda: False)
    assert _type(m, "::shit ") == (False, None)


def test_gate_recheck_during_rec():
    """录制中复查(500ms 节流):门禁转关 → 丢缓冲复位放行。"""
    states = iter([True, True, True, False])
    m = _machine({"shit": POO}, gate=lambda: next(states))
    assert m.on_key(":", now=_T) == (False, None)          # 武装(查门禁)
    assert m.on_key(":", now=_T) == (False, None)          # 入 REC
    assert m.on_key("s", now=_T) == (False, None)          # 缓冲
    assert m.on_key("h", now=_T + 0.6) == (False, None)    # 复查:关 → 复位
    assert m.on_key("space", now=_T + 0.6) == (False, None)  # 已 IDLE,放行


def test_gate_recheck_throttled():
    """500ms 内不重复查门禁(syscall 节流):时钟近不动时仅武装查一次。"""
    calls: list[int] = []

    def gate() -> bool:
        calls.append(1)
        return True

    m = _machine({"shit": POO}, gate=gate)
    for k in "::shit":
        m.on_key(k, now=_T)
    assert m.on_key("space", now=_T + 0.02) == (True, {"back": 6, "text": POO})
    assert len(calls) == 1  # 仅武装时查询;REC 内未到复查窗口


# ── 别名热替换与匹配表来源(search 联动)─────────────────────────


def test_set_table_hot_swap():
    """匹配表热替换即时生效(FR3.5)。"""
    m = _machine({})
    assert _type(m, "::kk ") == (False, None)
    m.set_table({"kk": POO}.get)
    assert _type(m, "::kk ") == (True, {"back": 4, "text": POO})


def _mini_entries() -> list[dict]:
    return [
        {"char": POO, "cp": "1F4A9", "kw_en": ["shit"], "kw_abbr": ["bb"],
         "kw_py": ["shi"], "kw_zh": ["屎"]},
        {"char": "😀", "cp": "1F600", "kw_en": ["grin face"], "kw_abbr": [],
         "kw_py": [], "kw_zh": []},
    ]


def test_expander_table_rules():
    """别名入表并覆盖内置;kw_py/中文/含空格词不参与(§6.6 匹配表)。"""
    idx = SearchIndex(_mini_entries(), {}, aliases={POO: ["xx"]})
    table = idx.expander_table(use_builtin=True)
    assert table["shit"] == POO and table["bb"] == POO
    assert table["xx"] == POO
    assert "shi" not in table
    assert "屎" not in table
    assert "grin face" not in table
    # 别名覆盖内置:同词时别名所指胜出
    idx2 = SearchIndex(_mini_entries(), {}, aliases={"😀": ["shit"]})
    assert idx2.expander_table(True)["shit"] == "😀"
    # 关内置:仅别名
    only_alias = idx2.expander_table(False)
    assert only_alias == {"shit": "😀"}


def test_set_aliases_updates_search():
    """set_aliases 后搜索立即命中新别名(FR3.5 搜索侧)。"""
    idx = SearchIndex(_mini_entries(), {})
    assert idx.query("翔") == []
    idx.set_aliases({POO: ["翔"]})
    assert [e["char"] for e in idx.query("翔")] == [POO]


# ── 钩子适配层返回值语义(真机踩坑回归锁)────────────────────────


def test_hook_return_semantics():
    """_on_event 返回 True=放行 / False=拦截(_winkeyboard.prepare_intercept
    约定,与直觉相反 —— M3 真机 E2E 踩坑:按「True=吞」实现会吞掉所有键)。"""
    from types import SimpleNamespace

    from emoji_palette.expander import ExpandBridge, ExpanderHook

    tasks: list[dict] = []
    bridge = ExpandBridge()
    bridge.action.connect(tasks.append)
    hook = ExpanderHook(_machine({"shit": POO}), bridge)

    def ev(name: str, etype: str = "down"):
        return SimpleNamespace(event_type=etype, name=name)

    assert hook._on_event(ev(":")) is True        # 前缀放行
    assert hook._on_event(ev(":")) is True
    for k in "shit":
        assert hook._on_event(ev(k)) is True     # 缓冲放行
    assert hook._on_event(ev("space", "up")) is True  # 抬键一律放行
    assert hook._on_event(ev("space")) is False   # 命中 → 拦截触发键
    assert tasks == [{"back": 6, "text": POO}], tasks


# ── config.aliases 读写往返(§4.3)───────────────────────────────


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
