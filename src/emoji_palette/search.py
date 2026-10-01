"""索引加载 / 四路查询 / 打分排序(DESIGN.md §6.3)。

纯内存线性扫描(~14 万词条 <30ms/键),勿提前建桶。
档位得分基数取 20000 而非 §6.3 示例的 10000:保证档位绝对主导
(FR3.2 档位 > 频率),否则 alias 权重 1.2 × 满频 9999 ≈ 11999
会反超上一档,与规格自相矛盾(决议见 DEVLOG)。
"""

import json
from pathlib import Path
from typing import Literal

TermType = Literal["en", "zh", "py", "abbr", "alias"]

# 档位:3=term == q;2=term.startswith(q);1=q in term(FR3.2)
_TIER_EXACT, _TIER_PREFIX, _TIER_SUBSTR = 3, 2, 1
_TIER_BASE = 20000
_FREQ_CAP = 9999
_ALIAS_WEIGHT = 1.2
_DEFAULT_LIMIT = 50


class SearchIndex:
    """启动时全量载入 + 预展开扁平匹配列表;frequencies 为共享引用。"""

    def __init__(self, emojis: list[dict], frequencies: dict[str, int],
                 aliases: dict[str, list[str]] | None = None) -> None:
        self._emojis = emojis
        self._freq = frequencies
        self._chars = [e["char"] for e in emojis]
        # 码点 tie-break 键:cp 为多码点空格串,必须数值元组比较
        self._cps = [tuple(int(x, 16) for x in e["cp"].split()) for e in emojis]
        self._by_char = {c: i for i, c in enumerate(self._chars)}
        # 预展开 (term, emoji_idx, weight);alias 权重 1.2,独立段便于热更新
        self._base_terms: list[tuple[str, int, float]] = []
        for i, e in enumerate(emojis):
            for key in ("kw_en", "kw_zh", "kw_py", "kw_abbr"):
                for term in e.get(key, ()):
                    term = term.strip().lower()
                    if term:
                        self._base_terms.append((term, i, 1.0))
        self._terms: list[tuple[str, int, float]] = []
        self._aliases: dict[str, list[str]] = {}
        self.set_aliases(aliases or {})

    def set_aliases(self, aliases: dict[str, list[str]]) -> None:
        """别名热更新(FR3.5「立即生效」):重建 alias 段并重挂扁平表。

        未收录字符忽略(别名只挂到索引内 emoji);小写归一与内置词一致。
        """
        self._aliases = aliases
        alias_terms: list[tuple[str, int, float]] = []
        for char, words in aliases.items():
            i = self._by_char.get(char)
            if i is None:
                continue
            for term in words:
                term = term.strip().lower()
                if term:
                    alias_terms.append((term, i, _ALIAS_WEIGHT))
        self._terms = self._base_terms + alias_terms

    @classmethod
    def load(cls, index_path: Path, frequencies: dict[str, int],
             aliases: dict[str, list[str]] | None = None) -> "SearchIndex":
        data = json.loads(Path(index_path).read_text(encoding="utf-8"))
        return cls(data["emojis"], frequencies, aliases)

    def entry_by_char(self, char: str) -> dict | None:
        """字符 → 索引条目(面板固定常用条用);未收录返回 None。"""
        i = self._by_char.get(char)
        return self._emojis[i] if i is not None else None

    def entries_for_group(self, group: str) -> list[dict]:
        """组内全部条目,保持 emoji-test 原始顺序(分类浏览用,M2)。"""
        return [e for e in self._emojis if e["group"] == group]

    def top_frequent(self, limit: int) -> list[dict]:
        """按频率降序的已用条目(常用栏数据源,M2);同频码点升序。"""
        used = [i for i, c in enumerate(self._chars) if self._freq.get(c, 0) > 0]
        used.sort(key=lambda i: (-self._freq[self._chars[i]], self._cps[i]))
        return [self._emojis[i] for i in used[:limit]]

    def expander_table(self, use_builtin: bool = True) -> dict[str, str]:
        """文本扩展匹配表(FR4.2):term(小写拉丁)→ emoji 字符。

        内置取 kw_en/kw_abbr(§6.6;kw_py 不参与 —— `::` 录制是精确全等,
        拼音子串价值低且误触多),同词先到先得(索引序 = emoji-test 序);
        别名后入覆盖内置(优先)。含空格/非拉丁词无法被 [a-z0-9] 缓冲命中,剔除。
        """
        table: dict[str, str] = {}
        if use_builtin:
            for e in self._emojis:
                for key in ("kw_en", "kw_abbr"):
                    for term in e.get(key, ()):
                        term = term.strip().lower()
                        if term.isascii() and term.isalnum():
                            table.setdefault(term, e["char"])
        for char, words in self._aliases.items():
            for term in words:
                term = term.strip().lower()
                if term.isascii() and term.isalnum():
                    table[term] = char
        return table

    def query(self, text: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
        """四路命中 + 三级排序,返回条目 dict 引用列表(只读)。"""
        q = text.strip().lower()
        if not q:
            return []
        # 每查询一次取各 emoji 的封顶频率(共享表,bump 后即时可见)
        capped = [min(self._freq.get(c, 0), _FREQ_CAP) for c in self._chars]
        # 同 emoji 多词命中只取最高分(去重,DESIGN.md 未规定、必须做)
        best: dict[int, float] = {}
        for term, idx, weight in self._terms:
            if term == q:
                tier = _TIER_EXACT
            elif term.startswith(q):
                tier = _TIER_PREFIX
            elif q in term:
                tier = _TIER_SUBSTR
            else:
                continue
            score = tier * _TIER_BASE + capped[idx] * weight
            if score > best.get(idx, -1.0):
                best[idx] = score
        ranked = sorted(best.items(), key=lambda kv: (-kv[1], self._cps[kv[0]]))
        return [self._emojis[i] for i, _ in ranked[:limit]]
