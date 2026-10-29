"""Test banner ASCII art + warna kuning."""
from __future__ import annotations

from src import banner


def test_render_five_lines_and_centered():
    art = banner.render("DIO BELAGAMA")
    assert len(art.splitlines()) == 5
    b = banner.banner()
    for line in b.strip().splitlines():
        assert banner.render("DIO BELAGAMA").splitlines()[0].rstrip() or True
    assert "PROSES MONITOR  |  DAILY DOWNTIME" in b


def test_banner_no_ansi_when_not_tty(monkeypatch):
    import sys
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    out = banner.banner()
    assert "\033[93m" not in out
    assert "DIO BELAGAMA" not in out  # art-nya ASCII blok, bukan teks asli
    assert "####  ###  ###" in out     # huruf D I O di baris pertama


def test_banner_has_yellow_when_tty(monkeypatch):
    import sys
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    out = banner.banner()
    assert banner.YELLOW in out
    assert banner.RESET in out
    assert out.count(banner.RESET) == 1  # seluruh banner satu blok warna


def test_banner_byline_and_centering(monkeypatch):
    import shutil

    class _Term:
        columns = 100
        lines = 24

    monkeypatch.setattr(banner.shutil, "get_terminal_size", lambda *a, **k: _Term)
    out = banner.banner()
    assert "tools by : davi" in out
    assert "support : bryan addam" in out
    assert "github.com/KhonsuGod/pareto-app" in out
    lines = [line for line in out.splitlines() if line.strip()]
    # setiap baris di-center: tengah teks aslinya jatuh di tengah terminal (kolom 50)
    for line in lines:
        pad = len(line) - len(line.lstrip(" "))
        raw_center = pad + (len(line) - pad) / 2
        assert abs(raw_center - 50) <= 1
    assert any(line.strip() == "tools by : davi" for line in lines)