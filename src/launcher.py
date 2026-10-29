"""Launcher dua tool: Daily Production Monitoring + Tooling & Spare Monitoring.

Dipanggil `python app.py` tanpa argumen. Animasi kosmetik (src/anim),
tidak pernah menyentuh logika Tool 1 / Tool 2.
"""
from __future__ import annotations

import os

from . import anim, banner, menu

LINE = "-" * 64


def _screen(title: str) -> None:
    print(banner.banner())
    print(menu.LINE)
    print(f"  {title}")
    print(menu.LINE)


def run(cfg: dict, actions: dict, animate: bool = True) -> int:
    """actions: tool1(), tool2(), open_output_spare() — dipasang di app.py."""
    if animate:
        anim.progress("INITIALIZING PRODUCTION MONITOR", seconds=0.7)
        anim.typewriter("PRODUCTION MONITOR - PLANT BOLANG", seconds=0.35)
        anim.ready("SYSTEM READY")
    else:
        print("PRODUCTION MONITOR - PLANT BOLANG")

    while True:
        print()
        print(LINE)
        print("  PRODUCTION MONITOR - PLANT BOLANG")
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
