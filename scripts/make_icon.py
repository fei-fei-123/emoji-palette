"""生成 assets/icon.ico:原生平台渲染 😀(Segoe UI Emoji)多尺寸拼 ICO。

用法:python scripts/make_icon.py(幂等,随时重跑)
ICO 采用 PNG 压缩条目(Vista+ 标准),16~256 共 6 档。
注意:不要用 offscreen 平台 —— 它渲染不出彩色 emoji 字形。
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QBuffer, QIODevice, QSize
from PySide6.QtGui import QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icon.ico"
SIZES = (256, 128, 64, 48, 32, 16)


def render_png(size: int) -> bytes:
    """按指定边长独立渲染 😀(字体按尺寸渲染,小尺寸更清晰)→ PNG 字节。"""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont("Segoe UI Emoji")
    font.setPixelSize(int(size * 0.82))
    painter.setFont(font)
    painter.drawText(img.rect(), 0x84, "😀")  # 0x84 = AlignCenter
    painter.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def build_ico(pngs: list[tuple[int, bytes]]) -> bytes:
    """PNG 列表 → ICO(ICONDIR + ICONDIRENTRY × N + PNG 数据)。"""
    count = len(pngs)
    header = struct.pack("<HHH", 0, 1, count)  # reserved, type=icon, 数量
    offset = 6 + 16 * count
    entries = bytearray()
    data = bytearray()
    for size, png in pngs:
        w = 0 if size >= 256 else size  # 256 存 0
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(png), offset)
        data += png
        offset += len(png)
    return bytes(header + entries + data)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):  # GBK 控制台防 UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    app = QApplication.instance() or QApplication(sys.argv)
    pngs = [(s, render_png(s)) for s in SIZES]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build_ico(pngs))
    print(f"✓ {OUT}({OUT.stat().st_size} 字节,{len(SIZES)} 档:{SIZES})")


if __name__ == "__main__":
    main()
