"""数据管道:下载 CLDR/emoji-test/emojilib → 解析 → 拼音 → data/index.json。

用法:
    python build_data.py            # 在线下载(优先 data/raw 缓存)
    python build_data.py --offline  # 仅用缓存构建,缺缓存即报错
    python build_data.py --refresh  # 忽略缓存强制重新下载

运行期零网络,本脚本仅构建期使用(pypinyin 仅此处依赖)。
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pypinyin import lazy_pinyin

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "index.json"

# emoji-test 版本探测顺序:新版本存在则用,否则回退
EMOJI_TEST_VERSIONS = ("17.0", "16.0")
URL_EMOJI_TEST = "https://www.unicode.org/Public/emoji/{ver}/emoji-test.txt"
URL_CLDR_ANNOT = (
    "https://raw.githubusercontent.com/unicode-org/cldr-json/main/"
    "cldr-json/cldr-annotations-full/annotations/{lang}/annotations.json"
)
# emojilib 仓库路径历史上有变动,dist/ 与根路径都试一次
URL_EMOJILIB = (
    "https://raw.githubusercontent.com/muan/emojilib/main/dist/emoji-en-US.json",
    "https://raw.githubusercontent.com/muan/emojilib/main/emoji-en-US.json",
)

TIMEOUT = 60
HEADERS = {"User-Agent": "Mozilla/5.0 (EmojiPalette build_data; +local)"}

# 数据行:`1F4A9  ; fully-qualified # 💩 E1.0 pile of poo`
RE_DATA = re.compile(
    r"^\s*([0-9A-Fa-f][0-9A-Fa-f ]*?)\s*;\s*([\w-]+)\s*#\s*(.+?)\s+E[<>]?([\d.]+)\s+(.+?)\s*$"
)
RE_GROUP = re.compile(r"^#\s*group:\s*(.+?)\s*$")
RE_SUBGROUP = re.compile(r"^#\s*subgroup:\s*(.+?)\s*$")
# CLDR default 中的冗余项,如 "(u1F4A9)"
RE_PAREN = re.compile(r"[()]")


def norm_cp(cp: str) -> str:
    """码点串归一化:大小写统一、`-` 视同空格、去掉前导零。"""
    return " ".join(t.upper().lstrip("0") or "0" for t in cp.replace("-", " ").split())


def fetch(urls: str | tuple[str, ...], cache_name: str, offline: bool, refresh: bool,
          required: bool = True) -> Path | None:
    """下载到 data/raw 缓存并返回路径;已缓存且非 --refresh 时直接复用。

    --offline 缺缓存/下载失败:required 为真时报错退出,
    否则返回 None(可选数据源降级)。
    """
    dest = RAW_DIR / cache_name
    if dest.exists() and not refresh:
        return dest
    if offline:
        if required:
            raise SystemExit(f"[offline] 缓存缺失 {cache_name},请先在线运行一次 build_data.py")
        print(f"  ⚠ [offline] 缓存缺失 {cache_name},可选源跳过")
        return None
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for url in (urls if isinstance(urls, tuple) else (urls,)):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = resp.read()
            dest.write_bytes(data)
            print(f"  ✓ {cache_name}({len(data) // 1024} KB)← {url}")
            return dest
        except Exception as e:  # noqa: BLE001 — 构建脚本,逐 URL 降级
            last_err = e
            print(f"  ✗ {url}: {e}")
    if required:
        raise SystemExit(f"下载失败 {cache_name}: {last_err}")
    print(f"  ⚠ 可选源下载失败,跳过 {cache_name}: {last_err}")
    return None


def parse_emoji_test(path: Path) -> list[dict]:
    """解析 emoji-test.txt:只收 fully-qualified,跳过 Component 组。"""
    emojis: list[dict] = []
    group = subgroup = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        m = RE_GROUP.match(line)
        if m:
            group = m.group(1)
            continue
        m = RE_SUBGROUP.match(line)
        if m:
            subgroup = m.group(1)
            continue
        m = RE_DATA.match(line)
        if not m or m.group(2) != "fully-qualified" or group == "Component":
            continue
        emojis.append({
            "cp": " ".join(t.upper() for t in m.group(1).split()),
            "char": m.group(3),
            "ver": m.group(4),
            "name": m.group(5),
            "group": group,
            "subgroup": subgroup,
        })
    return emojis


def load_annotations(path: Path) -> dict[str, dict]:
    """CLDR annotations.json → {归一化码点: {"default": [...], "tts": [...]}}。

    CLDR 的键是 emoji 字符本身(非十六进制),逐字符转码点后归一化,
    与 emoji-test 的码点序列天然对齐。
    """
    anns = json.loads(path.read_text(encoding="utf-8"))["annotations"]["annotations"]
    out: dict[str, dict] = {}
    for key, val in anns.items():
        cp_str = " ".join(f"{ord(ch):X}" for ch in key)
        defaults = [w.strip().lower() for w in val.get("default", []) if not RE_PAREN.search(w)]
        tts = [t.strip() for t in val.get("tts", []) if t.strip()]
        out[norm_cp(cp_str)] = {"default": defaults, "tts": tts}
    return out


def load_emojilib(path: Path) -> dict[str, list[str]]:
    """emojilib → {emoji 字符: [小写关键词]};兼容新旧两种文件格式。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for k, v in data.items():
        if isinstance(v, list):  # v3+:字符 → 关键词数组
            words = [w.strip().lower() for w in v if isinstance(w, str) and w.strip()]
            if words:
                out[k] = words
        elif isinstance(v, str):  # 旧版:名称 → 字符,反排
            out.setdefault(v, []).append(k.strip().lower())
    return out


def pinyin_words(zh_words: list[str]) -> tuple[list[str], list[str]]:
    """kw_zh → (整词拼音连写, 逐音节首字母缩写)。"""
    pys: list[str] = []
    abbrs: list[str] = []
    for word in zh_words:
        units = [u for u in lazy_pinyin(word) if u]
        if not units:
            continue
        full = "".join(units)
        ab = "".join(u[0] for u in units)
        if full.isascii() and full not in pys:
            pys.append(full)
        if ab.isascii() and ab not in abbrs:
            abbrs.append(ab)
    return pys, abbrs


def _dedup(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def build(offline: bool, refresh: bool) -> None:
    sys.path.insert(0, str(ROOT / "src"))  # 复用运行期包
    from emoji_palette.groups import group_zh

    print("① 获取数据源 ...")
    et_path: Path | None = None
    et_ver = ""
    if offline:
        for ver in EMOJI_TEST_VERSIONS:
            p = RAW_DIR / f"emoji-test-{ver}.txt"
            if p.exists():
                et_path, et_ver = p, ver
                break
        if et_path is None:
            raise SystemExit("[offline] 缓存中无 emoji-test.txt")
    else:
        for ver in EMOJI_TEST_VERSIONS:
            et_path = fetch(URL_EMOJI_TEST.format(ver=ver), f"emoji-test-{ver}.txt",
                            offline, refresh, required=False)
            if et_path is not None:
                et_ver = ver
                break
        if et_path is None:
            raise SystemExit("emoji-test.txt 各版本均下载失败")

    ann_en_p = fetch(URL_CLDR_ANNOT.format(lang="en"), "cldr-annotations-en.json",
                     offline, refresh)
    ann_zh_p = fetch(URL_CLDR_ANNOT.format(lang="zh"), "cldr-annotations-zh.json",
                     offline, refresh)
    lib_p = fetch(URL_EMOJILIB, "emojilib-en.json", offline, refresh, required=False)

    print("② 解析与合并 ...")
    base = parse_emoji_test(et_path)
    ann_en = load_annotations(ann_en_p)
    ann_zh = load_annotations(ann_zh_p)
    lib = load_emojilib(lib_p) if lib_p else {}

    out: list[dict] = []
    seen: set[str] = set()
    for e in base:
        key = norm_cp(e["cp"])
        if key in seen:
            continue
        seen.add(key)
        en = ann_en.get(key, {})
        zh = ann_zh.get(key, {})
        kw_en = _dedup(en.get("default", []) + lib.get(e["char"], []))
        kw_zh = _dedup(zh.get("default", []))
        kw_py, kw_abbr = pinyin_words(kw_zh)
        out.append({
            "cp": e["cp"],
            "char": e["char"],
            "ver": e["ver"],
            "name": (en.get("tts") or [e["name"]])[0],
            "name_zh": (zh.get("tts") or [""])[0],
            "group": e["group"],
            "group_zh": group_zh(e["group"]),
            "subgroup": e["subgroup"],
            "kw_en": kw_en,
            "kw_zh": kw_zh,
            "kw_py": kw_py,
            "kw_abbr": kw_abbr,
        })

    payload = {
        "version": et_ver,
        "built_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "emojis": out,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    size_kb = OUT_PATH.stat().st_size // 1024
    print(f"③ 写出 {OUT_PATH}({len(out)} 条,emoji-test {et_ver},{size_kb} KB)")


def main() -> None:
    # Windows 控制台可能为 GBK,打印 emoji 时防 UnicodeEncodeError
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Emoji Palette 数据索引构建")
    ap.add_argument("--offline", action="store_true", help="仅用 data/raw 缓存构建")
    ap.add_argument("--refresh", action="store_true", help="忽略缓存强制重新下载")
    args = ap.parse_args()
    build(args.offline, args.refresh)


if __name__ == "__main__":
    main()
