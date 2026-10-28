"""Test kalkulasi downtime & Pareto (deterministic)."""
from __future__ import annotations

import datetime as dt

from tests.conftest import make_event, base_cfg
from src import downtime as dow
from src import pareto


def test_daily_totals():
    evs = [
        make_event("2026-10-27", machine="TFM 1", menit=10),
        make_event("2026-10-27", machine="WM", menit=5),
        make_event("2026-10-26", machine="TFM 1", menit=7),
    ]
    totals = dow.daily_totals(evs)
    assert totals[dt.date(2026, 10, 27)]["minutes"] == 15
    assert totals[dt.date(2026, 10, 27)]["events"] == 2
    assert totals[dt.date(2026, 10, 26)]["minutes"] == 7


def test_trend_rows_sorted_unique_dates():
    evs = [
        make_event("2026-10-27", menit=10),
        make_event("2026-10-26", menit=20),
        make_event("2026-10-27", menit=5),
    ]
    trend = dow.trend_rows(evs)
    assert [t["date"] for t in trend] == [dt.date(2026, 10, 26), dt.date(2026, 10, 27)]
    assert trend[-1]["minutes"] == 15 and trend[-1]["events"] == 2


def test_pareto_machine_order_and_math():
    evs = [
        make_event("2026-10-27", machine="VACUM 7", menit=200),
        make_event("2026-10-27", machine="VACUM 7", menit=50),
        make_event("2026-10-27", machine="WM", menit=100),
        make_event("2026-10-27", machine="WM", menit=50),
        make_event("2026-10-27", machine="TFM 2", menit=50),
    ]
    rows = pareto.pareto_machine(evs)
    assert rows[0]["name"] == "VACUM 7" and rows[0]["minutes"] == 250
    assert rows[1]["name"] == "WM" and rows[1]["minutes"] == 150
    # tie 50 & 50: nama asc
    assert rows[2]["name"] == "TFM 2" and rows[2]["minutes"] == 50
    assert abs(rows[0]["contribution"] - 250 / 450) < 1e-9   # 250 / 450
    assert abs(rows[0]["cumulative"] - 250 / 450) < 1e-5     # kumulatif dibulatkan 6 desimal
    assert abs(rows[-1]["cumulative"] - 1.0) < 1e-9
    assert abs(sum(r["contribution"] for r in rows) - 1.0) < 1e-6


def test_pareto_issue_uses_issue_label():
    evs = [
        make_event("2026-10-27", keterangan="tunggu bahan", menit=80),
        make_event("2026-10-27", keterangan="produk nempel di plugassit", menit=20),
    ]
    rows = pareto.pareto_issue(evs)
    assert rows[0]["name"] == "Tunggu Bahan"
    assert rows[0]["event_count"] == 1
    assert abs(rows[0]["cumulative"] - 0.8) < 1e-9


def test_rekap_machine_rows_structure():
    cfg = base_cfg()
    evs = [
        make_event("2026-10-27", machine="TFM 1", menit=30, kategori="B"),
        make_event("2026-10-27", machine="TFM 1", menit=10, kategori="A"),
        make_event("2026-10-27", machine="WM", menit=20, kategori="C"),
        make_event("2026-10-26", machine="WM", menit=5, kategori="D"),
    ]
    rows = dow.rekap_machine_rows(evs, cfg)
    day27 = [r for r in rows if r["date"] == dt.date(2026, 10, 27)]
    assert {(r["machine"], r["minutes"]) for r in day27} == {("TFM 1", 40), ("WM", 20)}
    tfm = next(r for r in day27 if r["machine"] == "TFM 1")
    assert tfm["k_A"] == 10 and tfm["k_B"] == 30
    # total mesin per tanggal == total harian
    assert sum(r["minutes"] for r in day27) == dow.daily_totals(evs)[dt.date(2026, 10, 27)]["minutes"]


def test_summary_dominan():
    evs = [
        make_event("2026-10-27", machine="VACUM 8", menit=205, keterangan="alarm produk ganda", kategori="B"),
        make_event("2026-10-27", machine="VACUM 8", menit=5, keterangan="alarm produk ganda", kategori="B"),
        make_event("2026-10-27", machine="WM", menit=50, keterangan="tunggu bahan", kategori="B"),
        make_event("2026-10-26", machine="TFM 1", menit=999, keterangan="tunggu bahan", kategori="B"),
    ]
    s = dow.summary(evs, dt.date(2026, 10, 27))
    assert s["total_minutes"] == 260
    assert s["total_events"] == 3
    assert s["top_machine"] == "VACUM 8" and s["top_machine_minutes"] == 210
    assert s["top_issue"] == "Alarm Mesin" and s["top_issue_minutes"] == 210
    assert s["top_kategori"] == "B"
