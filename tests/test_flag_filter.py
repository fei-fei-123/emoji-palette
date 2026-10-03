"""_is_flag_sequence 旗帜判定回归:Windows 渲染不出旗面,须按不支持过滤。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from emoji_palette.app import _is_flag_sequence


def test_regional_indicator_pair_is_flag():
    assert _is_flag_sequence([0x1F1E8, 0x1F1F3])  # 🇨🇳 CN 对


def test_subdivision_tag_sequence_is_flag():
    # 🏴󠁧󠁢󠁳󠁣󠁴󠁿 苏格兰细分旗:黑旗 + tag 字母 + 结束符
    assert _is_flag_sequence(
        [0x1F3F4, 0xE0067, 0xE0073, 0xE0063, 0xE0074, 0xE007F])


def test_regular_emoji_not_flag():
    assert not _is_flag_sequence([0x1F600])  # 😀
    assert not _is_flag_sequence([0x2764, 0xFE0F])  # ❤️ 变体选择符不算旗帜
    assert not _is_flag_sequence([0x1F3F4])  # 🏴 单独黑旗正常渲染
