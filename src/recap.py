"""Rekap downtime bulanan dari workbook monitoring (Proses 1 & 2).

Prinsip (sama dengan modul lain):
- Excel yang menghitung: template berisi formula COUNTIF/SUMIF/kontribusi
  yang hidup; Python HANYA mengisi nilai (baris data, nama rank, tanggal).
- Template dipakai sebagai basis setiap build (tanpa state sisa), file
  output ditulis ulang penuh; kalau file bulan itu sudah ada -> backup.
- Layout tiap proses beda dan dideteksi dari template itu sendiri:
  baris header, jumlah kolom, range formula lama ($2320 / $165).
- Tanpa data karangan: bulan tanpa transaksi = rekap kosong (valid).
"""
from __future__ import annotations

import calendar
import copy
import datetime as dt
import re
import shutil
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import openpyxl

ROOT = Path(__file__).resolve().parent.parent

_NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_PK = "http://schemas.openxmlformats.org/package/2006/relationships"
_RT_DRAWING = _NS_R + "/drawing"
_CT_DRAWING = "application/vnd.openxmlformats-officedocument.drawing+xml"
_CT_CHART = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"

MONTHS_FULL = ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI",
               "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"]
MONTHS_ABBR = ["JAN", "FEB", "MAR", "APR", "MEI", "JUN", "JUL",
               "AGU", "SEP", "OKT", "NOV", "DES"]


class RecapError(RuntimeError):
    """Error rekap bulanan dengan pesan yang bisa ditindaklanjuti."""


# --------------------------------------------------------------------------- #
# parsing bulan & label
# --------------------------------------------------------------------------- #
def parse_month(text: str | None) -> tuple[int, int]:
    """'2026-11' / '2026-11-05' -> (2026, 11). None -> bulan berjalan."""
    if not text:
        today = dt.date.today()
        return today.year, today.month
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", text.strip())
    if not m:
        raise RecapError(f"Format bulan salah: '{text}' (gunakan YYYY-MM).")
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        raise RecapError(f"Bulan tidak valid: {month}.")
    return year, month


def month_label(year: int, month: int) -> str:
    return f"{MONTHS_FULL[month - 1]} {year}"


# --------------------------------------------------------------------------- #
# template & layout (dideteksi dari file, bukan di-hardcode)
# --------------------------------------------------------------------------- #
def template_path(cfg: dict) -> Path:
    recap = cfg.get("recap") or {}
    key = cfg.get("process_key") or "proses2"
    path = (recap.get("templates") or {}).get(key) or ""
    if not path:
        raise RecapError(
            f"Template rekap untuk '{key}' belum diisi di config.yaml (recap.templates).")
    p = Path(path)
    return p if p.is_absolute() else (ROOT / p)


def _header_row(ws, keyword: str = "tanggal") -> int:
    """Baris header: cari sel kolom A yang PERSIS keyword (case-insesitif).

    Fallback substring hanya bila tak ada yang persis — supaya baris catatan
    semacam r3 'PERIODE ... | TANGGAL TANPA RECORD ...' tidak salah kira header.
    """
    fallback = None
    for r in range(1, 15):
        v = ws.cell(r, 1).value
        if v is None:
            continue
        s = str(v).strip().casefold()
        if s == keyword:
            return r
        if fallback is None and keyword in s:
            fallback = r
    if fallback is not None:
        return fallback
    raise RecapError(f"Baris header '{keyword}' tidak ditemukan di sheet {ws.title}.")


def _filled_header_cols(ws, hdr: int) -> int:
    n = 0
    while ws.cell(hdr, n + 1).value not in (None, ""):
        n += 1
    return n


def _last_data_row(ws, first: int, ncols: int) -> int:
    last = first - 1
    for r in range(first, ws.max_row + 1):
        if any(ws.cell(r, c).value not in (None, "") for c in range(1, ncols + 1)):
            last = r
    return last


def _last_rank_row(ws, first: int) -> int:
    last = first - 1
    for r in range(first, ws.max_row + 1):
        if isinstance(ws.cell(r, 1).value, (int, float)):
            last = r
    return last


def _grow_ok(ws, first: int) -> bool:
    """True bila tidak ada konten di bawah baris rank terakhir (boleh klon baris)."""
    last = _last_rank_row(ws, first)
    for r in range(last + 1, ws.max_row + 1):
        for c in range(1, 9):
            if ws.cell(r, c).value not in (None, ""):
                return False
    return True


def detect_layout(wb) -> dict:
    data = wb["DATA DOWNTIME"]
    hdr = _header_row(data)
    heads = [str(data.cell(hdr, c).value or "").strip().casefold()
             for c in range(1, data.max_column + 1)]
    ncols = _filled_header_cols(data, hdr)
    is_extrusion = not any("kode bj" in h for h in heads)

    layout = {
        "data_first": hdr + 1,
        "data_cols": ncols,
        "data_old_end": _last_data_row(data, hdr + 1, ncols),
        "trend_first": _header_row(wb["TREND HARIAN"]) + 1,
        "pareto_first": _header_row(wb["PARETO MESIN"], "rank") + 1,
        "issue_first": _header_row(wb["PARETO ISSUE"], "rank") + 1,
        "extrusion": is_extrusion,
        "total_row": None,
        "breakdown_first": None,
        "breakdown_rows": 0,
    }
    if is_extrusion:
        pm = wb["PARETO MESIN"]
        last_rank = _last_rank_row(pm, layout["pareto_first"])
        for r in range(last_rank + 1, pm.max_row + 1):
            if str(pm.cell(r, 2).value or "").strip().upper() == "TOTAL":
                layout["total_row"] = r
                break
        for r in range((layout["total_row"] or 0) + 1, pm.max_row + 1):
            if str(pm.cell(r, 1).value or "").strip().casefold() == "mesin":
                layout["breakdown_first"] = r + 1
                break
        if layout["breakdown_first"]:
            r = layout["breakdown_first"]
            while r <= pm.max_row:
                v = pm.cell(r, 1).value
                if v in (None, "") or str(v).strip().upper().startswith("TOTAL"):
                    break
                r += 1
            layout["breakdown_rows"] = r - layout["breakdown_first"]
    layout["machine_grow"] = (not is_extrusion) and _grow_ok(
        wb["PARETO MESIN"], layout["pareto_first"])
    layout["issue_grow"] = _grow_ok(wb["PARETO ISSUE"], layout["issue_first"])
    return layout


# --------------------------------------------------------------------------- #
# event -> baris data
# --------------------------------------------------------------------------- #
def month_events(cfg: dict, year: int, month: int) -> list[dict]:
    """Event dari workbook proses: filter bulan target, dedupe, urut tanggal."""
    from . import workbook as wb_mod

    events = wb_mod.read_events(cfg)
    seen: set[str] = set()
    out = []
    for e in events:
        key = str(e.get("event_key") or (e["date"], e.get("machine_raw"), e.get("jam_mulai")))
        if key in seen:
            continue
        seen.add(key)
        if e["date"].year == year and e["date"].month == month:
            out.append(e)
    out.sort(key=lambda e: (e["date"], e.get("machine_raw") or "",
                            e.get("jam_mulai") or dt.time()))
    return out


def _durasi(e: dict) -> str:
    kat = str(e.get("kategori") or "").strip().upper()
    return "LT" if kat.startswith("LT") else "REGULER"


def _data_row(layout: dict, e: dict) -> list:
    if layout["extrusion"]:
        return [dt.datetime.combine(e["date"], dt.time()),
                e.get("machine_raw") or "", e.get("jam_mulai"),
                e.get("jam_selesai"), int(e["menit"]),
                e.get("keterangan") or "", e.get("kategori") or "",
                e.get("issue_label") or "", _durasi(e)]
    return [dt.datetime.combine(e["date"], dt.time()),
            e.get("machine_raw") or "", e.get("kode_barang") or "",
            e.get("nama_produk") or "", e.get("jam_mulai"),
            e.get("jam_selesai"), int(e["menit"]),
            e.get("keterangan") or "", e.get("kategori") or "",
            e.get("issue_label") or ""]
    # (dipotong ke jumlah kolom layout saat penulisan)


# --------------------------------------------------------------------------- #
# helper tulis
# --------------------------------------------------------------------------- #
def _clear_rows(ws, first: int, last: int, ncols: int) -> None:
    """Kosongkan nilai (style & column width tetap)."""
    for r in range(first, last + 1):
        for c in range(1, ncols + 1):
            ws.cell(r, c).value = None


def _clone_row(ws, src: int, dst: int, ncols: int) -> None:
    """Salin style + formula baris rank (formula di-translasi ke baris baru)."""
    from openpyxl.formula.translate import Translator

    for c in range(1, ncols + 1):
        s = ws.cell(src, c)
        d = ws.cell(dst, c)
        d._style = copy.copy(s._style)
        if isinstance(s.value, str) and s.value.startswith("="):
            d.value = Translator(s.value, origin=s.coordinate).translate_formula(
                d.coordinate)


def _extend_ranges(wb, old_end: int, new_end: int) -> int:
    """Perpanjang akhir range data '...!$B$2:$B$2320' bila data melewatinya."""
    if new_end <= old_end:
        return 0
    pat = re.compile(r"(\$?[A-Z]{1,3}\$?)(\d+):(\$?[A-Z]{1,3}\$?)(\d+)")
    count = 0

    def _sub(m: re.Match) -> str:
        nonlocal count
        if int(m.group(4)) == old_end:
            count += 1
            return f"{m.group(1)}{m.group(2)}:{m.group(3)}{new_end}"
        return m.group(0)

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if not isinstance(v, str) or not v.startswith("="):
                    continue
                nv = pat.sub(_sub, v)
                if nv != v:
                    cell.value = nv
    return count


def _title_zone(sheet: str, layout: dict) -> int | None:
    """Batas baris zona judul per sheet (judul selalu di ATAS header konten).

    None = scan seluruh sheet (SUMMARY BULANAN; formula di-skip).
    """
    if sheet == "SUMMARY BULANAN":
        return None
    if sheet == "DATA DOWNTIME":
        return layout["data_first"] - 1
    if sheet == "TREND HARIAN":
        return layout["trend_first"] - 1
    if sheet == "PARETO MESIN":
        return layout["pareto_first"] - 1
    if sheet == "PARETO ISSUE":
        return layout["issue_first"] - 1
    return 6


def _title_cells(wb, layout: dict) -> list[tuple["openpyxl.worksheet.worksheet.Worksheet", int, int]]:
    """Cari sel judul: string berisi nama bulan/rentang '01–31', bukan formula."""
    full_pat = "|".join(MONTHS_FULL)
    abbr_pat = "|".join(MONTHS_ABBR)
    out = []
    for ws in wb.worksheets:
        limit = _title_zone(ws.title, layout)
        if limit is not None and limit <= 0:
            continue  # judul menempel header (mis. DATA DOWNTIME p2) -> tak ada judul
        max_row = ws.max_row if limit is None else min(limit, ws.max_row)
        pat = re.compile(rf"\b({full_pat}|{abbr_pat})\b", re.IGNORECASE)
        for r in range(1, max_row + 1):
            for c in range(1, 12):
                v = ws.cell(r, c).value
                if not isinstance(v, str) or v.startswith("="):
                    continue
                if pat.search(v) or re.search(r"01[\u2013-]\d{1,2}", v):
                    out.append((ws, r, c))
    return out


def retitle(wb, layout: dict, year: int, month: int) -> None:
    """Ganti nama bulan/tahun/rentang hari di sel judul template."""
    full = MONTHS_FULL[month - 1]
    abbr = MONTHS_ABBR[month - 1]
    ndays = calendar.monthrange(year, month)[1]
    full_pat = "|".join(MONTHS_FULL)
    abbr_pat = "|".join(MONTHS_ABBR)
    for ws, r, c in _title_cells(wb, layout):
        v = ws.cell(r, c).value
        s = re.sub(rf"\b({full_pat})\b", full, v, flags=re.IGNORECASE)
        s = re.sub(rf"\b({abbr_pat})\b", abbr, s)
        s = re.sub(r"\b(20\d{2})\b", str(year), s)
        s = re.sub(r"(?<=01\u2013)\d{1,2}", str(ndays), s)
        s = re.sub(r"(?<=01-)\d{1,2}", str(ndays), s)
        if s != v:
            ws.cell(r, c).value = s


# --------------------------------------------------------------------------- #
# nama rank (pareto mesin/issue) — aturan sama dgn pareto Tool 1
# --------------------------------------------------------------------------- #
def names_in_order(events: list[dict], field: str) -> list[str]:
    agg: dict[str, int] = {}
    for e in events:
        name = str(e.get(field) or "-").strip() or "-"
        agg[name] = agg.get(name, 0) + int(e["menit"])
    rows = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
    return [name for name, _m in rows]


def write_rank_names(ws, first: int, names: list[str], grow: bool = True) -> list[str]:
    """Tulis nama rank di kolom B sesuai urutan pareto.

    grow=True  : nama > slot template -> baris baru diklon (style + formula).
    grow=False : hanya slot template yang diisi; sisanya dikembalikan
                 sebagai overflow (dipakai untuk warning, baris di bawah
                 rank tidak boleh digeser karena ada TOTAL/breakdown).

    Baris rank yang tak terpakai: nama di B dikosongkan, nomor rank & formula
    template dipertahankan (hasil pareto otomatis 0 lewat formula Excel).
    """
    last_tpl_rank = _last_rank_row(ws, first)
    n_tpl = max(0, last_tpl_rank - first + 1)
    n = len(names)
    overflow: list[str] = []

    nkinds = n_tpl
    if n > n_tpl:
        if grow:
            for i in range(n - n_tpl):
                _clone_row(ws, last_tpl_rank, last_tpl_rank + 1 + i, 8)
            nkinds = n
        else:
            overflow = names[n_tpl:]
            nkinds = n_tpl

    for i in range(nkinds):
        r = first + i
        # nomor rank: baris template sudah berisi; baris klon perlu diisi
        if last_tpl_rank < r:
            ws.cell(r, 1).value = i + 1
        ws.cell(r, 2).value = names[i] if i < n else None
    return overflow


def _write_trend(wb, layout: dict, year: int, month: int) -> None:
    ws = wb["TREND HARIAN"]
    first = layout["trend_first"]
    ndays = calendar.monthrange(year, month)[1]
    n_tpl = 0
    for r in range(first, ws.max_row + 1):
        if ws.cell(r, 1).value not in (None, ""):
            n_tpl = r - first + 1
    for i in range(n_tpl):
        r = first + i
        if i < ndays:
            ws.cell(r, 1).value = dt.datetime(year, month, i + 1)
        else:
            _clear_rows(ws, r, r, 6)


# --------------------------------------------------------------------------- #
# restore chart/drawing dari template (openpyxl membuangnya saat load->save)
# --------------------------------------------------------------------------- #
def _read(name: str, src) -> bytes:
    if isinstance(src, dict):
        return src[name]
    return src.read(name)


def _sheet_map(reader) -> dict[str, str]:
    """nama sheet -> part path (mis. xl/worksheets/sheet2.xml)."""
    zroot = ET.fromstring(_read("xl/workbook.xml", reader))
    zrels = ET.fromstring(_read("xl/_rels/workbook.xml.rels", reader))
    targets = {r.get("Id"): r.get("Target") for r in zrels}
    out: dict[str, str] = {}
    for sh in zroot.find(f"{{{_NS_SHEET}}}sheets"):
        t = (targets.get(sh.get(f"{{{_NS_R}}}id")) or "").lstrip("/")
        if not t.startswith("xl/"):
            t = "xl/" + t
        out[sh.get("name")] = t
    return out


def _norm(from_dir: str, target: str) -> str:
    """Resolve target relatif rel (../drawings/x.xml) jadi part path."""
    t = target.lstrip("/")
    if t.startswith("xl/"):
        return t
    parts = (from_dir + "/" + t).split("/")
    out: list[str] = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
            continue
        if p not in (".", ""):
            out.append(p)
    return "/".join(out)


def _sheet_drawings(reader, sheets: dict[str, str]) -> dict[str, list[str]]:
    """nama sheet -> daftar part drawing yang direferensikan sheet tsb."""
    res: dict[str, list[str]] = {}
    for name, sheet_file in sheets.items():
        base = sheet_file.rsplit("/", 1)
        relp = f"{base[0]}/_rels/{base[1]}.rels"
        try:
            zrels = ET.fromstring(_read(relp, reader))
        except (KeyError, ET.ParseError):
            continue
        parts = []
        for rel in zrels:
            if (rel.get("Type") or "").endswith("/drawing"):
                parts.append(_norm(base[0], rel.get("Target") or ""))
        if parts:
            res[name] = parts
    return res


def _drawing_family(reader, drawing_part: str) -> list[str]:
    """Part drawing + semua part terkait (rels + chart)."""
    base = drawing_part.rsplit("/", 1)
    relp = f"{base[0]}/_rels/{base[1]}.rels"
    family = [drawing_part]
    try:
        zrels = ET.fromstring(_read(relp, reader))
    except (KeyError, ET.ParseError):
        return family
    for rel in zrels:
        t = _norm(base[0], rel.get("Target") or "")
        if t not in family:
            family.append(t)
    family.append(relp)
    return family


def restore_drawings(tpl_path: Path, out_path: Path) -> int:
    """Salin balik chart/drawing dari template ke file hasil openpyxl.

    openpyxl membuang semua drawing/chart saat load->save, padahal template
    rekap berisi grafik pareto buatan user. Fungsi ini menyalin part
    drawing/chart apa adanya lalu menautkannya kembali ke sheet yang sama.
    Return: jumlah sheet yang mendapat chart-nya kembali; 0 = tanpa chart.
    """
    with zipfile.ZipFile(tpl_path) as zt:
        t_sheets = _sheet_map(zt)
        t_drawings = _sheet_drawings(zt, t_sheets)
        if not t_drawings:
            return 0  # template tanpa chart -> tidak ada yang direstorasi

        with zipfile.ZipFile(out_path) as zo:
            names = zo.namelist()
            data = {n: zo.read(n) for n in names}

        o_sheets = _sheet_map(data)
        used = set(data)
        additions: list[tuple[str, bytes]] = []   # part baru utk output
        overrides: list[tuple[str, str]] = []     # (part, content-type)
        ct = data["[Content_Types].xml"].decode("utf-8")

        for sheet_name, tparts in t_drawings.items():
            out_sheet = o_sheets.get(sheet_name)
            if not out_sheet:
                continue
            # semua part anggota keluarga drawing (drawing + rels + chart)
            family: list[str] = []
            for tp in tparts:
                for member in _drawing_family(zt, tp):
                    if member not in family:
                        family.append(member)
            # nama unik bila bentrok (output openpyxl biasanya kosong)
            rename: dict[str, str] = {}
            for p in family:
                np = p
                while np in used:
                    np = np.replace("drawing", "recap_drawing", 1)
                    if np == p:
                        np = p.replace("chart", "recap_chart", 1)
                rename[p] = np
                used.add(np)
            for p in family:
                np = rename[p]
                additions.append((np, _read(p, zt)))
                base_name = np.rsplit("/", 1)[-1]
                if "drawing" in base_name:
                    overrides.append((f"/{np}", _CT_DRAWING))
                elif "/charts/" in np:
                    overrides.append((f"/{np}", _CT_CHART))
            # rels sheet output (tambah Relationship baru)
            obase = out_sheet.rsplit("/", 1)
            relp = f"{obase[0]}/_rels/{obase[1]}.rels"
            dr_part = rename[tparts[0]]
            target = "../" + "/".join(dr_part.split("/")[1:])
            rid = "rIdRecapDraw"
            rel_xml = (f'<Relationship Type="{_RT_DRAWING}" '
                       f'Target="{target}" Id="{rid}"/>')
            if relp in data:
                rels = data[relp].decode("utf-8").replace(
                    "</Relationships>", rel_xml + "</Relationships>")
            else:
                rels = ('<?xml version="1.0" encoding="UTF-8" '
                        'standalone="yes"?>\n'
                        f'<Relationships xmlns="{_NS_PK}">{rel_xml}'
                        "</Relationships>")
            data[relp] = rels.encode("utf-8")
            additions.append((relp, data[relp]))
            # sisipkan elemen <drawing> di sheet xml (r:id terdaftar via rels)
            sx = data[out_sheet].decode("utf-8")
            if "<drawing " not in sx:
                ins = f'<drawing r:id="{rid}" xmlns:r="{_NS_R}"/>'
                sx = sx.replace("</worksheet>", ins + "</worksheet>")
                data[out_sheet] = sx.encode("utf-8")

        overrides_ct = ""
        for part, ctype in overrides:
            if f'PartName="{part}"' not in ct:
                overrides_ct += (f'<Override PartName="{part}" '
                                 f'ContentType="{ctype}"/>')
        if overrides_ct:
            ct = ct.replace("</Types>", overrides_ct + "</Types>")
        data["[Content_Types].xml"] = ct.encode("utf-8")

        # tulis ulang zip: data lama + part baru
        tmp = out_path.with_name(out_path.name + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zn:
            for name, payload in data.items():
                zn.writestr(name, payload)
        tmp.replace(out_path)

        return len(t_drawings)


# --------------------------------------------------------------------------- #
# build utama
# --------------------------------------------------------------------------- #
def _outputs_has_drawings(path: Path) -> bool:
    """Cek cepat: file hasil masih menyimpan drawing/chart atau tidak."""
    with zipfile.ZipFile(path) as z:
        return any("/drawing" in n or "/chart" in n for n in z.namelist())


def build(cfg: dict, month_text: str | None = None) -> dict:
    """Buat file rekap bulanan. Return info untuk tampilan CLI."""
    year, month = parse_month(month_text)
    label = str(cfg.get("process_label", "?")).upper()
    tpl = template_path(cfg)
    if not tpl.exists():
        raise RecapError(f"Template rekap tidak ditemukan: {tpl}")

    events = month_events(cfg, year, month)
    ndays = calendar.monthrange(year, month)[1]
    warnings: list[str] = []

    out_dir = Path(cfg["output"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"REKAP DOWNTIME BULANAN {label} - {month_label(year, month)}.xlsx"
    if out.exists():
        bdir = out_dir / "backups"
        bdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, bdir / f"{out.stem}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}{out.suffix}")

    wb = openpyxl.load_workbook(tpl)  # formula tetap hidup
    layout = detect_layout(wb)
    data = wb["DATA DOWNTIME"]

    first = layout["data_first"]
    old_end = layout["data_old_end"]
    _clear_rows(data, first, max(old_end, first - 1), layout["data_cols"])
    row = first
    for e in events:
        for c, v in enumerate(_data_row(layout, e)[: layout["data_cols"]], start=1):
            data.cell(row, c).value = v
        row += 1
    last_data = row - 1
    extended = _extend_ranges(wb, old_end, max(old_end, last_data + 100))

    retitle(wb, layout, year, month)

    machines = names_in_order(events, "machine_raw")
    issues = names_in_order(events, "issue_label")
    overflow_m = write_rank_names(wb["PARETO MESIN"], layout["pareto_first"],
                                  machines, grow=layout["machine_grow"])
    overflow_i = write_rank_names(wb["PARETO ISSUE"], layout["issue_first"],
                                  issues, grow=layout["issue_grow"])
    if overflow_m:
        warnings.append(f"{len(overflow_m)} mesin tidak muat di rank PARETO MESIN: "
                        f"{', '.join(overflow_m[:6])}")
    if overflow_i:
        warnings.append(f"{len(overflow_i)} issue tidak muat di rank PARETO ISSUE: "
                        f"{', '.join(overflow_i[:6])}")

    # breakdown REGULER vs LT (proses 1): nama mesin ikut urutan rank
    if layout["breakdown_first"]:
        pm = wb["PARETO MESIN"]
        for i in range(layout["breakdown_rows"]):
            name = machines[i] if i < len(machines) else None
            pm.cell(layout["breakdown_first"] + i, 1).value = name if name else None

    _write_trend(wb, layout, year, month)

    errors = validate_recap(wb, layout, events, year, month)
    if errors:
        raise RecapError("Rekap tidak valid, file tidak disimpan:\n" +
                         "\n".join(f"  - {e}" for e in errors))

    wb.save(out)
    charts = 0
    if not _outputs_has_drawings(out):
        # fallback: openpyxl kadang membuang drawing (versi/fitur tertentu) —
        # salin balik chart dari template bila hilang.
        try:
            charts = restore_drawings(tpl, out)
        except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
            warnings.append(f"Chart template tidak direstorasi: {exc}")
    check = openpyxl.load_workbook(out)
    missing = [s for s in ("SUMMARY BULANAN", "PARETO MESIN", "PARETO ISSUE",
                           "TREND HARIAN", "DATA DOWNTIME") if s not in check.sheetnames]
    check.close()
    if missing:
        raise RecapError(f"Hasil simpan tidak lengkap (sheet hilang: {missing}).")

    covered = sorted({e["date"].day for e in events})
    if not events:
        warnings.append(f"Tidak ada event downtime untuk {month_label(year, month)} — "
                        "rekap dibuat kosong.")
    return {
        "path": str(out),
        "label": label,
        "month": month_label(year, month),
        "n_events": len(events),
        "covered": covered,
        "n_days": ndays,
        "n_machines": len(machines),
        "n_issues": len(issues),
        "extended": extended,
        "charts": charts,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# validasi (murni baca)
# --------------------------------------------------------------------------- #
def validate_recap(wb, layout: dict, events: list[dict], year: int, month: int) -> list[str]:
    errors: list[str] = []
    data = wb["DATA DOWNTIME"]
    first = layout["data_first"]
    n = 0
    for r in range(first, data.max_row + 1):
        v = data.cell(r, 1).value
        if v in (None, ""):
            continue
        d = v.date() if isinstance(v, dt.datetime) else v
        if not isinstance(d, dt.date) or (d.year, d.month) != (year, month):
            errors.append(f"DATA DOWNTIME r{r}: tanggal di luar bulan target ({v}).")
        n += 1
    if n != len(events):
        errors.append(f"Jumlah baris data ({n}) != jumlah event ({len(events)}).")

    for sheet in ("PARETO MESIN", "PARETO ISSUE", "SUMMARY BULANAN", "TREND HARIAN"):
        if sheet not in wb.sheetnames:
            errors.append(f"Sheet hilang: {sheet}")
            continue
        for row in wb[sheet].iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and "#REF" in v:
                    errors.append(f"{sheet} {cell.coordinate}: formula rusak (#REF).")

    pms = wb["PARETO MESIN"]
    listed = {str(pms.cell(r, 2).value or "").strip()
              for r in range(layout["pareto_first"],
                             _last_rank_row(pms, layout["pareto_first"]) + 1)}
    missing_m = [m for m in (names_in_order(events, "machine_raw")) if m not in listed]
    if missing_m and layout.get("machine_grow"):
        # baris tidak growable sudah dilaporkan sbg warning di build()
        errors.append("Mesin tanpa baris rank PARETO MESIN: "
                      + ", ".join(missing_m[:6]))
    pis = wb["PARETO ISSUE"]
    listed_i = {str(pis.cell(r, 2).value or "").strip()
                for r in range(layout["issue_first"],
                               _last_rank_row(pis, layout["issue_first"]) + 1)}
    missing_i = [m for m in (names_in_order(events, "issue_label")) if m not in listed_i]
    if missing_i and layout.get("issue_grow"):
        errors.append("Issue tanpa baris rank PARETO ISSUE: " + ", ".join(missing_i[:6]))
    return errors
