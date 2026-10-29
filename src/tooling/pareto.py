"""Pareto pemakaian spare + dashboard Excel (formula hidup, tanpa data karangan)."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from openpyxl.styles import Font

from .repository import LOG_FIRST, _key, _norm
from .models import OutTx

DASH_SHEET = "DASHBOARD SPARE"


def _in_range(tx: OutTx, start: dt.date | None, end: dt.date | None) -> bool:
    if tx.date is None or tx.qty <= 0:
        return False
    if start and tx.date < start:
        return False
    if end and tx.date > end:
        return False
    return True


def _rank(counter: dict[str, int], freq: dict[str, int], top: int | None = 5):
    rows = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    total = sum(counter.values()) or 1
    out, cum = [], 0
    for name, qty in rows[: top] if top else rows:
        cum += qty
        out.append({
            "name": name, "qty": qty, "freq": freq.get(name, 0),
            "pct": qty / total, "cum_pct": cum / total,
        })
    return out, total


def pareto(txs: list[OutTx], start: dt.date | None = None,
           end: dt.date | None = None, top: int | None = 5) -> dict:
    """Pareto dari transaksi OUT nyata per komponen / family / mesin."""
    sel = [t for t in txs if _in_range(t, start, end)]
    comp: dict[str, int] = defaultdict(int)
    fam: dict[str, int] = defaultdict(int)
    mesin: dict[str, int] = defaultdict(int)
    comp_f: dict[str, int] = defaultdict(int)
    fam_f: dict[str, int] = defaultdict(int)
    mes_f: dict[str, int] = defaultdict(int)
    for t in sel:
        comp[t.component or "-"] += t.qty
        comp_f[t.component or "-"] += 1
        fam[t.family or "-"] += t.qty
        fam_f[t.family or "-"] += 1
        if t.mesin:
            mesin[t.mesin] += t.qty
            mes_f[t.mesin] += 1
    return {
        "range": (start, end),
        "n_tx": len(sel),
        "total_qty": sum(t.qty for t in sel),
        "component": _rank(comp, comp_f, top),
        "family": _rank(fam, fam_f, top),
        "machine": _rank(mesin, mes_f, top),
    }


# --------------------------------------------------------------------------- #
# DASHBOARD SPARE — dibuat begitu ada transaksi nyata
# --------------------------------------------------------------------------- #
def build_dashboard(wb, items, alarms, build_time: dt.datetime) -> None:
    """Bikin/perbarui DASHBOARD SPARE. Metrik pakai formula Excel agar hidup."""
    if DASH_SHEET not in wb.sheetnames:
        ws = wb.create_sheet(DASH_SHEET)
        ws.column_dimensions["A"].width = 34
        for col in "BCDEFGH":
            ws.column_dimensions[col].width = 14
    ws = wb[DASH_SHEET]
    for row in ws.iter_rows():
        for cell in row:
            cell.value = None

    last = _formula_last_row(wb)
    log = f"'LOG PENGELUARAN'!$H${LOG_FIRST}:$H${last}"
    dates = f"'LOG PENGELUARAN'!$A${LOG_FIRST}:$A${last}"
    fams = f"'LOG PENGELUARAN'!$D${LOG_FIRST}:$D${last}"
    comps = f"'LOG PENGELUARAN'!$G${LOG_FIRST}:$G${last}"

    ws["A1"] = "DASHBOARD SPARE TOOLING | PROSES 2"
    ws["A1"].font = Font(bold=True)
    st = wb["STOCK SPARE"]
    n_fam = len({i.family for i in items})
    n_comp = len({i.component for i in items})
    meta = [
        ("Total tooling family", n_fam),
        ("Total spare komponen", n_comp),
        ("Qty keluar hari ini", f"=SUMIFS({log},{dates},TODAY())"),
        ("Jumlah transaksi OUT", f"=COUNTIF({dates},\">0\")"),
        ("Stock alarm (saat simpan)", sum(1 for a in alarms if a.status.value in ("OUT", "LOW", "DEFICIT"))),
        ("Diperbarui", build_time.strftime("%Y-%m-%d %H:%M")),
    ]
    for i, (label, value) in enumerate(meta, start=3):
        ws.cell(i, 1).value = label
        ws.cell(i, 2).value = value

    # ---- helper pareto komponen & family (formula SUMIFS full-range) ----
    comp_names = sorted({i.component for i in items})
    fam_names = sorted({i.family for i in items})
    ws.cell(1, 4).value = "KOMPONEN (data STOCK SPARE)"
    ws.cell(1, 5).value = "QTY KELUAR"
    ws.cell(1, 6).value = "FAMILY"
    ws.cell(1, 7).value = "QTY KELUAR"
    for c in range(4, 8):
        ws.cell(1, c).font = Font(bold=True)
    for i, name in enumerate(comp_names, start=2):
        ws.cell(i, 4).value = name
        ws.cell(i, 5).value = f'=SUMIFS({log},{comps},D{i})'
    for i, name in enumerate(fam_names, start=2):
        ws.cell(i, 6).value = name
        ws.cell(i, 7).value = f'=SUMIFS({log},{fams},F{i})'
    n_comp_rows = len(comp_names)
    top = 10
    top_end = 1 + min(top, n_comp_rows)
    ws["I1"] = "Top komponen"
    ws["I2"] = f"=INDEX(D2:D{1 + n_comp_rows},MATCH(MAX(E2:E{1 + n_comp_rows}),E2:E{1 + n_comp_rows},0))"
    ws["I3"] = "Trend harian (14 hari terakhir)"

    # trend 14 hari sliding
    ws.cell(4, 9).value = "TGL"
    ws.cell(4, 10).value = "QTY"
    for i in range(14):
        r = 5 + i
        ws.cell(r, 9).value = f"=TODAY()-{13 - i}"
        ws.cell(r, 10).value = f"=SUMIFS({log},{dates},I{r})"

    if n_comp_rows >= 1:
        _add_charts(ws, top_end, n_fam_names=len(fam_names))
    # trend helper di kolom I/J baris 5..18
    from openpyxl.chart import LineChart, Reference
    trend = LineChart()
    trend.title = "Pemakaian spare 14 hari"
    data = Reference(ws, min_col=10, min_row=4, max_row=18)
    cats = Reference(ws, min_col=9, min_row=5, max_row=18)
    trend.add_data(data, titles_from_data=True)
    trend.set_categories(cats)
    trend.height, trend.width = 7.5, 16
    ws.add_chart(trend, "A20")


def _add_charts(ws, comp_top_end: int, n_fam_names: int) -> None:
    from openpyxl.chart import BarChart, Reference
    pareto_c = BarChart()
    pareto_c.title = "Pareto komponen (top 10)"
    pareto_c.add_data(Reference(ws, min_col=5, min_row=1, max_row=comp_top_end), titles_from_data=True)
    pareto_c.set_categories(Reference(ws, min_col=4, min_row=2, max_row=comp_top_end))
    pareto_c.height, pareto_c.width = 7.5, 16
    ws.add_chart(pareto_c, "H20")


def _formula_last_row(wb) -> int:
    import re
    st = wb["STOCK SPARE"]
    v = st.cell(5, 6).value or ""
    m = re.search(r"\$H\$5:\$H\$(\d+)", str(v))
    return int(m.group(1)) if m else LOG_FIRST + 650
