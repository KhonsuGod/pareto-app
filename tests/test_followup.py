"""Test follow-up row (threshold, idempotent, no placeholder)."""
from __future__ import annotations

import datetime as dt

from tests.conftest import make_event, base_cfg
from src import downtime as dow


def cfg_followup() -> dict:
    cfg = base_cfg()
    cfg["followup"] = {"priorities": {"P1": 120, "P2": 60}, "status": "OPEN",
                       "action_template": "Follow up alarm {machine} yang masih berulang.",
                       "include_monitor_row": True}
    return cfg


def test_threshold_and_priority():
    cfg = cfg_followup()
    evs = [
        # VACUM 8 = 205 menit -> P1
        make_event("2026-10-27", machine="VACUM 8", menit=200, keterangan="alarm produk ganda"),
        make_event("2026-10-27", machine="VACUM 8", menit=5, keterangan="alarm produk ganda"),
        # WM = 70 menit -> P2
        make_event("2026-10-27", machine="WM", menit=70, keterangan="tunggu bahan"),
        # TFM 2 = 50 menit -> tidak masuk follow-up
        make_event("2026-10-27", machine="TFM 2", menit=50, keterangan="tunggu bahan"),
    ]
    rows = dow.followup_rows(evs, dt.date(2026, 10, 27), cfg)
    by_prio = {r["machine"]: r for r in rows if r["priority"] != "MONITOR"}
    assert set(by_prio) == {"VACUM 8", "WM"}
    assert by_prio["VACUM 8"]["priority"] == "P1"
    assert by_prio["WM"]["priority"] == "P2"
    assert "205 menit downtime" in by_prio["VACUM 8"]["evidence"]
    # action bukan root cause teknis
    assert by_prio["VACUM 8"]["action"] == "Follow up alarm VACUM 8 yang masih berulang."
    # PIC kosong bila data tidak memuat owner
    for r in rows:
        assert r["pic"] == ""


def test_monitor_row_compare_with_prev_day():
    cfg = cfg_followup()
    evs = [
        make_event("2026-10-26", machine="TFM 1", menit=1000),
        make_event("2026-10-27", machine="VACUM 8", menit=500),
    ]
    rows = dow.followup_rows(evs, dt.date(2026, 10, 27), cfg)
    monitor = [r for r in rows if r["priority"] == "MONITOR"]
    assert monitor and "TURUN" in monitor[0]["evidence"]
    assert monitor[0]["date"] == dt.date(2026, 10, 27)


def test_no_monitor_row_if_disabled():
    cfg = cfg_followup()
    cfg["followup"]["include_monitor_row"] = False
    evs = [make_event("2026-10-27", machine="VACUM 8", menit=500)]
    rows = dow.followup_rows(evs, dt.date(2026, 10, 27), cfg)
    assert all(r["priority"] != "MONITOR" for r in rows)
