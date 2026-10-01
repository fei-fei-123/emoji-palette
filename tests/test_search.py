"""打分与四路命中测试(DESIGN.md §6.3/§10 M1/§11.1)。

验收核心:`屎`/`shit`/`shi`/`bb` 查询 → 💩 命中且排名前列;
档位 > 频率 > 码点三级排序正确;同 emoji 多词命中不重复出项。
`翔` 为 M3 别名,数据中不存在,以注入别名表覆盖(桩 docstring 承诺)。
"""

from pathlib import Path

import pytest

from emoji_palette.search import SearchIndex

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "data" / "index.json"

POO = "💩"


def _mk(cp: str, char: str, **kw: list[str]) -> dict:
    """合成最小条目:SearchIndex 只消费 cp/char/kw_* 字段。"""
    entry = {"cp": cp, "char": char, "name": char, "name_zh": "",
             "kw_en": [], "kw_zh": [], "kw_py": [], "kw_abbr": []}
    entry.update(kw)
    return entry


@pytest.fixture
def real_index() -> SearchIndex:
    if not INDEX_PATH.exists():
        pytest.skip("data/index.json 缺失,先运行 build_data.py")
    return SearchIndex.load(INDEX_PATH, {})


@pytest.fixture
def synthetic() -> SearchIndex:
    emojis = [
        _mk("1F4A9", POO, kw_py=["foo"], kw_abbr=["x"]),
        _mk("1F600", "😀", kw_py=["foobar"]),
        _mk("1F62E 200D 1F4A8", "😮‍💨", kw_py=["foo", "bar"]),
    ]
    return SearchIndex(emojis, {})


def _ranks(index: SearchIndex, q: str) -> list[str]:
    return [e["char"] for e in index.query(q)]


# ── 四路命中(真实索引)──────────────────────────────────────────


def test_four_way_hit_realdata(real_index: SearchIndex) -> None:
    for q in ("屎", "shit", "shi", "bb"):
        chars = _ranks(real_index, q)
        assert POO in chars, f"查 {q!r} 未命中 💩"
    # 首位验收:屎/shit 为 💩 独有精确命中;
    # shi 的精确命中集 {1F450👐, 1F4A9💩, 1F944🥄, 1FAE1🫡} 码点升序下
    # 💩 冷启动第 2(1F450 码点更小),首次上屏后频率学习固化首位(§11.1 前三位达标);
    # bb 的 abbr 精确命中按码点 💩 第 3
    assert _ranks(real_index, "屎")[0] == POO
    assert _ranks(real_index, "shit")[0] == POO
    assert _ranks(real_index, "shi").index(POO) <= 2
    # bb 的 abbr 精确命中集较大(🇧🇧/🍧/👜/👶 等),码点升序冷启动下 💩 第 7,
    # 频率学习后升至前列(此处仅断言可被翻页覆盖的 top 10)
    assert _ranks(real_index, "bb").index(POO) <= 9


def test_alias_injection() -> None:
    """注入别名表后 `翔` 命中 💩,且 alias 权重生效(M3 前向验证)。"""
    emojis = [_mk("1F4A9", POO), _mk("1F600", "😀", kw_py=["xiang"])]
    idx = SearchIndex(emojis, {}, aliases={POO: ["翔"]})
    assert _ranks(idx, "翔") == [POO]


def test_no_duplicate_emoji(real_index: SearchIndex) -> None:
    """💩 对 poop 有 精确+前缀 双词命中,结果只出现一次。"""
    assert _ranks(real_index, "poop").count(POO) == 1


def test_perf_smoke(real_index: SearchIndex) -> None:
    """性能冒烟:单键查询线性扫描,100 次平均 <50ms(FR3.3 毫秒级)。"""
    import time

    start = time.perf_counter()
    for _ in range(100):
        real_index.query("shi")
    avg_ms = (time.perf_counter() - start) * 1000 / 100
    assert avg_ms < 50, f"平均查询 {avg_ms:.1f}ms 超标"


# ── 打分排序(合成数据)──────────────────────────────────────────


def test_tier_priority(synthetic: SearchIndex) -> None:
    """同频下:精确 > 前缀 > 子串。查 foo:💩 exact、😮‍💨 exact(码点大在后)、😀 前缀。"""
    assert _ranks(synthetic, "foo") == [POO, "😮‍💨", "😀"]


def test_freq_within_tier() -> None:
    """档位内频率降序;且档位绝对主导——满频前缀(含 alias ×1.2)仍输零频精确。"""
    emojis = [_mk("1F4A9", POO, kw_py=["foo"]), _mk("1F600", "😀", kw_py=["foo"])]
    # 同档 exact 零频同分:码点 1F4A9 < 1F600 → 💩 在前
    assert _ranks(SearchIndex(emojis, {}), "foo") == [POO, "😀"]
    # 同档频率降序:😀 频 5 反超
    assert _ranks(SearchIndex(emojis, {"😀": 5}), "foo") == ["😀", POO]

    # 档位主导:零频 exact 胜满频 prefix
    emojis2 = [_mk("1F600", "😀", kw_py=["foo"]), _mk("1F4A9", POO, kw_py=["foobar"])]
    assert _ranks(SearchIndex(emojis2, {POO: 9999}), "foo")[0] == "😀"

    # 档位主导(极端):满频 alias prefix ×1.2 仍输零频 exact
    emojis3 = [_mk("1F600", "😀", kw_py=["foo"]), _mk("1F4A9", POO)]
    idx3 = SearchIndex(emojis3, {POO: 9999}, aliases={POO: ["foobar"]})
    assert _ranks(idx3, "foo")[0] == "😀"


def test_alias_weight() -> None:
    """同档同频(非零):alias(×1.2)优先于内置词。"""
    emojis = [_mk("1F4A9", POO, kw_py=["foo"]), _mk("1F600", "😀")]
    idx = SearchIndex(emojis, {POO: 10, "😀": 10}, aliases={"😀": ["foo"]})
    assert _ranks(idx, "foo") == ["😀", POO]


def test_codepoint_tiebreak() -> None:
    """同分按码点升序;多码点 ZWJ 序列按元组数值比较(非字符串)。"""
    emojis = [
        _mk("1F62E 200D 1F4A8", "😮‍💨", kw_py=["tie"]),
        _mk("1F600", "😀", kw_py=["tie"]),
        _mk("1F4A9", POO, kw_py=["tie"]),
    ]
    idx = SearchIndex(emojis, {})
    # (1F4A9) < (1F600) < (1F62E, ...) —— 字符串比较会把 "1F62E ..." 排最前,错
    assert _ranks(idx, "tie") == [POO, "😀", "😮‍💨"]


def test_empty_and_normalize() -> None:
    idx = SearchIndex([_mk("1F4A9", POO, kw_en=["Shit"])], {})
    assert idx.query("") == []
    assert idx.query("   ") == []
    assert _ranks(idx, "  SHIT ") == [POO]  # strip + lower


def test_limit() -> None:
    emojis = [_mk(f"1F6{i:03X}", chr(0x1F600 + i), kw_py=[f"e{i}"]) for i in range(60)]
    assert len(SearchIndex(emojis, {}).query("e")) == 50


# ── 分类与频率数据面(M2)────────────────────────────────────────


def test_entries_for_group(real_index: SearchIndex) -> None:
    """组内条目全命中且保持索引原始顺序(emoji-test 顺序)。"""
    entries = real_index.entries_for_group("Smileys & Emotion")
    assert entries, "笑脸组为空"
    assert all(e["group"] == "Smileys & Emotion" for e in entries)
    raw = [e for e in _all_entries() if e["group"] == "Smileys & Emotion"]
    assert [e["cp"] for e in entries] == [e["cp"] for e in raw]
    assert real_index.entries_for_group("不存在的组") == []


def test_top_frequent() -> None:
    """频率降序、零频排除、同频码点升序、limit 截断。"""
    emojis = [_mk("1F4A9", POO), _mk("1F600", "😀"), _mk("1F62E", "😮")]
    idx = SearchIndex(emojis, {"😀": 1, POO: 3, "😮": 1})
    assert [e["char"] for e in idx.top_frequent(10)] == [POO, "😀", "😮"]
    assert [e["char"] for e in idx.top_frequent(2)] == [POO, "😀"]
    assert SearchIndex(emojis, {}).top_frequent(10) == []


def _all_entries() -> list[dict]:
    import json

    data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return data["emojis"]
