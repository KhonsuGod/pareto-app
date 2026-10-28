"""Kelola workbook monitoring (template, data sheet, charts, save/backup)."""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import openpyxl
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import extractor, downtime as dow, pareto as pareto_mod
from .extractor import clean_text

S_RINGKASAN = "RINGKASAN"
S_DETAIL = "DETAIL_DOWNTIME"
S_REKAP = "REKAP_MESIN"
S_PARETO_M = "PARETO_MESIN"
S_PARETO_I = "PARETO_ISSUE"
S_TREND = "TREND_HARIAN"
S_PLUG = "PLUG_ASSIST"
S_TUNGGU = "TUNGGU_BAHAN"
S_FOLLOW = "FOLLOW_UP"

BANNER_ROW = 1
HEAD_ROW = 2
DATA_ROW = 3

PCT_FMT = "0.0%"
DATE_FMT = "yyyy-mm-dd"
TIME_FMT = "hh:mm"

BANNER_FONT = Font(bold=True, size=13, color="FFFFFFFF")
BANNER_FILL = PatternFill("solid", fgColor="FF1F4E79")
HEAD_FONT = Font(bold=True, color="FFFFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="FF2F74B5")
BORDER = Border(bottom=Side("thin", color="FFBFBFBF"))

KATS_DEFAULT = {"A": "MTC", "B": "PRD", "C": "TS", "D": "BAHAN", "E": "QC/RND", "F": "PPIC", "G": "WS"}

DETAIL_COLUMNS = [
    ("date", "Tanggal", 11, DATE_FMT),
    ("machine_raw", "Mesin", 11, None),
    ("machine_group", "Machine Group", 14, None),
    ("kode_barang", "Kode Barang", 16, None),
    ("nama_produk", "Nama Produk", 38, None),
    ("jam_mulai", "Jam Mulai", 10, TIME_FMT),
    ("jam_selesai", "Jam Selesai", 11, TIME_FMT),
    ("menit", "Downtime (menit)", 15, "0"),
    ("keterangan", "Keterangan", 46, None),
    ("kategori", "Kategori", 9, None),
    ("issue_group", "Issue Group", 18, None),
    ("issue_label", "Issue Label", 26, None),
    ("event_key", "Event Key", 34, None),
]
PARETO_MACHINE_HEAD = [("name", "Mesin"), ("event_count", "Frekuensi"), ("minutes", "Downtime (menit)"),
                       ("contribution", "Kontribusi"), ("cumulative", "Kumulatif")]
PARETO_ISSUE_HEAD = [("name", "Issue Group"), ("event_count", "Frekuensi"), ("minutes", "Downtime (menit)"),
                     ("contribution", "Kontribusi"), ("cumulative", "Kumulatif")]
TREND_HEAD = [("date", "Tanggal"), ("events", "Frekuensi"), ("minutes", "Downtime (menit)")]
REKAP_BASE = [("date", "Tanggal"), ("machine", "Mesin"), ("events", "Frekuensi"),
              ("minutes", "Downtime (menit)")]
REKAP_BASE_KEYS = ["date", "machine", "events", "minutes"]

FOLLOW_HEAD = [("priority", "Priority"), ("date", "Tanggal"), ("machine", "Mesin"), ("issue", "Issue"),
               ("evidence", "Evidence"), ("pic", "PIC"), ("action", "Action"), ("status", "Status"),
               ("update", "Update"), ("next_check", "Next Check")]


def _kategori_keys(cfg: dict) -> list[str]:
    return list((cfg or {}).get("kategori_labels") or KATS_DEFAULT)


def _kategori_head(cfg: dict) -> list[tuple[str, str]]:
    kats = (cfg or {}).get("kategori_labels") or KATS_DEFAULT
    return [(f"k_{k}", f"{k} ({name})") for k, name in kats.items()]


def _issue_label(cfg: dict, key: str, default: str) -> str:
    groups = ((cfg.get("issue_mapping", {}) or {}).get("groups", {}) or {})
    return (groups.get(key, {}) or {}).get("label", default)


# --------------------------------------------------------------------------- #
# Penulisan dasar
# --------------------------------------------------------------------------- #
def _clear_rows(ws, start: int) -> None:
    if ws.max_row >= start:
        ws.delete_rows(start, ws.max_row - start + 1)


def _set_widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _banner(ws, title: str, ncols: int, subtitle: str = "") -> None:
    cell = ws.cell(row=BANNER_ROW, column=1, value=title)
    cell.font = BANNER_FONT
    cell.alignment = Alignment(vertical="center")
    for c in range(1, ncols + 1):
        ws.cell(row=BANNER_ROW, column=c).fill = BANNER_FILL
    if subtitle:
        s = ws.cell(row=BANNER_ROW, column=ncols, value=subtitle)
        s.font = Font(italic=True, size=9, color="FFE6EEF7")
        s.alignment = Alignment(horizontal="right", vertical="center")


def _header(ws, cols: list[tuple[str, str]]) -> None:
    for i, (_key, label) in enumerate(cols, start=1):
        cell = ws.cell(row=HEAD_ROW, column=i, value=label)
        cell.font = HEAD_FONT
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = ws.cell(row=DATA_ROW, column=1).coordinate


def _write_table(ws, cols: list[tuple[str, str]], rows: list[dict], banner: str,
                 fmt_map: dict[str, str] | None = None) -> None:
    _clear_rows(ws, BANNER_ROW)
    _banner(ws, banner, len(cols), f"Update: {_now_stamp()}")
    _header(ws, cols)
    for i, row in enumerate(rows, start=DATA_ROW):
        for j, (key, label) in enumerate(cols, start=1):
            cell = ws.cell(row=i, column=j, value=row.get(key))
            cell.border = BORDER
            fmt = (fmt_map or {}).get(label)
            if fmt:
                cell.number_format = fmt


def _ensure_sheet(wb, title: str, ncols: int, widths: list[int]):
    if title in wb.sheetnames:
        return wb[title]
    ws = wb.create_sheet(title=title)
    _set_widths(ws, widths[:ncols])
    return ws


def _now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _stamp_file() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


# --------------------------------------------------------------------------- #
# Template
# --------------------------------------------------------------------------- #
def template_path(cfg: dict) -> Path:
    return Path(cfg["output"]["template"])


def ensure_template(cfg: dict, force: bool = False) -> Path | None:
    """Buat workbook template (header saja, tanpa data dummy) bila belum ada."""
    path = template_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return None
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, ncols, widths in _sheet_layouts(cfg):
        ws = wb.create_sheet(title)
        _set_widths(ws, widths[:ncols])
    wb.save(path)
    return path


def _optional(cfg: dict, name: str) -> bool:
    return bool(((cfg.get("workbook_optional") or {}).get(name, True)))


def _sheet_layouts(cfg: dict):
    kats = _kategori_keys(cfg)
    detail_w = [c[2] for c in DETAIL_COLUMNS]
    rekap_w = [11, 12, 10, 16] + [11] * len(kats)
    pareto_w = [16, 11, 17, 12, 11, 12]
    trend_w = [13, 11, 17, 12]
    follow_w = [10, 11, 12, 30, 46, 12, 42, 10, 18, 12]
    plug_w = [11, 11, 16, 38, 10, 11, 8, 46, 9, 4, 14, 11]
    ringkasan_w = [30, 36, 17, 16, 18, 18]
    layouts = [
        (S_DETAIL, len(DETAIL_COLUMNS), detail_w),
        (S_REKAP, 4 + len(kats), rekap_w),
        (S_PARETO_M, 5, pareto_w),
        (S_PARETO_I, 5, pareto_w),
        (S_TREND, 3, trend_w),
    ]
    if _optional(cfg, "plug_assist"):
        layouts.append((S_PLUG, 9, plug_w))
    if _optional(cfg, "tunggu_bahan"):
        layouts.append((S_TUNGGU, 9, plug_w))
    layouts += [
        (S_FOLLOW, len(FOLLOW_HEAD), follow_w),
        (S_RINGKASAN, 6, ringkasan_w),
    ]
    return layouts


# --------------------------------------------------------------------------- #
# Buka / baca workbook current
# --------------------------------------------------------------------------- #
def find_current_workbook(cfg: dict) -> Path | None:
    out_dir = Path(cfg["output"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = out_dir / cfg["output"].get("latest_name", "Monitoring_Proses2_LATEST.xlsx")
    if latest.exists():
        return latest
    dated = sorted(out_dir.glob("Monitoring_Proses2_*-??-??.xlsx"))
    return dated[-1] if dated else None


def load_or_create(cfg: dict):
    """Workbook current bila ada, selain itu dari template / sheet bersih."""
    path = find_current_workbook(cfg)
    if path:
        return openpyxl.load_workbook(path)
    tpl = template_path(cfg)
    if tpl.exists():
        return openpyxl.load_workbook(tpl)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, ncols, widths in _sheet_layouts(cfg):
        ws = wb.create_sheet(title)
        _set_widths(ws, widths[:ncols])
    return wb


def read_processed_dates(cfg: dict) -> set:
    path = find_current_workbook(cfg)
    if not path:
        return set()
    wb = openpyxl.load_workbook(path, read_only=True)
    if S_DETAIL not in wb.sheetnames:
        return set()
    ws = wb[S_DETAIL]
    col = [c[0] for c in DETAIL_COLUMNS].index("date") + 1
    dates: set = set()
    for row in ws.iter_rows(min_row=DATA_ROW, min_col=col, max_col=col, values_only=True):
        parsed = extractor.parse_date(row[0])
        if parsed:
            dates.add(parsed)
    return dates


def read_events(cfg: dict) -> list[dict]:
    """Baca ulang event dari workbook current (idempotent upsert)."""
    path = find_current_workbook(cfg)
    if not path:
        return []
    wb = openpyxl.load_workbook(path, read_only=True)
    if S_DETAIL not in wb.sheetnames:
        return []
    ws = wb[S_DETAIL]
    keys = [c[0] for c in DETAIL_COLUMNS]
    group_mode = (cfg.get("machine_grouping", {}) or {}).get("mode", "strip_dot")
    out = []
    for n, values in enumerate(ws.iter_rows(min_row=DATA_ROW, values_only=True), start=DATA_ROW):
        if all(v in (None, "") for v in values):
            continue
        rec = dict(zip(keys, values))
        d = extractor.parse_date(rec.get("date"))
        if d is None:
            continue
        menit = rec.get("menit")
        try:
            menit = int(menit)
        except (TypeError, ValueError):
            continue
        ev = {
            "date": d,
            "machine_raw": clean_text(rec.get("machine_raw")),
            "machine": clean_text(rec.get("machine_raw")),
            "machine_group": extractor.machine_group(rec.get("machine_raw") or "", group_mode),
            "kode_barang": clean_text(rec.get("kode_barang")),
            "nama_produk": clean_text(rec.get("nama_produk")),
            "jam_mulai": extractor.parse_time(rec.get("jam_mulai")),
            "jam_selesai": extractor.parse_time(rec.get("jam_selesai")),
            "menit": menit,
            "keterangan": rec.get("keterangan") or "",
            "kategori": clean_text(rec.get("kategori")),
            "issue_label": rec.get("issue_label") or "",
            "row": n,
        }
        ev["issue_group"] = _key_from_label(cfg, ev["issue_label"])
        ev["event_key"] = extractor.event_key(ev)
        out.append(ev)
    return out


def _key_from_label(cfg: dict, label: str) -> str:
    groups = cfg.get("issue_mapping", {}).get("groups", {}) or {}
    for k, v in groups.items():
        if (v or {}).get("label") == label:
            return k
    return "other"


def read_followup_rows(cfg: dict, exclude_date=None) -> list[dict]:
    path = find_current_workbook(cfg)
    if not path:
        return []
    wb = openpyxl.load_workbook(path, read_only=True)
    if S_FOLLOW not in wb.sheetnames:
        return []
    ws = wb[S_FOLLOW]
    keys = [k for k, _ in FOLLOW_HEAD]
    rows = []
    for values in ws.iter_rows(min_row=DATA_ROW, values_only=True):
        if all(v in (None, "") for v in values):
            continue
        rec = dict(zip(keys, values))
        d = extractor.parse_date(rec.get("date"))
        if d is None or (exclude_date is not None and d == exclude_date):
            continue
        rec["date"] = d
        rows.append(rec)
    return rows


# --------------------------------------------------------------------------- #
# Penulisan sheet
# --------------------------------------------------------------------------- #
def detail_cols() -> list[tuple[str, str]]:
    return [(k, h) for k, h, _w, _f in DETAIL_COLUMNS]


def ordered_events(events: list[dict]) -> list[dict]:
    return sorted(events, key=lambda e: (e["date"], e["jam_mulai"] or dt.time(0, 0), e["machine_raw"]))


def build_sheets(wb, cfg: dict, merged: list[dict], target, pareto_mesin: list[dict],
                 pareto_issue: list[dict], trend: list[dict], rekap: list[dict],
                 summary: dict, followup: list[dict]) -> None:
    # DETAIL_DOWNTIME - semua tanggal processed; baris tanggal target sudah di-replace upstream
    ws = _ensure_sheet(wb, S_DETAIL, len(DETAIL_COLUMNS), [c[2] for c in DETAIL_COLUMNS])
    _write_table(ws, detail_cols(), ordered_events(merged),
                 "DETAIL DOWNTIME (semua tanggal processed)",
                 fmt_map={c[1]: c[3] for c in DETAIL_COLUMNS})

    # REKAP_MESIN
    kats = _kategori_head(cfg)
    rekap_cols = REKAP_BASE + kats
    rekap_rows = []
    for r in rekap:
        row = {k: r.get(k) for k in REKAP_BASE_KEYS}
        for (kk, _h) in kats:
            row[kk] = r.get(kk, 0)
        rekap_rows.append(row)
    ws_rekap = _ensure_sheet(wb, S_REKAP, len(rekap_cols), [11, 12, 10, 16] + [12] * len(kats))
    _write_table(ws_rekap, rekap_cols, rekap_rows, "REKAP DOWNTIME PER MESIN (semua tanggal processed)",
                 fmt_map={"Tanggal": DATE_FMT, "Downtime (menit)": "0"})

    # PARETO_MESIN / PARETO_ISSUE (tanggal target)
    ws_pm = _ensure_sheet(wb, S_PARETO_M, 5, [16, 11, 17, 12, 11, 12])
    _write_table(ws_pm, PARETO_MACHINE_HEAD, pareto_mesin, "PARETO DOWNTIME MESIN",
                 fmt_map={"Kontribusi": PCT_FMT, "Kumulatif": PCT_FMT})
    ws_pi = _ensure_sheet(wb, S_PARETO_I, 5, [26, 11, 17, 12, 11, 12])
    _write_table(ws_pi, PARETO_ISSUE_HEAD, pareto_issue, "PARETO DOWNTIME ISSUE",
                 fmt_map={"Kontribusi": PCT_FMT, "Kumulatif": PCT_FMT})

    # TREND_HARIAN
    ws_tr = _ensure_sheet(wb, S_TREND, 3, [13, 11, 17, 12])
    _write_table(ws_tr, TREND_HEAD, trend, "TREND DOWNTIME HARIAN", fmt_map={"Tanggal": DATE_FMT})

    # PLUG_ASSIST / TUNGGU_BAHAN (bisa dimatikan per proses)
    if _optional(cfg, "plug_assist") or _optional(cfg, "tunggu_bahan"):
        plug_label = _issue_label(cfg, "plug_assist", "Plug Assist / Produk Nempel")
        tunggu_label = _issue_label(cfg, "tunggu_bahan", "Tunggu Bahan")
        plug_cols = [("date", "Tanggal"), ("machine_raw", "Mesin"), ("kode_barang", "Kode Barang"),
                     ("nama_produk", "Produk"), ("jam_mulai", "Mulai"), ("jam_selesai", "Selesai"),
                     ("menit", "Menit"), ("keterangan", "Keterangan"), ("kategori", "Kategori")]
        fmt_map = {"Tanggal": DATE_FMT, "Mulai": TIME_FMT, "Selesai": TIME_FMT, "Menit": "0"}
        if _optional(cfg, "plug_assist"):
            plug_rows = [e for e in merged if e.get("issue_label") == plug_label]
            ws_plug = _ensure_sheet(wb, S_PLUG, len(plug_cols), [11, 11, 16, 38, 10, 11, 8, 46, 9])
            _write_table(ws_plug, plug_cols, plug_rows, f"{plug_label} — detail", fmt_map=fmt_map)
        if _optional(cfg, "tunggu_bahan"):
            tunggu_rows = [e for e in merged if e.get("issue_label") == tunggu_label]
            ws_tunggu = _ensure_sheet(wb, S_TUNGGU, len(plug_cols), [11, 11, 16, 38, 10, 11, 8, 46, 9])
            _write_table(ws_tunggu, plug_cols, tunggu_rows, f"{tunggu_label} — detail", fmt_map=fmt_map)

    # FOLLOW_UP (old rows di luar tanggal target dipertahankan)
    old = read_followup_rows(cfg, exclude_date=target)
    rows = old + list(followup)
    prio = dow.PRIORITY_ORDER
    rows.sort(key=lambda r: (r["date"], prio.get(r.get("priority"), 5), str(r.get("machine", ""))))
    ws_f = _ensure_sheet(wb, S_FOLLOW, len(FOLLOW_HEAD), [10, 11, 12, 30, 46, 12, 42, 10, 18, 12])
    _write_table(ws_f, FOLLOW_HEAD, rows, "FOLLOW UP / ALARM PRODUKSI", fmt_map={"Tanggal": DATE_FMT})

    # RINGKASAN
    _write_ringkasan(wb, cfg, merged, summary, pareto_mesin, pareto_issue)


def _write_ringkasan(wb, cfg: dict, merged: list[dict], summary: dict,
                     pareto_mesin: list[dict], pareto_issue: list[dict]) -> None:
    ws = wb[S_RINGKASAN] if S_RINGKASAN in wb.sheetnames else wb.create_sheet(S_RINGKASAN)
    _clear_rows(ws, 1)
    kats = cfg.get("kategori_labels") or KATS_DEFAULT
    kat = summary["top_kategori"]
    kat_disp = f"{kat} ({kats[kat]})" if kat in kats else (kat or "-")

    blocks: list[tuple[str, object, object, bool]] = [
        ("DAILY DOWNTIME PROSES 2 / BOLANG", None, None, True),
        ("Periode Data", f"{summary['period_start']} s/d {summary['period_end']}", None, False),
        ("Tanggal Latest", summary["date"], None, False),
        ("Total Downtime (menit)", summary["total_minutes"], None, False),
        ("Total Event", summary["total_events"], None, False),
        ("Mesin Dominan", summary["top_machine"], summary["top_machine_minutes"], False),
        ("Issue Dominan", summary["top_issue"], summary["top_issue_minutes"], False),
        ("Kategori Dominan", kat_disp, summary["top_kategori_minutes"], False),
        ("Workbook update", _now_stamp(), None, False),
    ]
    r = 1
    for label, b, c, is_title in blocks:
        cell = ws.cell(row=r, column=1, value=label)
        if is_title:
            cell.font = BANNER_FONT
            for cc in range(1, 7):
                ws.cell(row=r, column=cc).fill = BANNER_FILL
            r += 2
            continue
        cell.font = Font(bold=True)
        if b is not None:
            bcell = ws.cell(row=r, column=2, value=b)
            if hasattr(b, "date") or isinstance(b, dt.date):
                bcell.number_format = DATE_FMT
        if c is not None:
            ws.cell(row=r, column=3, value=c)
        r += 1

    def section(title: str, table: list[dict], cols: list[tuple[str, str]]):
        nonlocal r
        r += 1
        ws.cell(row=r, column=1, value=title).font = Font(bold=True, size=11)
        r += 1
        for i, (_k, name) in enumerate(cols, start=1):
            cell = ws.cell(row=r, column=i, value=name)
            cell.font = HEAD_FONT
            cell.fill = HEAD_FILL
        r += 1
        for row in table:
            for i, (k, _n) in enumerate(cols, start=1):
                cell = ws.cell(row=r, column=i, value=row.get(k))
                cell.border = BORDER
                if k in ("contribution", "cumulative"):
                    cell.number_format = PCT_FMT
                elif k == "date":
                    cell.number_format = DATE_FMT
            r += 1

    section(f"TOP 5 MESIN ({dow.short_date(summary['date'])})",
            pareto_mod.top_rows(pareto_mesin, int((cfg.get("ringkasan", {}) or {}).get("top_n", 5))),
            PARETO_MACHINE_HEAD)
    section(f"TOP 5 ISSUE ({dow.short_date(summary['date'])})",
            pareto_mod.top_rows(pareto_issue, int((cfg.get("ringkasan", {}) or {}).get("top_n", 5))),
            PARETO_ISSUE_HEAD)
    fokus = dow.fokus_series(merged, cfg)
    fokus_cols = [("date", "Tanggal"), ("minutes", "Total Downtime (menit)"), ("events", "Frekuensi"),
                  ("tunggu_bahan", "Tunggu Bahan (menit)"), ("plug_assist", "Plug Assist (menit)"),
                  ("kategori_c", "Kategori C (menit)")]
    section(f"FOKUS {len(fokus)} HARI TERAKHIR", fokus, fokus_cols)
    _set_widths(ws, [30, 36, 17, 16, 18, 18])


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def apply_charts(wb, cfg: dict) -> None:
    """Chart dari data worksheet (tidak ada angka hardcode)."""
    for title, name, anchor in ((S_PARETO_M, "Mesin", "G3"), (S_PARETO_I, "Issue Group", "G3")):
        if title not in wb.sheetnames:
            continue
        ws = wb[title]
        ws._charts.clear()
        n = ws.max_row - (DATA_ROW - 1)
        if n < 1 or ws.max_column < 5:
            continue
        bar = BarChart()
        bar.type = "col"
        bar.style = 10
        bar.add_data(Reference(ws, min_col=3, min_row=HEAD_ROW, max_row=HEAD_ROW + n), titles_from_data=True)
        bar.set_categories(Reference(ws, min_col=1, min_row=DATA_ROW, max_row=HEAD_ROW + n))
        bar.title = f"Pareto Downtime ({name}) - Menit"
        bar.y_axis.title = "Downtime (menit)"
        bar.x_axis.title = name
        bar.height = 9.5
        bar.width = 23

        line = LineChart()
        line.add_data(Reference(ws, min_col=5, min_row=HEAD_ROW, max_row=HEAD_ROW + n), titles_from_data=True)
        line.y_axis.axId = 200
        line.y_axis.title = "Kumulatif"
        line.y_axis.majorGridlines = None
        line.y_axis.numFmt = "0%"
        bar.y_axis.crosses = "max"
        bar += line
        ws.add_chart(bar, anchor)

    if S_TREND in wb.sheetnames:
        ws_tr = wb[S_TREND]
        ws_tr._charts.clear()
        n = ws_tr.max_row - (DATA_ROW - 1)
        if n >= 1:
            line = LineChart()
            line.style = 12
            line.add_data(Reference(ws_tr, min_col=3, min_row=HEAD_ROW, max_row=HEAD_ROW + n), titles_from_data=True)
            line.set_categories(Reference(ws_tr, min_col=1, min_row=DATA_ROW, max_row=HEAD_ROW + n))
            line.title = "Trend Downtime Harian (menit)"
            line.y_axis.title = "Downtime (menit)"
            line.x_axis.title = "Tanggal"
            line.height = 9
            line.width = 24
            ws_tr.add_chart(line, "E3")


def finalize(wb, cfg: dict) -> None:
    if S_RINGKASAN in wb.sheetnames:
        wb.active = wb.sheetnames.index(S_RINGKASAN)


# --------------------------------------------------------------------------- #
# Save + backup
# --------------------------------------------------------------------------- #
def save_workbook(wb, cfg: dict, target) -> tuple[Path, Path]:
    out_dir = Path(cfg["output"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(cfg["output"].get("backup_dir") or out_dir / "backups")
    latest = out_dir / cfg["output"].get("latest_name", "Monitoring_Proses2_LATEST.xlsx")
    dated = out_dir / cfg["output"].get("dated_name", "Monitoring_Proses2_{date}.xlsx").format(date=target.isoformat())

    if latest.exists():                     # backup LATEST sebelum diubah
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest, backup_dir / f"Monitoring_Proses2_backup_{_stamp_file()}.xlsx")
        _rotate_backups(backup_dir, int(cfg["output"].get("backup_keep", 10)))

    wb.save(dated)
    wb.save(latest)
    return dated, latest


def _rotate_backups(backup_dir: Path, keep: int) -> None:
    files = sorted(backup_dir.glob("Monitoring_Proses2_backup_*.xlsx"))
    for f in files[:-keep] if keep > 0 else []:
        try:
            f.unlink()
        except OSError:
            pass
