"""Validasi workbook spare (dedicated, tidak menyentuh validator Tool 1)."""
from __future__ import annotations

import datetime as dt

from .repository import LEDGER_SHEET, LOG_FIRST, TXN_ID_HEADER, _key, _norm

HEAD_LOG = ("Tanggal", "Jam", "Mesin Tujuan", "Tooling Family", "Kode BJ",
            "Nama Produk", "Sparepart Keluar", "Qty Keluar", "Keterangan / Alasan", "PIC / Checker")
HEAD_STOCK = ("No.", "Tooling Family", "Sparepart / Component", "Stock Awal",
              "Keluar Hari Ini", "Stock Aktual", "Lokasi", "Catatan", "kondisi sparepart")


def validate_spare_workbook(wb) -> list[str]:
    """Kembalikan daftar error; kosong = valid. Murni baca, tidak menulis."""
    errors: list[str] = []
    required = ("MASTER TOOLING", "STOCK SPARE", "LOG PENGELUARAN")
    for name in required:
        if name not in wb.sheetnames:
            errors.append(f"Sheet wajib hilang: {name}")
            return errors

    st = wb["STOCK SPARE"]
    head = [_norm(st.cell(4, c).value) for c in range(1, 10)]
    if [h.upper() for h in head] != [h.upper() for h in HEAD_STOCK]:
        errors.append(f"Header STOCK SPARE berubah: {head}")

    items = {}
    for r in range(5, st.max_row + 1):
        fam, comp = _norm(st.cell(r, 2).value), _norm(st.cell(r, 3).value)
        if not fam or not comp:
            if st.cell(r, 1).value is not None:
                errors.append(f"STOCK SPARE r{r}: family/komponen kosong.")
            continue
        awal = st.cell(r, 4).value
        if awal not in (None, "") and (not isinstance(awal, (int, float)) or isinstance(awal, bool)
                                       or awal < 0):
            errors.append(f"STOCK SPARE r{r}: Stock Awal tidak valid ({awal!r}).")
        if isinstance(awal, float) and awal != int(awal):
            errors.append(f"STOCK SPARE r{r}: Stock Awal harus bilangan bulat ({awal}).")
        items[(_key(fam), _key(comp))] = r

    # formula kolom E/F masih utuh?
    for r in range(5, st.max_row + 1):
        if not _norm(st.cell(r, 2).value):
            continue
        for col, tag in ((5, "E"), (6, "F")):
            v = st.cell(r, col).value
            if not (isinstance(v, str) and v.startswith("=IF(")):
                errors.append(f"STOCK SPARE {tag}{r}: formula stock hilang/tidak dikenal.")
            elif isinstance(v, str) and ("#REF" in v or "#VALUE" in v or "#DIV/0" in v):
                errors.append(f"STOCK SPARE {tag}{r}: error formula {tag}{r}.")

    log = wb["LOG PENGELUARAN"]
    if _norm(log.cell(4, 11).value) != TXN_ID_HEADER:
        errors.append(f"Kolom K header LOG harus '{TXN_ID_HEADER}'.")

    seen_ids: dict[str, int] = {}
    n_tx = 0
    for r in range(LOG_FIRST, log.max_row + 1):
        vals = [log.cell(r, c).value for c in range(1, 11)]
        if all(v in (None, "") for v in vals):
            continue
        n_tx += 1
        tanggal, qty = vals[0], vals[7]
        family, comp, kode_bj = _norm(vals[3]), _norm(vals[6]), _norm(vals[4])
        if not isinstance(tanggal, (dt.date, dt.datetime)):
            errors.append(f"LOG r{r}: Tanggal tidak valid ({tanggal!r}).")
        if isinstance(tanggal, dt.datetime):
            tanggal = tanggal.date()
        if not isinstance(qty, (int, float)) or isinstance(qty, bool) or int(qty) <= 0:
            errors.append(f"LOG r{r}: Qty Keluar harus angka positif ({qty!r}).")
        if (_key(family), _key(comp)) not in items:
            errors.append(f"LOG r{r}: family/komponen '{family}'/'{comp}' tidak ada di STOCK SPARE.")
        if kode_bj and not any(_norm(row.kode_bj).upper() == kode_bj.upper()
                               for row in _routing(wb)):
            errors.append(f"LOG r{r}: Kode BJ '{kode_bj}' tidak ada di MASTER TOOLING.")
        # routing: BJ harus dipetakan ke family yang sama di MASTER TOOLING
        if kode_bj and family:
            fams = {row.family.casefold() for row in _routing(wb)
                    if _norm(row.kode_bj).upper() == kode_bj.upper()}
            if fams and family.casefold() not in fams:
                errors.append(f"LOG r{r}: '{kode_bj}' bukan routing '{family}' "
                              f"(family valid: {sorted(fams)}).")
        tid = _norm(log.cell(r, 11).value)
        if not tid:
            errors.append(f"LOG r{r}: ID Transaksi kosong.")
        elif tid in seen_ids:
            errors.append(f"LOG r{r}: ID Transaksi duplikat '{tid}' (juga di r{seen_ids[tid]}).")
        else:
            seen_ids[tid] = r
        # jangkauan formula: baris di luar cakupan SUMIFS tidak akan terhitung
        if not (LOG_FIRST <= r <= _formula_last(st)):
            errors.append(f"LOG r{r}: di luar jangkauan formula stock (perlu perpanjang range).")

    if LEDGER_SHEET in wb.sheetnames:
        led = wb[LEDGER_SHEET]
        for r in range(2, led.max_row + 1):
            if led.cell(r, 1).value in (None, ""):
                continue
            for col in (6, 7, 8, 9):
                v = led.cell(r, col).value
                if v not in (None, "") and not isinstance(v, (int, float)):
                    errors.append(f"LEDGER r{r}: kolom {col} harus angka/kosong ({v!r}).")

    if n_tx == 0 and not errors:
        pass  # log kosong sah — stock semua UNKNOWN sampai opname
    return errors


def _routing(wb):
    ws = wb["MASTER TOOLING"]
    for r in range(5, ws.max_row + 1):
        family = _norm(ws.cell(r, 3).value)
        if family:
            yield type("R", (), {"kode_bj": _norm(ws.cell(r, 4).value), "family": family})()


def _formula_last(st) -> int:
    """Batas akhir SUMIFS dari formula kolom F baris 5."""
    import re
    v = st.cell(5, 6).value or ""
    m = re.search(r"\$H\$5:\$H\$(\d+)", str(v))
    return int(m.group(1)) if m else 0
