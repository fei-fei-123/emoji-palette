"""配置 / 别名 / 频率读写,自启动注册表(DESIGN.md §4.3/§6.8/§8)。

目录:%APPDATA%\\EmojiPalette\\。config.json / frequency.json / aliases.json
全部「变更即写」(FR5.4;与 §4.3 的批量落盘矛盾,决议见 DEVLOG)。
自启动:HKCU Run 注册表值(§6.8),打包后 = exe 本体,
开发态 = python -c 引导(sys.path 注入 src,Run 键无法设环境变量)。
"""

import json
import os
import sys
import winreg
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "EmojiPalette"
CONFIG_PATH = DATA_DIR / "config.json"
FREQ_PATH = DATA_DIR / "frequency.json"
ALIAS_PATH = DATA_DIR / "aliases.json"

# DESIGN.md §8 完整默认值;任何字段缺失/类型不符时代码内兜底,不抛错
# M2 偏差:width 480→600/新增 height(§5 布局加分类栏+信息栏后 10 列需 ~600);
# 新增 advanced.hide_unsupported(坑 #12 豆腐块按 QRawFont 字形检测隐藏)
DEFAULT_CONFIG: dict[str, Any] = {
    "hotkey": "alt+e",
    "panel": {
        "width": 600,
        "height": 440,
        "columns": 10,
        "icon_size": 36,
        "theme": "dark",
        "position": "cursor",
        "show_recent": True,
        "recent_count": 24,
    },
    "expansion": {
        "enabled": True,
        "prefix": "::",
        "trigger_key": "space",
        "builtin_keywords": True,
        "process_blacklist": ["game.exe", "mstsc.exe"],
    },
    "autostart": True,
    "advanced": {
        "hook_watchdog": True,
        "fallback_to_clipboard": True,
        "hide_unsupported": True,
    },
}

# 模块级共享频率表:SearchIndex 持同一引用,bump 后查询即时可见
_frequencies: dict[str, int] = {}


def _atomic_write(path: Path, text: str) -> None:
    """临时文件 + os.replace 原子写;失败仅 stderr 警告(不抛错)。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        print(f"[config] 写入失败 {path}: {e}", file=sys.stderr)


def _merge(defaults: dict[str, Any], loaded: Any) -> dict[str, Any]:
    """深合并:文件值逐键校验类型,不符用默认;多余的键保留(前向兼容)。"""
    if not isinstance(loaded, dict):
        return json.loads(json.dumps(defaults))  # 深拷贝
    out: dict[str, Any] = dict(loaded)
    for key, default in defaults.items():
        value = loaded.get(key)
        if isinstance(default, dict):
            out[key] = _merge(default, value)
        elif isinstance(default, bool):
            out[key] = value if isinstance(value, bool) else default
        elif isinstance(default, int):
            out[key] = value if isinstance(value, int) and not isinstance(value, bool) else default
        elif isinstance(default, list):
            out[key] = value if isinstance(value, list) else default
        elif isinstance(default, str):
            out[key] = value if isinstance(value, str) else default
    return out


def load_config() -> dict[str, Any]:
    """读取 config.json;缺失/损坏 → 返回默认值并落盘首启文件。"""
    raw: Any = None
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as e:
        print(f"[config] 读取失败,使用默认值:{e}", file=sys.stderr)
    if raw is None:
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        save_config(cfg)
        return cfg
    return _merge(DEFAULT_CONFIG, raw)


def save_config(cfg: dict[str, Any]) -> None:
    _atomic_write(CONFIG_PATH, json.dumps(cfg, ensure_ascii=False, indent=2))


def load_frequencies() -> dict[str, int]:
    """读取 frequency.json(缺失/损坏 → {});返回模块级共享 dict。"""
    try:
        raw = json.loads(FREQ_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        raw = {}
    _frequencies.clear()
    if isinstance(raw, dict):
        _frequencies.update(
            {k: v for k, v in raw.items()
             if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)}
        )
    return _frequencies


def _save_frequencies() -> None:
    _atomic_write(FREQ_PATH, json.dumps(_frequencies, ensure_ascii=False))


def bump_frequency(char: str) -> int:
    """使用频率 +1 并立即落盘(FR5.4);返回新值。"""
    _frequencies[char] = _frequencies.get(char, 0) + 1
    _save_frequencies()
    return _frequencies[char]


def flush_frequencies() -> None:
    """退出安全网:bump 已即写,此处幂等重写一次。"""
    _save_frequencies()


def load_aliases() -> dict[str, list[str]]:
    """读 aliases.json(§4.3 list[{char, aliases}] → dict[char, list])。

    缺失/损坏/结构不符 → {}(宁可没有别名也不抛错);条目过滤空串。
    """
    try:
        raw = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    out: dict[str, list[str]] = {}
    if isinstance(raw, list):
        for item in raw:
            if (isinstance(item, dict) and isinstance(item.get("char"), str)
                    and isinstance(item.get("aliases"), list)):
                words = [w.strip() for w in item["aliases"]
                         if isinstance(w, str) and w.strip()]
                if words:
                    out[item["char"]] = words
    return out


def save_aliases(aliases: dict[str, list[str]]) -> None:
    """别名全量落盘(改动即写,量小无需增量);空列表条目剔除。"""
    data = [{"char": c, "aliases": w} for c, w in aliases.items() if w]
    _atomic_write(ALIAS_PATH, json.dumps(data, ensure_ascii=False, indent=2))


# ── 开机自启(HKCU Run,§6.8/FR5.3)─────────────────────────────

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "EmojiPalette"


def autostart_command() -> str:
    """自启动命令行:打包态 = exe 本体;开发态 = python -c 引导带 src 路径。

    Run 键只是命令行、无环境变量,`python -m` 找不到包 —— 用 -c 内嵌
    sys.path.insert。UTF-8 模式(-X utf8)对齐开发运行环境。
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    src = Path(__file__).resolve().parents[1]
    return (f'"{sys.executable}" -X utf8 -c '
            f'"import sys; sys.path.insert(0, r\'{src}\'); '
            f'from emoji_palette.app import main; main()"')


def set_autostart(enabled: bool) -> bool:
    """写/删自启动注册表值;失败仅 stderr 警告并返回 False(不抛错)。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY,
                            0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, AUTOSTART_NAME, 0, winreg.REG_SZ,
                                  autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass  # 本就未开,幂等
        return True
    except OSError as e:
        print(f"[config] 自启动注册表操作失败:{e}", file=sys.stderr)
        return False


def is_autostart() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY,
                            0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, AUTOSTART_NAME)
            return True
    except OSError:
        return False
