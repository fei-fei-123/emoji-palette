"""IME 门禁判定测试(ime_transcribing 子模式双判,M5 案件 2 回归)。

真机探测数据(2026-10-01,MS 拼音):中文子模式 IMC_GETCONVERSIONMODE
= 1025(原生|符号),英文子模式 = 0,英文键盘 IMC_GETOPENSTATUS = 0。
门禁据此三态:英文键盘/英文子模式 → 放行;中文原生/全角 → 拦截。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from emoji_palette import ime


class _FakeUser32:
    def __init__(self, hwnd: int = 99, status: int = 1, mode: int = 0,
                 exc: bool = False) -> None:
        self._hwnd, self._status = hwnd, status
        self._mode, self._exc = mode, exc
        self.queries: list[int] = []  # 实际发出的 IMC_* 查询(断言短路用)

    def GetForegroundWindow(self) -> int:
        return self._hwnd

    def SendMessageW(self, hime: int, msg: int, param: int, _extra: int) -> int:
        if self._exc:
            raise RuntimeError("boom")
        self.queries.append(param)
        return self._status if param == ime.IMC_GETOPENSTATUS else self._mode


class _FakeImm:
    def __init__(self, hime: int = 7) -> None:
        self._hime = hime

    def ImmGetDefaultIMEWnd(self, _hwnd: int) -> int:
        return self._hime


def _patch(monkeypatch, **kw) -> _FakeUser32:
    user32 = _FakeUser32(**kw)
    monkeypatch.setattr(ime, "user32", user32)
    monkeypatch.setattr(ime, "imm32", _FakeImm())
    return user32


def test_english_keyboard_passes(monkeypatch):
    """纯英文键盘:IME 关闭 → 放行(不查子模式)。"""
    u = _patch(monkeypatch, status=0)
    assert ime.ime_transcribing() is False
    assert u.queries == [ime.IMC_GETOPENSTATUS]  # 短路,未查转换模式


def test_chinese_submode_blocks(monkeypatch):
    """中文子模式(真机实测 mode=1025)→ 拦截。"""
    _patch(monkeypatch, status=1, mode=1025)
    assert ime.ime_transcribing() is True


def test_english_submode_passes(monkeypatch):
    """中文输入法的英文半角子模式(mode=0)→ 放行(FR4.3 本意,M5 修复点)。"""
    _patch(monkeypatch, status=1, mode=0)
    assert ime.ime_transcribing() is False


def test_fullshape_english_blocks(monkeypatch):
    """英文全角子模式(0x0008):产出全角非 ASCII,回删镜像会错位 → 拦截。"""
    _patch(monkeypatch, status=1, mode=ime.IME_CMODE_FULLSHAPE)
    assert ime.ime_transcribing() is True


def test_query_exception_passes(monkeypatch):
    """查询异常 → False(与 ime_open 失败语义一致)。"""
    _patch(monkeypatch, exc=True)
    assert ime.ime_transcribing() is False


def test_no_foreground_or_ime_window(monkeypatch):
    """无前台窗口 / 无默认 IME 窗口 → 放行。"""
    _patch(monkeypatch, hwnd=0)
    assert ime.ime_transcribing() is False
    monkeypatch.setattr(ime, "user32", _FakeUser32())
    monkeypatch.setattr(ime, "imm32", _FakeImm(hime=0))
    assert ime.ime_transcribing() is False
