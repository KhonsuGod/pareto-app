"""ASCII art & tampilan menu CLI (tanpa dependency)."""
from __future__ import annotations

import os
import shutil
import sys

# Kuning hanya untuk ASCII art (93 = bright yellow).
YELLOW = "\033[93m"
RESET = "\033[0m"

_ansi_done = {"done": False}


def _enable_ansi() -> None:
    """Nyalakan virtual terminal di console Windows (cmd lama mati default)."""
    if _ansi_done["done"] or not sys.stdout.isatty():
        return
    _ansi_done["done"] = True
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            mode = ctypes.c_uint32()
            if k32.GetConsoleMode(k32.GetStdHandle(-11), ctypes.byref(mode)):
                k32.SetConsoleMode(k32.GetStdHandle(-11), mode.value | 0x0004)
        except Exception:
            pass

# Font blok 5 baris. Lebar tiap glyph bebas; renderer yang meratakan.
_GLYPHS: dict[str, list[str]] = {
    "A": [" ### ", "#   #", "#####", "#   #", "#   #"],
    "B": ["#### ", "#   #", "#### ", "#   #", "#### "],
    "C": [" ####", "#    ", "#    ", "#    ", " ####"],
    "D": ["#### ", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#### ", "#    ", "#####"],
    "F": ["#####", "#    ", "#### ", "#    ", "#    "],
    "G": [" ####", "#    ", "#  ##", "#   #", " ####"],
    "H": ["#   #", "#   #", "#####", "#   #", "#   #"],
    "I": ["###", " # ", " # ", " # ", "###"],
    "J": ["  ###", "   # ", "   # ", "#  # ", " ##  "],
    "K": ["#   #", "#  # ", "###  ", "#  # ", "#   #"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "#   #", "#   #"],
    "N": ["#   #", "##  #", "# # #", "#  ##", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", " ### "],
    "P": ["#### ", "#   #", "#### ", "#    ", "#    "],
    "Q": [" ### ", "#   #", "# # #", "#  # ", " ## #"],
    "R": ["#### ", "#   #", "#### ", "#  # ", "#   #"],
    "S": [" ####", "#    ", " ### ", "    #", "#### "],
    "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#   #", "#   #", "#   #", "#   #", " ### "],
    "V": ["#   #", "#   #", "#   #", " # # ", "  #  "],
    "W": ["#   #", "#   #", "# # #", "## ##", "#   #"],
    "X": ["#   #", " # # ", "  #  ", " # # ", "#   #"],
    "Y": ["#   #", " # # ", "  #  ", "  #  ", "  #  "],
    "Z": ["#####", "   # ", "  #  ", " #   ", "#####"],
    " ": ["  ", "  ", "  ", "  ", "  "],
    "-": ["   ", "   ", "---", "   ", "   "],
    ".": [" ", " ", " ", " ", "#"],
    "!": ["#", "#", "#", " ", "#"],
}


TITLE = "DIO BELAGAMA"
SUBTITLE = "PROSES MONITOR  |  DAILY DOWNTIME"
BYLINE = ("tools by : davi",
          "support : bryan addam",
          "github : github.com/KhonsuGod/pareto-app")


def render(text: str, spacing: int = 1) -> str:
    """Render teks jadi ASCII art 5 baris (huruf besar)."""
    lines = ["", "", "", "", ""]
    gap = " " * spacing
    for ch in text.upper():
        glyph = _GLYPHS.get(ch)
        if glyph is None:
            glyph = _GLYPHS[" "]
        width = max(len(g) for g in glyph)
        for i in range(5):
            lines[i] += glyph[i].ljust(width) + gap
    return "\n".join(line.rstrip() for line in lines)


def banner(title: str = TITLE,
           subtitle: str = SUBTITLE,
           byline: tuple[str, ...] = BYLINE) -> str:
    """Banner utama: ASCII art + subtitle di tengah console, byline di bawah."""
    _enable_ansi()
    art = render(title)
    art_w = max(len(line) for line in art.splitlines())
    term_w = max(art_w, shutil.get_terminal_size((80, 24)).columns)

    def center(text: str) -> str:
        pad = max(0, (term_w - len(text)) // 2)
        return " " * pad + text

    rule = "=" * art_w
    out = [center(line) for line in art.splitlines()]
    out += [center(rule), center(subtitle), center(rule)]
    out += [center(line) for line in byline]
    body = "\n".join(out)
    if sys.stdout.isatty():
        body = f"{YELLOW}{body}{RESET}"
    return f"\n{body}\n"


def parts(title: str = TITLE,
          subtitle: str = SUBTITLE,
          byline: tuple[str, ...] = BYLINE) -> tuple[str, str]:
    """(ASCII art ter-center, ekor rule+subtitle+byline) tanpa warna.

    Untuk animasi reveal di launcher: art di-reveal dulu, ekor menyusul.
    """
    _enable_ansi()
    art = render(title)
    art_w = max(len(line) for line in art.splitlines())
    term_w = max(art_w, shutil.get_terminal_size((80, 24)).columns)

    def center(text: str) -> str:
        pad = max(0, (term_w - len(text)) // 2)
        return " " * pad + text

    centered = "\n".join(center(line) for line in art.splitlines())
    rule = "=" * art_w
    tail = "\n".join([center(rule), center(subtitle), center(rule)]
                     + [center(line) for line in byline])
    return centered, tail


def box(title: str, lines: list[str], width: int = 62) -> str:
    """Kotak ASCII sederhana untuk judul section menu."""
    inner = width - 2
    out = ["+" + "-" * inner + "+"]
    out.append("| " + title[: inner - 2].ljust(inner - 2) + " |")
    out.append("+" + "-" * inner + "+")
    for line in lines:
        out.append("| " + line[: inner - 2].ljust(inner - 2) + " |")
    out.append("+" + "-" * inner + "+")
    return "\n".join(out)
