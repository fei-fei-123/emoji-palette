"""索引完整性测试(DESIGN.md §10 M0)。

覆盖:条目数 ≥3700、必填字段齐全、码点无重复、
💩 条目含 zh/en/py/abbr 四类关键词、拼音推导正确性。
"""

import json
from pathlib import Path

import pytest

from build_data import norm_cp, pinyin_words

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "index.json"

REQUIRED_FIELDS = {
    "cp", "char", "ver", "name", "name_zh", "group", "group_zh",
    "subgroup", "kw_en", "kw_zh", "kw_py", "kw_abbr",
}


@pytest.fixture(scope="module")
def index() -> dict:
    if not INDEX.exists():
        pytest.skip("data/index.json 不存在,先运行 build_data.py 构建")
    return json.loads(INDEX.read_text(encoding="utf-8"))


def test_pinyin_derivation():
    """拼音推导直接对齐 DESIGN.md §4.2 示例:便便→bianbian/bb,屎→shi/s。"""
    pys, abbrs = pinyin_words(["便便", "屎"])
    assert "bianbian" in pys and "bb" in abbrs
    assert "shi" in pys and "s" in abbrs


def test_norm_cp():
    assert norm_cp("1F4A9") == "1F4A9"
    assert norm_cp("1f468-200d-1f4bb") == "1F468 200D 1F4BB"
    assert norm_cp("A9-20E3") == "A9 20E3"
    assert norm_cp("00A9 FE0F") == "A9 FE0F"


def test_count_ge_3700(index):
    assert len(index["emojis"]) >= 3700, f"仅 {len(index['emojis'])} 条,未达 3700"


def test_required_fields(index):
    for e in index["emojis"]:
        missing = REQUIRED_FIELDS - e.keys()
        assert not missing, f"{e.get('cp')} 缺字段: {missing}"
        assert e["char"], f"{e['cp']} char 为空"
        assert e["group_zh"], f"{e['cp']} 组名未映射: {e['group']}"


def test_no_duplicate_cp(index):
    cps = [e["cp"] for e in index["emojis"]]
    assert len(cps) == len(set(cps)), "存在重复码点"


def test_poop_four_keyword_types(index):
    """💩 必须同时具备 zh/en/py/abbr 四类词(M0 验收)。"""
    poop = next(e for e in index["emojis"] if e["cp"] == "1F4A9")
    assert poop["kw_en"], "kw_en 为空"
    assert poop["kw_zh"], "kw_zh 为空"
    assert poop["kw_py"], "kw_py 为空"
    assert poop["kw_abbr"], "kw_abbr 为空"
    assert "shit" in poop["kw_en"], "emojilib 俚语补充未生效"


def test_keyword_lengths(index):
    for e in index["emojis"]:
        if e["kw_zh"]:
            assert e["kw_py"] and e["kw_abbr"], f"{e['cp']} 有中文词但拼音缺失"
