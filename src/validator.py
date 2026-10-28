"""Validasi workbook sebelum disimpan (mencegah workbook rusak ke LATEST)."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

ERROR_LITERALS = {"#REF!", "#DIV/0!", "#VALUE!", "#N/A", "#NAME?", "#NULL!", "#NUM!"}


def validate_workbook(wb, cfg: dict, target: dt.date | None = None, wpath=None) -> list[str]:
    """Semua pengecekan spesifikasi N. Return daftar error (kosong = lolos)."""
    from . import workbook as wbmod
    from .extractor import parse_date
    from .downtime import daily_totals

    errors: list[str] = []
    name = f"'{wpath.name}' " if wpath is not None else ""

    if wbmod.S_DETAIL not in wb.sheetnames:
        return [f"Sheet {wbmod.S_DETAIL} tidak ada."]

    # 1. Baca detil
    keys = [c[0] for c in wbmod.DETAIL_COLUMNS]
    ws = wb[wbmod.S_DETAIL]
    events = []
    for values in ws.iter_rows(min_row=wbmod.DATA_ROW, values_only=True):
        if all(v in (None, "") for v in values):
            continue
        rec = dict(zip(keys, values))
        d = parse_date(rec.get("date"))
        if d is None:
            errors.append("Tanggal tidak valid di DETAIL_DOWNTIME.")
            continue
        menit = rec.get("menit")
        if not isinstance(menit, (int, float)) or isinstance(menit, bool):
            errors.append(f"Downtime menit bukan angka: tanggal {d}, mesin {rec.get('machine_raw')}.")
            continue
        if menit < 0:
            errors.append(f"Downtime menit negatif: tanggal {d}, mesin {rec.get('machine_raw')}.")
            continue
        if rec.get("kategori") not in ("",) and len(str(rec.get("kategori"))) > 4:
            errors.append(f"Kategori tidak wajar: '{rec.get('kategori')}'.")
        events.append({"date": d, "menit": int(menit), "key": str(rec.get("event_key") or ""),
                       "machine_raw": rec.get("machine_raw"), "keterangan": rec.get("keterangan"),
                       "jam_mulai": rec.get("jam_mulai"), "jam_selesai": rec.get("jam_selesai"),
                       "kode_barang": rec.get("kode_barang")})
    if not events:
        errors.append("DETAIL_DOWNTIME kosong - tidak ada data untuk disimpan.")
        return errors

    # 2. Duplicate event (unique key: tgl+mesin+kode+jam+keterangan)
    seen = {}
    for e in events:
        k = e["key"] or f"{e['date']}|{e['machine_raw']}|{e['kode_barang']}|{e['jam_mulai']}|{e['jam_selesai']}|{str(e['keterangan']).lower()}"
        seen.setdefault(k, 0)
        seen[k] += 1
    dups = [k for k, c in seen.items() if c > 1]
    if dups:
        errors.append(f"Duplicate event ditemukan ({len(dups)} key): {dups[:3]}")

    # 3. Duplicate daily update (satu tanggal sekali di trend)
    if wbmod.S_TREND not in wb.sheetnames:
        errors.append("Sheet TREND_HARIAN tidak ada.")
    else:
        seen_dates = []
        for row in wb[wbmod.S_TREND].iter_rows(min_row=wbmod.DATA_ROW, values_only=True):
            d = parse_date(row[0]) if row else None
            if d:
                seen_dates.append(d)
        if len(seen_dates) != len(set(seen_dates)):
            errors.append("Duplicate daily update: ada tanggal muncul dua kali di TREND_HARIAN.")

    # 4. Total mesin = total downtime harian (REKAP vs TREND vs DETAIL)
    detail_totals = daily_totals([{"date": e["date"], "menit": e["menit"]} for e in events])
    if wbmod.S_REKAP in wb.sheetnames:
        rekap_totals = defaultdict(int)
        for row in wb[wbmod.S_REKAP].iter_rows(min_row=wbmod.DATA_ROW, values_only=True):
            d = parse_date(row[0]) if row else None
            if d:
                rekap_totals[d] += int(row[3] or 0)
        for d, tot in detail_totals.items():
            if rekap_totals.get(d) != tot["minutes"]:
                errors.append(f"Total mesin != total downtime harian ({d}): REKAP={rekap_totals.get(d)} vs DETAIL={tot['minutes']}")
    if wbmod.S_TREND in wb.sheetnames:
        for row in wb[wbmod.S_TREND].iter_rows(min_row=wbmod.DATA_ROW, values_only=True):
            d = parse_date(row[0]) if row else None
            tot = int(row[2] or 0) if row else 0
            if d and detail_totals.get(d, {}).get("minutes") != tot:
                errors.append(f"TREND_HARIAN tidak konsisten dengan detail ({d}): {tot} vs {detail_totals.get(d, {}).get('minutes')}")

    # 5. Pareto: contribution & cumulative
    for sheet_name, col_head in ((wbmod.S_PARETO_M, "mesin"), (wbmod.S_PARETO_I, "issue")):
        if sheet_name not in wb.sheetnames:
            errors.append(f"Sheet {sheet_name} tidak ada.")
            continue
        pws = wb[sheet_name]
        contrib = []
        rows = list(pws.iter_rows(min_row=wbmod.DATA_ROW, values_only=True))
        for row in rows:
            if row and row[0] not in (None, ""):
                if isinstance(row[3], (int, float)):
                    contrib.append(row[3])
        if contrib:
            total_contrib = sum(contrib)
            if not (0.999 <= total_contrib <= 1.001):
                errors.append(f"Pareto contribution total {sheet_name} = {total_contrib:.4f} (harus ~100%).")
            last_cum = rows[-1][4] if len(rows[-1]) > 4 else None
            if last_cum is None or abs((last_cum or 0) - 1.0) > 0.002:
                errors.append(f"Kumulatif terakhir {sheet_name} != 100% ({last_cum}).")

    # 6. Error literal (#REF! dll) di semua cache sel
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            for v in row:
                if isinstance(v, str) and v.strip().upper() in ERROR_LITERALS:
                    errors.append(f"Formula error '{v.strip()}' ada di sheet '{sheet.title}'.")

    # 7. Sheets wajib ada
    for req in (wbmod.S_RINGKASAN, wbmod.S_DETAIL, wbmod.S_REKAP, wbmod.S_PARETO_M,
                wbmod.S_PARETO_I, wbmod.S_TREND, wbmod.S_FOLLOW):
        if req not in wb.sheetnames:
            errors.append(f"Sheet wajib tidak ada: {req}")

    return dedup(errors)


def dedup(items: list[str]) -> list[str]:
    out = []
    for it in items:
        if it not in out:
            out.append(it)
    return out
