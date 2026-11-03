"""Gambar chart pareto (PNG) untuk draft WhatsApp — dari data nyata saja.

Proses 1 & 2: pareto downtime per mesin (menit) dari data workbook Tool 1.
Spare (Tool 2): pareto pemakaian komponen dari transaksi OUT nyata —
kalau belum ada transaksi, None (tanpa gambar, tanpa data karangan).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # tanpa layar — dipanggil dari CLI
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

ACCENT = "#00754A"  # hijau WhatsApp, senada


def _chart_dir(cfg: dict | None = None) -> Path:
    base = Path((cfg or {}).get("output", {}).get("output_dir", ROOT / "data" / "output"))
    path = Path(base) if Path(base).is_absolute() else (ROOT / base)
    d = path.parent / "wa_charts" if path.suffix else path / "wa_charts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _style(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)


def machine_chart(cfg: dict, target: dt.date, top_n: int = 8) -> Path | None:
    """Bar pareto downtime per mesin untuk satu tanggal. None kalau kosong."""
    from . import pareto, workbook

    if not workbook.find_current_workbook(cfg):
        return None
    events = [e for e in workbook.read_events(cfg) if e.get("date") == target]
    if not events:
        return None
    rows = pareto.pareto_machine(events)[:top_n]
    if not rows:
        return None

    names = [r["name"] for r in rows]
    minutes = [r["minutes"] for r in rows]
    cum = [r["cumulative"] * 100 for r in rows]

    fig, ax = plt.subplots(figsize=(8.0, 4.2), dpi=120)
    bars = ax.bar(range(len(rows)), minutes, color=ACCENT, width=0.62)
    for i, (bar, m) in enumerate(zip(bars, minutes)):
        ax.text(bar.get_x() + bar.get_width() / 2, m, f"{m}",
                ha="center", va="bottom", fontsize=9, color="#222222")
    ax2 = ax.twinx()
    ax2.plot(range(len(rows)), cum, color="#E07B00", marker="o", markersize=3.5,
             linewidth=1.4)
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("Kumulatif (%)", fontsize=9, color="#E07B00")
    ax2.spines["top"].set_visible(False)
    ax2.tick_params(axis="y", labelsize=8, colors="#E07B00")

    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Downtime (menit)", fontsize=9)
    _style(ax)
    label = cfg.get("process_label", "Proses")
    ax.set_title(f"Pareto Mesin Downtime - {label} - {target.strftime('%d %b %Y')}",
                 fontsize=11, fontweight="bold", loc="left", pad=10)
    fig.tight_layout()
    out = _chart_dir(cfg) / f"pareto_mesin_{cfg.get('process_key', 'proses')}_{target.isoformat()}.png"
    fig.savefig(out)
    plt.close(fig)
    return out


def spare_chart(cfg: dict, day: dt.date, top_n: int = 8) -> Path | None:
    """Bar pareto pemakaian spare (komponen) dari transaksi OUT nyata."""
    from src.tooling import service as spare_service
    from src.tooling.pareto import pareto as spare_pareto
    from src.tooling.repository import SpareStore

    store = SpareStore(cfg)
    txs = store.read_log(store.load())
    result = spare_pareto(txs, start=day, end=day, top=None)
    comp_rows, _total = result["component"]
    if result["n_tx"] == 0 or not comp_rows:
        return None  # belum ada transaksi nyata -> tanpa gambar

    rows = comp_rows[:top_n]
    names = [r["name"] for r in rows]
    qty = [r["qty"] for r in rows]

    fig, ax = plt.subplots(figsize=(8.0, 4.2), dpi=120)
    bars = ax.bar(range(len(rows)), qty, color=ACCENT, width=0.55)
    for bar, q in zip(bars, qty):
        ax.text(bar.get_x() + bar.get_width() / 2, q, str(q),
                ha="center", va="bottom", fontsize=9, color="#222222")
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Qty keluar (pcs)", fontsize=9)
    _style(ax)
    ax.set_title(f"Pareto Pemakaian Sparepart - Proses 2 - {day.strftime('%d %b %Y')}",
                 fontsize=11, fontweight="bold", loc="left", pad=10)
    fig.tight_layout()
    out = _chart_dir(cfg) / f"pareto_spare_{day.isoformat()}.png"
    fig.savefig(out)
    plt.close(fig)
    return out
