"""Menu interaktif CLI (dipakai saat `python app.py` tanpa argumen)."""
from __future__ import annotations

from . import banner, processes

LINE = "-" * 64


def _pick_process(cfg: dict, default: str | None = None) -> str | None:
    procs = processes.available(cfg)
    print("\n  Pilih proses:")
    for i, (key, label) in enumerate(procs, start=1):
        print(f"    {i}. {label}")
    default = default or cfg.get("default_process", "proses2")
    default_no = str([k for k, _ in procs].index(default) + 1) if default in dict(procs) else "2"
    try:
        raw = input(f"  Nomor proses [{default_no}]: ").strip()
    except EOFError:
        return None
    if not raw:
        raw = default_no
    if raw.isdigit() and 1 <= int(raw) <= len(procs):
        return procs[int(raw) - 1][0]
    try:
        return processes.normalize_key(raw, cfg)
    except KeyError:
        print("  Proses tidak dikenal.")
        return None


def _pick_date() -> str | None:
    try:
        raw = input("  Tanggal YYYY-MM-DD (Enter = otomatis): ").strip()
    except EOFError:
        return None
    return raw or None


def _header(cfg: dict) -> None:
    procs = " + ".join(label for _k, label in processes.available(cfg))
    print(LINE)
    print(f"  {cfg.get('project', {}).get('area', 'BOLANG')}  |  {procs}")
    print(LINE)


def run(cfg: dict, actions: dict, title: str | None = None, back: bool = False) -> int | str:
    """actions: update(proses, date), status(), draft(proses, date),
    validate(proses), open_output(proses).

    back=True  -> pilihan 0 jadi 'Kembali ke launcher', return "back".
    title      -> tampilkan judul section, bukan banner penuh (mode submenu).
    """
    if title:
        print(LINE)
        print(f"  {title}")
        print(LINE)
    else:
        print(banner.banner())
    exit_label = "0. Kembali ke launcher" if back else "0. Keluar"
    while True:
        if not title:
            _header(cfg)
        print("  1. Update data Proses 2")
        print("  2. Update data Proses 1")
        print("  3. Lihat status produksi")
        print("  4. Buat draft pesan WhatsApp")
        print("  5. Validasi workbook")
        print("  6. Buka folder hasil")
        print(f"  {exit_label}")
        try:
            choice = input("\n  Pilih menu: ").strip()
        except EOFError:
            print()
            return "back" if back else 0

        try:
            if choice == "1":
                date = _pick_date()
                actions["update"]("proses2", date)
            elif choice == "2":
                date = _pick_date()
                actions["update"]("proses1", date)
            elif choice == "3":
                actions["status"]()
            elif choice == "4":
                key = _pick_process(cfg)
                if key is None:
                    continue
                date = _pick_date()
                actions["draft"](key, date)
            elif choice == "5":
                key = _pick_process(cfg)
                if key is not None:
                    actions["validate"](key)
            elif choice == "6":
                key = _pick_process(cfg)
                if key is not None:
                    actions["open_output"](key)
            elif choice in ("0", "q", "keluar", "exit"):
                if back:
                    return "back"
                print("  Selesai.")
                return 0
            else:
                print("  Pilihan tidak ada.")
        except KeyboardInterrupt:
            print("\n  Dibatalkan.")
        except Exception as exc:  # jangan matikan menu karena satu error
            print(f"\n  [ERROR] {exc}")

        if back and choice in ("0", "q", "keluar", "exit"):
            return "back"
        print()
        try:
            input("  Tekan Enter untuk kembali ke menu...")
        except EOFError:
            return "back" if back else 0
