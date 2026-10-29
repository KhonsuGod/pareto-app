"""Logika bisnis Tool 2: lookup, stock, transaksi, alarm, analitik, draft."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from .models import OutTx, StockStatus, StockView
from .repository import SpareStore, _key, _norm


def _parse_date(text: str | None, default: dt.date | None = None) -> dt.date | None:
    if not text:
        return default
    return dt.datetime.strptime(str(text).strip(), "%Y-%m-%d").date()


# --------------------------------------------------------------------------- #
# lookup tooling (product-first, read-only)
# --------------------------------------------------------------------------- #
def find_tooling(store: SpareStore, query: str) -> list:
    """Cari routing di MASTER TOOLING. Semua hasil dikembalikan (tidak dipilih diam-diam)."""
    wb = store.load()
    rows = store.read_routing(wb)
    q = query.strip().casefold()
    exact_bj = [r for r in rows if r.kode_bj.upper() == query.strip().upper()]
    if exact_bj:
        return exact_bj
    hits = []
    seen = set()
    for r in rows:
        hay = f"{r.kode_bj} {r.nama_produk} {r.family} {r.mesin}".casefold()
        if q in hay:
            token = (r.row,)
            if token not in seen:
                seen.add(token)
                hits.append(r)
    return hits


def routing_for_bj(store: SpareStore, kode_bj: str) -> list:
    wb = store.load()
    return [r for r in store.read_routing(wb)
            if r.kode_bj.upper() == kode_bj.strip().upper()]


# --------------------------------------------------------------------------- #
# stock (mirror formula Excel)
# --------------------------------------------------------------------------- #
def stock_views(store: SpareStore, wb=None) -> list[StockView]:
    wb = wb or store.load()
    items = store.read_stock_items(wb)
    txs = store.read_log(wb)
    today = dt.date.today()
    keluar: dict[tuple[str, str], int] = defaultdict(int)
    keluar_today: dict[tuple[str, str], int] = defaultdict(int)
    for t in txs:
        if t.qty <= 0:
            continue
        k = (_key(t.family), _key(t.component))
        keluar[k] += t.qty
        if t.date == today:
            keluar_today[k] += t.qty
    views = []
    for it in items:
        total = keluar.get(it.key, 0)
        if it.stock_awal is None:
            stock = None
            status = StockStatus.UNKNOWN
        else:
            stock = it.stock_awal - total
            minimum = store.minimum_for(it.family, it.component)
            if stock < 0:
                status = StockStatus.DEFICIT
            elif stock == 0:
                status = StockStatus.OUT
            elif minimum is None:
                status = StockStatus.NOT_CONFIGURED
            elif stock <= minimum:
                status = StockStatus.LOW
            else:
                status = StockStatus.OK
        views.append(StockView(item=it, keluar_total=total, keluar_today=keluar_today.get(it.key, 0),
                               stock=stock, status=status, minimum=store.minimum_for(it.family, it.component)))
    return views


def alarms(store: SpareStore, wb=None) -> list[StockView]:
    """Stock alarm: OUT / LOW / DEFICIT. UNKNOWN bukan alarm (belum diinput)."""
    return [v for v in stock_views(store, wb)
            if v.status in (StockStatus.OUT, StockStatus.LOW, StockStatus.DEFICIT)]


# --------------------------------------------------------------------------- #
# transaksi OUT
# --------------------------------------------------------------------------- #
def validate_out(store: SpareStore, family: str, component: str, qty: int,
                 kode_bj: str = "", mesin: str = "") -> list[str]:
    """Validasi input pengeluaran sebelum menulis. Error = blok."""
    errors = []
    wb = store.load()
    items = {(i.family.casefold(), i.component.casefold()): i for i in store.read_stock_items(wb)}
    item = items.get((_key(family), _key(component)))
    if item is None:
        errors.append(f"Kombinasi family '{family}' + komponen '{component}' tidak ada di STOCK SPARE.")
    if not isinstance(qty, int) or qty <= 0:
        errors.append(f"Qty keluar harus bilangan bulat positif (dapat: {qty!r}).")
    if kode_bj:
        routing = routing_for_bj(store, kode_bj)
        if not routing:
            errors.append(f"Kode BJ '{kode_bj}' tidak ditemukan di MASTER TOOLING.")
        elif family and _key(family) not in {r.family.casefold() for r in routing}:
            fams = sorted({r.family for r in routing})
            errors.append(f"Kode BJ '{kode_bj}' bukan routing '{family}' (family valid: {fams}).")
    if item is not None and item.stock_awal is None and not errors:
        errors.append(
            f"Stock '{item.family}/{item.component}' belum diinput (Stock Awal kosong).\n"
            f"       Jalankan opname dulu supaya stock terverifikasi sebelum pengeluaran dicatat.")
    if item is not None and item.stock_awal is not None and isinstance(qty, int) and qty > 0:
        projected = item.stock_awal - sum(t.qty for t in store.read_log(wb)
                                          if t.qty > 0 and _key(t.family) == _key(family)
                                          and _key(t.component) == _key(component)) - qty
        if projected < 0:
            errors.append(f"__NEGATIVE__{projected}")
    return errors


def record_out(store: SpareStore, *, family: str, component: str, qty: int,
               mesin: str = "", kode_bj: str = "", keterangan: str = "", pic: str = "",
               txn_id: str | None = None, override_negative: bool = False) -> OutTx:
    """Catat pengeluaran: validasi -> append LOG -> LEDGER bila override -> save aman."""
    from . import validator as spare_validator
    wb = store.load()
    errors = validate_out(store, family, component, qty, kode_bj, mesin)
    negative = [e for e in errors if e.startswith("__NEGATIVE__")]
    blocking = [e for e in errors if not e.startswith("__NEGATIVE__")]
    if blocking:
        raise ValueError("\n".join(blocking))
    if negative and not override_negative:
        raise ValueError(f"Stock akan menjadi {negative[0].replace('__NEGATIVE__', '')} "
                         f"(negatif). Butuh konfirmasi override + alasan.")
    if not txn_id:
        txn_id = store.next_txn_id("OUT")
    produk = ""
    if kode_bj:
        routing = routing_for_bj(store, kode_bj)
        names = sorted({r.nama_produk for r in routing if r.nama_produk})
        produk = names[0] if len(names) == 1 else ""
    now = dt.datetime.now()
    tx = OutTx(row=0, txn_id=txn_id, date=now.date(), jam=now.time().replace(microsecond=0),
               mesin=mesin, family=family, kode_bj=kode_bj, nama_produk=produk,
               component=component, qty=qty, keterangan=keterangan, pic=pic)
    store.ensure_structure(wb)
    row = store.append_out(wb, tx, override=override_negative and bool(negative))
    if row == -1:
        return tx  # replay: sudah pernah tercatat
    _refresh_dashboard(store, wb)
    def _check(w):
        return spare_validator.validate_spare_workbook(w)
    store.save(wb, validator=_check)
    return tx


# --------------------------------------------------------------------------- #
# opname / opening / adjustment
# --------------------------------------------------------------------------- #
def opname(store: SpareStore, *, family: str, component: str, physical: int,
           lokasi: str = "", kondisi: str = "", catatan: str = "", pic: str = "",
           reason: str = "", set_location: bool = True) -> dict:
    """Stock opname: OPENING (stock belum ada) atau ADJUSTMENT (koreksi terverifikasi)."""
    from . import validator as spare_validator
    if not isinstance(physical, int) or physical < 0:
        raise ValueError("Jumlah fisik harus bilangan bulat >= 0.")
    wb = store.load()
    items = {(i.family.casefold(), i.component.casefold()): i for i in store.read_stock_items(wb)}
    item = items.get((_key(family), _key(component)))
    if item is None:
        raise ValueError(f"Kombinasi '{family}' + '{component}' tidak ada di STOCK SPARE.")

    keluar = sum(t.qty for t in store.read_log(wb)
                 if t.qty > 0 and _key(t.family) == _key(family)
                 and _key(t.component) == _key(component))
    kind, diff, new_awal = "", 0, physical
    if item.stock_awal is None:
        kind = "OPENING"
        previous = None
    else:
        previous = item.stock_awal
        system = item.stock_awal - keluar
        diff = physical - system
        new_awal = item.stock_awal + diff
        kind = "ADJUSTMENT"
    store.set_opening(wb, item.row, new_awal,
                      lokasi=lokasi if lokasi else None,
                      kondisi=kondisi if kondisi else None,
                      catatan=catatan if catatan else None)
    entry_id = store.append_ledger(wb, kind=kind, family=item.family, component=item.component,
                                   previous_awal=previous, physical=physical, diff=diff,
                                   new_awal=new_awal, pic=pic, note=reason)
    _refresh_dashboard(store, wb)
    store.save(wb, validator=spare_validator.validate_spare_workbook)
    return {"kind": kind, "previous": previous, "physical": physical,
            "diff": diff, "new_awal": new_awal, "entry_id": entry_id}


def _refresh_dashboard(store: SpareStore, wb) -> None:
    """Dashboard dibuat/diperbarui hanya bila sudah ada transaksi OUT nyata."""
    from .pareto import build_dashboard
    txs = [t for t in store.read_log(wb) if t.qty > 0]
    if not txs:
        return
    views = stock_views(store, wb)
    build_dashboard(wb, [v.item for v in views], views, dt.datetime.now())


# --------------------------------------------------------------------------- #
# riwayat & ringkasan harian
# --------------------------------------------------------------------------- #
def history(store: SpareStore, start: dt.date | None = None, end: dt.date | None = None,
            family: str = "", component: str = "") -> list[OutTx]:
    txs = store.read_log(store.load())
    out = []
    for t in txs:
        if start and (t.date is None or t.date < start):
            continue
        if end and (t.date is None or t.date > end):
            continue
        if family and _key(t.family) != _key(family):
            continue
        if component and _key(t.component) != _key(component):
            continue
        out.append(t)
    return sorted(out, key=lambda t: (t.date or dt.date.min, t.row))


def daily_summary(store: SpareStore, day: dt.date | None = None) -> dict:
    day = day or dt.date.today()
    txs = [t for t in store.read_log(store.load())
           if t.date == day and t.qty > 0]
    by_comp: dict[str, int] = defaultdict(int)
    by_fam: dict[str, int] = defaultdict(int)
    for t in txs:
        by_comp[t.component or "-"] += t.qty
        by_fam[t.family or "-"] += t.qty
    top_comp = max(by_comp.items(), key=lambda kv: kv[1]) if by_comp else None
    top_fam = max(by_fam.items(), key=lambda kv: kv[1]) if by_fam else None
    return {
        "date": day,
        "n_tx": len(txs),
        "total_qty": sum(t.qty for t in txs),
        "top_component": top_comp,
        "top_family": top_fam,
        "alarms": alarms(store),
    }


# --------------------------------------------------------------------------- #
# draft WhatsApp spare — fakta saja
# --------------------------------------------------------------------------- #
def whatsapp_summary(store: SpareStore, day: dt.date | None = None) -> str:
    day = day or dt.date.today()
    summary = daily_summary(store, day)
    lines = [f"Update Sparepart Proses 2 Di tanggal {day.day}:", ""]
    if summary["n_tx"] == 0:
        lines.append("Belum ada pengeluaran sparepart.")
    else:
        by_comp: dict[str, int] = defaultdict(int)
        by_fam: dict[str, int] = defaultdict(int)
        for t in store.read_log(store.load()):
            if t.date == day and t.qty > 0:
                by_comp[t.component or "-"] += t.qty
                by_fam[t.family or "-"] += t.qty
        comp_txt = ", ".join(f"{k} = {v}" for k, v in sorted(by_comp.items(), key=lambda kv: -kv[1]))
        fam_txt = ", ".join(f"{k} = {v}" for k, v in sorted(by_fam.items(), key=lambda kv: -kv[1]))
        lines.append(f"Pengeluaran hari ini: {comp_txt}.")
        if fam_txt:
            lines.append(f"Per family: {fam_txt}.")
        low = [v for v in summary["alarms"] if v.status != StockStatus.UNKNOWN]
        if low:
            parts = [f"{v.item.family}/{v.item.component} sisa {v.stock}"
                     for v in low[:4]]
            lines.append("")
            lines.append("Stock menipis: " + "; ".join(parts) + ".")
            lines.append("")
            lines.append("Tolong dibantu follow up restock yang masih menipis.")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# korelasi downtime (read-only, indikator saja)
# --------------------------------------------------------------------------- #
def downtime_correlation(store: SpareStore, aliases: dict[str, list[str]] | None = None,
                         start: dt.date | None = None, end: dt.date | None = None) -> list[dict]:
    """Hitung sebutan komponen di keterangan downtime Tool 1 vs pengeluaran spare.

    Indikator operasional saja — bukan klaim sebab-akibat.
    """
    aliases = aliases or {}
    from .. import workbook as wb1
    from ..config import load_config
    from ..processes import resolve
    from ..extractor import extract_events
    cfg = resolve(load_config(), "2")
    if not wb1.find_current_workbook(cfg):
        raise RuntimeError("Workbook Tool 1 belum ada. Jalankan update Proses 2 dulu.")
    events = wb1.read_events(cfg)
    if start or end:
        events = [e for e in events
                  if (start is None or e["date"] >= start) and (end is None or e["date"] <= end)]
    txs = [t for t in store.read_log(store.load())
           if t.qty > 0 and (start is None or (t.date and t.date >= start))
           and (end is None or (t.date and t.date <= end))]
    results = []
    for v in stock_views(store):
        component = v.item.component
        kws = {component.casefold()} | {a.casefold() for a in aliases.get(component, [])}
        if component.upper() == "PLUG ASSIST":
            kws |= {"plugassist", "plug asist"}
        mentions = sum(1 for e in events
                       if any(kw in str(e.get("keterangan", "")).casefold() for kw in kws))
        spare_out = sum(t.qty for t in txs if _key(t.component) == _key(component))
        if mentions or spare_out:
            results.append({"component": component, "downtime_mentions": mentions,
                            "spare_out": spare_out})
    return sorted(results, key=lambda r: (-r["spare_out"], -r["downtime_mentions"]))
