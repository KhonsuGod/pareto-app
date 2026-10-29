"""Menu interaktif Tool 2: Tooling & Spare Monitoring (Proses 2)."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from .repository import SpareStore
from . import service
from .models import StockStatus

LINE = "-" * 64


def _fmt_stock(view) -> str:
    return "belum diinput" if view.stock is None else str(view.stock)


def _pick(prompt: str, choices: list[str], allow_blank: bool = True) -> str:
    """Pilih dari daftar; ketik nomor atau teks (case-insensitive)."""
    for i, c in enumerate(choices, start=1):
        print(f"    {i}. {c}")
    raw = input(f"  {prompt}: ").strip()
    if not raw and allow_blank:
        return ""
    if raw.isdigit() and 1 <= int(raw) <= len(choices):
        return choices[int(raw) - 1]
    for c in choices:
        if c.casefold() == raw.casefold():
            return c
    return raw  # bebas ketik; validasi bisnis yang menolak bila salah


def _store(cfg) -> SpareStore:
    return SpareStore(cfg)


def _stock_status_line(view) -> str:
    return (f"  {view.item.family:<28} {view.item.component:<16} "
            f"stock={_fmt_stock(view):<12} [{view.status.value}]")


# --------------------------------------------------------------------------- #
# aksi menu
# --------------------------------------------------------------------------- #
def _status(cfg) -> None:
    store = _store(cfg)
    views = service.stock_views(store)
    unknown = [v for v in views if v.status == StockStatus.UNKNOWN]
    alarm = [v for v in views if v.status in (StockStatus.OUT, StockStatus.LOW, StockStatus.DEFICIT)]
    other = [v for v in views if v.status in (StockStatus.OK, StockStatus.NOT_CONFIGURED)]
    print(f"\n  STOCK SPARE — {len(views)} komponen / {len({v.item.family for v in views})} family")
    print(f"  Alarm: {len(alarm)} | Stock belum diinput: {len(unknown)}")
    if alarm:
        print("\n  == STOCK ALARM ==")
        for v in sorted(alarm, key=lambda v: (v.status.value, v.item.family)):
            print(_stock_status_line(v))
    if unknown:
        print("\n  == STOCK BELUM DIINPUT (jalankan opname) ==")
        for v in unknown[:10]:
            print(_stock_status_line(v))
        if len(unknown) > 10:
            print(f"  ... dan {len(unknown) - 10} lainnya")
    if other:
        print("\n  == STOCK TERSEDIA ==")
        for v in other:
            print(_stock_status_line(v))


def _input_out(cfg) -> None:
    store = _store(cfg)
    wb = store.load()
    items = service.stock_views(store, wb)
    families = sorted({v.item.family for v in items})
    print("\n  Input pengeluaran spare (Ctrl+C batal)")
    family = _pick("Tooling Family", families, allow_blank=False)
    comps = sorted({v.item.component for v in items if v.item.family.casefold() == family.casefold()})
    component = _pick("Sparepart", comps, allow_blank=False)
    raw = input("  Qty Keluar: ").strip()
    try:
        qty = int(raw)
    except ValueError:
        print("  [ERROR] Qty harus bilangan bulat positif.")
        return
    mesin = input("  Mesin Tujuan (Enter = kosong): ").strip()
    kode_bj = input("  Kode BJ (Enter = kosong): ").strip()
    keterangan = input("  Keterangan / Alasan: ").strip()
    pic = input("  PIC / Checker: ").strip()

    # tampilkan ringkasan & validasi pra-simpan
    item = next((v for v in items
                 if v.item.family.casefold() == family.casefold()
                 and v.item.component.casefold() == component.casefold()), None)
    print("\n  Konfirmasi:")
    print(f"    Family    : {family}")
    print(f"    Komponen  : {component}")
    print(f"    Qty       : {qty}")
    if mesin:
        print(f"    Mesin     : {mesin}")
    if kode_bj:
        print(f"    Kode BJ   : {kode_bj}")
    if item is not None and item.stock is not None:
        print(f"    Stock now : {item.stock} -> {item.stock - qty}")
    confirm = input("  Simpan? [y/N]: ").strip().lower()
    if confirm != "y":
        print("  Dibatalkan.")
        return
    try:
        tx = service.record_out(store, family=family, component=component, qty=qty,
                                mesin=mesin, kode_bj=kode_bj, keterangan=keterangan,
                                pic=pic)
    except ValueError as exc:
        print(f"  [ERROR] {exc}")
        if str(exc).startswith("Stock akan menjadi -") :
            ans = input("  Override stock negatif? [y/N]: ").strip().lower()
            if ans == "y":
                reason = input("  Alasan override (wajib): ").strip()
                if not reason:
                    print("  [ERROR] Override tanpa alasan ditolak.")
                    return
                keterangan = f"{keterangan} | OVERRIDE: {reason}".strip(" |")
                tx = service.record_out(store, family=family, component=component, qty=qty,
                                        mesin=mesin, kode_bj=kode_bj, keterangan=keterangan,
                                        pic=pic, override_negative=True)
            else:
                return
    views = service.stock_views(store)
    now_stock = next((v.stock for v in views
                      if v.item.family.casefold() == family.casefold()
                      and v.item.component.casefold() == component.casefold()), None)
    print("\n  [OK] Pengeluaran tercatat")
    print(f"    Family       : {family}")
    print(f"    Component    : {component}")
    print(f"    Qty          : {qty}")
    print(f"    Stock aktual : {_fmt_stock_pad(now_stock)}")
    print(f"    ID           : {tx.txn_id}")


def _fmt_stock_pad(value) -> str:
    return "belum diinput" if value is None else str(value)


def _find(cfg) -> None:
    store = _store(cfg)
    query = input("  Cari (Kode BJ / nama produk / family / mesin): ").strip()
    if not query:
        print("  [ERROR] Kata kunci kosong.")
        return
    rows = service.find_tooling(store, query)
    if not rows:
        print("  Tidak ada hasil di MASTER TOOLING.")
        return
    print(f"\n  {len(rows)} hasil untuk '{query}':")
    for r in rows[:20]:
        unverified = " [BELUM TERVERIFIKASI]" if r.unverified() else ""
        print(f"\n  No.{r.no} | {r.family} | {r.kode_bj or '(tanpa Kode BJ)'}{unverified}")
        print(f"    Produk : {r.nama_produk or '-'}")
        print(f"    Mesin  : {r.mesin or '-'} | Cavity: {r.cavity if r.cavity is not None else '-'}")
        parts = ", ".join(f"{name}={val}" for name, val in
                          (("Mould", r.mould), ("Insert", r.insert),
                           ("Plug Assist", r.plug_assist), ("Ejector", r.ejector)) if val)
        print(f"    Komponen: {parts or 'CEK TS (belum terverifikasi)'}")
    if len(rows) > 20:
        print(f"  ... dan {len(rows) - 20} hasil lain (perjelas kata kunci)")


def _alarms(cfg) -> None:
    store = _store(cfg)
    alarm = service.alarms(store)
    if not alarm:
        print("\n  Tidak ada stock alarm.")
        return
    print(f"\n  STOCK ALARM ({len(alarm)} item)")
    for v in sorted(alarm, key=lambda v: (v.status.value, v.item.family, v.item.component)):
        minimum = v.minimum if v.minimum is not None else "-"
        print(f"  [{v.status.value:<8}] {v.item.family:<28} {v.item.component:<16} "
              f"sisa={_fmt_stock(v):<12} min={minimum}")


def _pareto_menu(cfg) -> None:
    store = _store(cfg)
    print("\n  Periode: 1. Hari ini  2. 7 hari terakhir  3. Bulan ini  4. Rentang kustom")
    ch = input("  Pilih [1-4]: ").strip()
    today = dt.date.today()
    start = end = None
    if ch == "1":
        start = end = today
    elif ch == "2":
        start, end = today - dt.timedelta(days=6), today
    elif ch == "3":
        start, end = today.replace(day=1), today
    elif ch == "4":
        s = input("  Dari (YYYY-MM-DD): ").strip()
        e = input("  Sampai (YYYY-MM-DD): ").strip()
        try:
            start = dt.datetime.strptime(s, "%Y-%m-%d").date()
            end = dt.datetime.strptime(e, "%Y-%m-%d").date()
        except ValueError:
            print("  [ERROR] Format tanggal salah.")
            return
    result = service.pareto(store.read_log(store.load()), start=start, end=end, top=5)
    label = f"{start or 'awal'} s/d {end or 'sekarang'}"
    print(f"\n  PARETO PEMAKAIAN SPARE — {label}")
    if result["n_tx"] == 0:
        print("  Belum ada transaksi pada periode ini.")
        return
    for dim in ("component", "family", "machine"):
        rows, total = result[dim]
        print(f"\n  Per {dim} (total {total}):")
        if not rows:
            print("    (kosong)")
        for i, r in enumerate(rows, start=1):
            print(f"    {i}. {r['name']:<26} {r['qty']:>4}  "
                  f"({r['freq']}x)  {r['pct']*100:5.1f}%  kum {r['cum_pct']*100:5.1f}%")
    print("  Catatan: bandingkan qty hanya antar item dengan satuan sama (cek catatan STOCK SPARE).")


def _history_menu(cfg) -> None:
    store = _store(cfg)
    s = input("  Dari (YYYY-MM-DD, Enter = awal): ").strip()
    e = input("  Sampai (YYYY-MM-DD, Enter = hari ini): ").strip()
    fam = input("  Filter family (Enter = semua): ").strip()
    comp = input("  Filter komponen (Enter = semua): ").strip()
    start = dt.datetime.strptime(s, "%Y-%m-%d").date() if s else None
    end = dt.datetime.strptime(e, "%Y-%m-%d").date() if e else dt.date.today()
    rows = service.history(store, start, end, fam, comp)
    if not rows:
        print("\n  Tidak ada transaksi pada filter ini.")
        return
    print(f"\n  RIWAYAT ({len(rows)} transaksi)")
    for t in rows[-30:]:
        print(f"  {t.date} {t.jam or '-'} | {t.family:<24} {t.component:<14} "
              f"qty={t.qty:<3} {t.mesin:<6} {t.kode_bj:<14} {t.pic}")
    if len(rows) > 30:
        print(f"  ... {len(rows) - 30} transaksi lebih lama (perkecil rentang untuk melihat)")


def _opname_menu(cfg) -> None:
    store = _store(cfg)
    wb = store.load()
    items = service.stock_views(store, wb)
    families = sorted({v.item.family for v in items})
    print("\n  Update stock opname (Ctrl+C batal)")
    family = _pick("Tooling Family", families, allow_blank=False)
    comps = sorted({v.item.component for v in items if v.item.family.casefold() == family.casefold()})
    component = _pick("Sparepart", comps, allow_blank=False)
    item = next((v for v in items
                 if v.item.family.casefold() == family.casefold()
                 and v.item.component.casefold() == component.casefold()), None)
    if item is not None:
        print(f"  Stock sistem : {_fmt_stock_pad(item.stock)}")
    raw = input("  Jumlah fisik: ").strip()
    try:
        physical = int(raw)
    except ValueError:
        print("  [ERROR] Jumlah fisik harus bilangan bulat >= 0.")
        return
    lokasi = input("  Lokasi (Enter = tetap): ").strip()
    kondisi = input("  Kondisi (Enter = tetap): ").strip()
    catatan = input("  Catatan (Enter = tetap): ").strip()
    pic = input("  PIC / Checker: ").strip()
    reason = input("  Alasan / keterangan opname: ").strip()
    try:
        res = service.opname(store, family=family, component=component, physical=physical,
                             lokasi=lokasi, kondisi=kondisi, catatan=catatan,
                             pic=pic, reason=reason)
    except ValueError as exc:
        print(f"  [ERROR] {exc}")
        return
    print("\n  [OK] Opname tercatat")
    print(f"    Tipe          : {res['kind']}")
    if res["previous"] is not None:
        print(f"    Stock sistem  : {res['previous']}")
        print(f"    Selisih       : {res['diff']}")
    print(f"    Stock fisik   : {res['physical']}")
    print(f"    Stock Awal baru: {res['new_awal']}")
    print(f"    ID ledger     : {res['entry_id']}")


def _open_workbook(cfg) -> None:
    store = SpareStore(cfg)
    path = store.ensure_workbook()
    os.startfile(path)  # type: ignore[attr-defined]
    print(f"  Membuka {path}")


def _daily_menu(cfg) -> None:
    store = _store(cfg)
    raw = input("  Tanggal (YYYY-MM-DD, Enter = hari ini): ").strip()
    day = dt.datetime.strptime(raw, "%Y-%m-%d").date() if raw else dt.date.today()
    s = service.daily_summary(store, day)
    print(f"\n  DAILY SUMMARY SPARE — {s['date']}")
    print(f"    Transaksi OUT : {s['n_tx']}")
    print(f"    Total qty     : {s['total_qty']}")
    if s["top_component"]:
        print(f"    Top komponen  : {s['top_component'][0]} = {s['top_component'][1]}")
    if s["top_family"]:
        print(f"    Top family    : {s['top_family'][0]} = {s['top_family'][1]}")
    n_alarm = len(s["alarms"])
    print(f"    Stock alarm   : {n_alarm}")


def _whatsapp_menu(cfg) -> None:
    from ..message import _copy_clipboard  # reuse util clipboard Tool 1
    store = _store(cfg)
    raw = input("  Tanggal (YYYY-MM-DD, Enter = hari ini): ").strip()
    day = dt.datetime.strptime(raw, "%Y-%m-%d").date() if raw else dt.date.today()
    text = service.whatsapp_summary(store, day)
    print("\n" + LINE)
    print(text, end="")
    print(LINE)
    out = Path(cfg.get("_root", ".")) / "data" / "spare"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"Draft_WhatsApp_Spare_{day.isoformat()}.txt"
    path.write_text(text, encoding="utf-8")
    print(f"  Disimpan: {path}")
    try:
        if input("  Salin ke clipboard? [y/N]: ").strip().lower() == "y":
            print("  Disalin." if _copy_clipboard(text) else "  Gagal menyalin.")
    except EOFError:
        pass


def _correlate_menu(cfg) -> None:
    store = _store(cfg)
    aliases = ((cfg.get("spare") or {}).get("downtime_aliases")) or {}
    print("\n  Korelasi downtime Tool 1 vs spare keluar (indikator saja)")
    try:
        rows = service.downtime_correlation(store, aliases=aliases)
    except RuntimeError as exc:
        print(f"  [INFO] {exc}")
        return
    if not rows:
        print("  Belum ada data untuk dikorelasikan.")
        return
    print(f"  {'Komponen':<16} {'Downtime':>9} {'Spare':>6}")
    for r in rows[:15]:
        print(f"  {r['component']:<16} {r['downtime_mentions']:>9} {r['spare_out']:>6}")
    print("  Catatan: indikator operasional, bukan klaim sebab-akibat.")


# --------------------------------------------------------------------------- #
# loop menu utama Tool 2
# --------------------------------------------------------------------------- #
def run(cfg: dict) -> str:
    title = "TOOLING & SPARE — PROSES 2".replace("—", "-")
    items = (
        ("1", "Status stock spare", _status),
        ("2", "Input pengeluaran spare", _input_out),
        ("3", "Cari tooling / produk", _find),
        ("4", "Alarm stock", _alarms),
        ("5", "Pareto pemakaian spare", _pareto_menu),
        ("6", "Riwayat pengeluaran", _history_menu),
        ("7", "Update stock opname", _opname_menu),
        ("8", "Buka workbook spare", _open_workbook),
        ("9", "Daily summary spare", _daily_menu),
        ("10", "Draft WhatsApp spare", _whatsapp_menu),
        ("11", "Korelasi downtime (indikator)", _correlate_menu),
    )
    while True:
        print(LINE)
        print("  TOOLING & SPARE - PROSES 2")
        print(LINE)
        for key, label, _fn in items:
            print(f"  {key:>2}. {label}")
        print("   0. Kembali ke launcher")
        try:
            choice = input("\n  Pilih menu: ").strip()
        except EOFError:
            return "back"
        if choice in ("0", "q", "keluar", "exit"):
            return "back"
        action = next((fn for k, _l, fn in items if k == choice), None)
        if action is None:
            print("  Pilihan tidak ada.")
            continue
        try:
            action(cfg)
        except KeyboardInterrupt:
            print("\n  Dibatalkan.")
        except Exception as exc:
            print(f"\n  [ERROR] {exc}")
        print()
        try:
            input("  Tekan Enter untuk kembali ke menu...")
        except EOFError:
            return "back"
