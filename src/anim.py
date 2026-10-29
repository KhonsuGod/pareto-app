"""Animasi terminal ringan — kosmetik saja, tidak pernah menyentuh logika bisnis.

Aturan aktif (semua harus terpenuhi):
    - stdout interaktif (tty)
    - bukan NO_COLOR / bukan MONITOR_NO_ANIMATION
    - Windows: ANSI virtual terminal dinyalakan sekali

Direct CLI command TIDAK memanggil modul ini (hanya launcher interaktif).
"""
from __future__ import annotations

import os
import sys
import time

_ansi_done = {"done": False}


def enabled() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("MONITOR_NO_ANIMATION"):
        return False
    return True


def enable_ansi() -> None:
    if _ansi_done["done"] or os.name != "nt":
        _ansi_done["done"] = True
        return
    _ansi_done["done"] = True
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        mode = ctypes.c_uint32()
        if k32.GetConsoleMode(k32.GetStdHandle(-11), ctypes.byref(mode)):
            k32.SetConsoleMode(k32.GetStdHandle(-11), mode.value | 0x0004)
    except Exception:
        pass


def _clear() -> None:
    sys.stdout.write("\x1b[2K\r" if enabled() else "\r")
    sys.stdout.flush()


def progress(label: str = "INITIALIZING PRODUCTION MONITOR", seconds: float = 0.7) -> None:
    """Progress bar ASCII sederhana; tidak menyatakan validasi apa pun."""
    if not enabled():
        print(label)
        return
    enable_ansi()
    steps = 12
    for i in range(steps + 1):
        filled = "#" * i
        empty = "-" * (steps - i)
        pct = int(i / steps * 100)
        sys.stdout.write(f"\x1b[2K\r{label}\n\x1b[1A\x1b[2K\r[{filled.ljust(steps)}] {pct}%")
        sys.stdout.flush()
        time.sleep(seconds / steps)
    sys.stdout.write("\x1b[2K\r")
    sys.stdout.flush()


def typewriter(text: str, seconds: float = 0.4) -> None:
    """Reveal karakter per karakter (versi instan kalau animasi nonaktif)."""
    if not enabled():
        print(text)
        return
    enable_ansi()
    delay = max(0.0, seconds / max(1, len(text)))
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")


def dots(text: str, seconds: float = 0.5) -> None:
    """Transisi pendek 'teks...' — dipakai saat pindah tool."""
    if not enabled():
        print(text)
        return
    enable_ansi()
    sys.stdout.write(text)
    sys.stdout.flush()
    for _ in range(3):
        time.sleep(seconds / 3)
        sys.stdout.write(".")
        sys.stdout.flush()
    sys.stdout.write("\n")


def spinner(text: str, seconds: float = 0.6) -> None:
    """Spinner kecil |/-\\ — tidak menyatakan pemeriksaan apa pun."""
    if not enabled():
        print(text)
        return
    enable_ansi()
    frames = "|/-\\"
    per = seconds / len(frames)
    for fr in frames:
        sys.stdout.write(f"\x1b[2K\r{fr} {text}")
        sys.stdout.flush()
        time.sleep(per)
    sys.stdout.write("\x1b[2K\r")
    sys.stdout.flush()


def ready(text: str = "SYSTEM READY") -> None:
    print(text)
