# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包(DESIGN.md §9/§10 M4):单 exe、无控制台。

datas 把 data/index.json 打进 _MEIPASS/data/(app.py 以 _MEIPASS 定位);
pathex 指向 src/ 使 emoji_palette 包可被 Analysis 静态发现。
构建:pyinstaller build.spec --noconfirm
"""

from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    ["src/emoji_palette/__main__.py"],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[(str(ROOT / "data" / "index.json"), "data")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc_data"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="EmojiPalette",
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)
