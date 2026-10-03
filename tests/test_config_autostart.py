"""autostart_command 模板回归:开机静默(开发态必须 pythonw,免控制台黑窗)。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from emoji_palette import config


def test_frozen_uses_exe_itself(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert config.autostart_command() == f'"{sys.executable}"'


def test_dev_uses_pythonw_for_silent_boot(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    cmd = config.autostart_command()
    assert "pythonw.exe" in cmd  # 免控制台黑窗
    assert "emoji_palette.app" in cmd  # 仍走 -c 引导带 src 路径
