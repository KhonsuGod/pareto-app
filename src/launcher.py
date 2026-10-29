"""Launcher dua tool: Daily Production Monitoring + Tooling & Spare Monitoring.

Dipanggil `python app.py` tanpa argumen. Animasi kosmetik (src/anim),
tidak pernah menyentuh logika Tool 1 / Tool 2.
"""
from __future__ import annotations

import sys

from . import anim, banner, menu

LINE = "-" * 64


def _startup(animate: bool) -> None:
    """Banner DIO BELAGAMA + byline. Animasi: reveal ASCII per baris."""
    if not animate or not anim.enabled():
        print(banner.banner())
        return
    art, tail = banner.parts()
    sys.stdout.write(banner.YELLOW)
    for line in art.splitlines():
        anim.typewriter(line, seconds=0.1)   # 5 baris art ~0.5s
    anim.dots("Loading interface", seconds=0.4)
    sys.stdout.write(tail + "\n" + banner.RESET)
    anim.ready("SYSTEM READY")


def run(cfg: dict, actions: dict, animate: bool = True) -> int:
    """actions: tool1(), tool2() — dipasang di app.py."""
    _startup(animate)

    first = True  # banner sudah tampil di _startup, jangan dobel
    while True:
        if not first:
            print(banner.banner())
        first = False
        print(LINE)
        print("  [1] DAILY PRODUCTION MONITORING")
        print("      Proses 1 / Proses 2 / Downtime / Pareto")
        print("  [2] TOOLING & SPARE MONITORING")
        print("      Stock / Tooling / Pengeluaran / Alarm")
        print("  [0] EXIT")
        try:
            choice = input("\n  Pilih tool: ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("\n  Dibatalkan.")
            return 0

        try:
            if choice == "1":
                anim.dots("Membuka Daily Production Monitoring", seconds=0.4)
                actions["tool1"]()
            elif choice == "2":
                anim.dots("Membuka Tooling & Spare Monitoring", seconds=0.4)
                actions["tool2"]()
            elif choice in ("0", "q", "exit", "keluar"):
                print("  Selesai.")
                return 0
            else:
                print("  Pilihan tidak ada.")
        except KeyboardInterrupt:
            print("\n  Dibatalkan.")
        except Exception as exc:
            print(f"\n  [ERROR] {exc}")

        # kembali ke pilihan tool, tanpa mengulang animasi startup
        try:
            input("\n  Tekan Enter untuk kembali ke launcher...")
        except EOFError:
            return 0
