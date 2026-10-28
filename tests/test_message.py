"""Test draft pesan WhatsApp: deterministik, tanpa kalimat template kosong."""
from __future__ import annotations

import datetime as dt

from conftest import base_cfg, make_event
from src import message, processes

TARGET = dt.date(2026, 10, 27)


def _cfg() -> dict:
    return processes.resolve(base_cfg(), "proses2")


def test_fmt_minutes_indonesian_separator():
    assert message.fmt_minutes(180) == "180"
    assert message.fmt_minutes(1440) == "1.440"
    assert message.fmt_minutes(1234567) == "1.234.567"


def test_join_list_two_and_three():
    assert message._join_list(["pisau"]) == "pisau"
    assert message._join_list(["pisau", "stacking"]) == "pisau dan stacking"
    assert message._join_list(["a", "b", "c"]) == "a, b, dan c"


def test_join_top_single_and_multi():
    rows = [{"name": "EXT 1", "minutes": 1440}]
    assert message._join_top(rows) == "EXT 1 = 1.440 menit"
    rows = [{"name": "A", "minutes": 10}, {"name": "B", "minutes": 5}]
    assert message._join_top(rows) == "A = 10 menit dan B = 5 menit"


def test_build_follows_report_format():
    events = [
        make_event(machine="VACUM 7", menit=100, keterangan="ganti pisau 1pcs"),
        make_event(machine="VACUM 7", menit=50, keterangan="perbaikan stackingan"),
        make_event(machine="WM", menit=80, keterangan="alarm axis drive error"),
        make_event(machine="TFM 1", menit=20, keterangan="bahan putus"),
    ]
    text = message.build(events, TARGET, _cfg())
    lines = text.strip().splitlines()

    assert lines[0] == "Update Pareto Proses 2 Pak @mr lukman cjm Di tanggal 27:"
    assert lines[2] == (
        "Downtime tertinggi ada di VACUM 7 = 150 menit, lanjut WM = 80 menit, "
        "dan TFM 1 = 20 menit."
    )
    assert lines[4] == "VACUM 7 banyak dari pisau dan stacking. WM karena alarm drives."
    assert lines[-3] == "Tolong dibantu follow up yang masih berulang."
    assert lines[-1] == "CC Pak Dio"


def test_build_single_machine_single_cause():
    events = [make_event(machine="EXT 1", menit=1440, keterangan="mpa error")]
    cfg = processes.resolve(base_cfg(), "proses1")
    text = message.build(events, TARGET, cfg)

    assert "Update Pareto Proses 1" in text
    assert "Downtime tertinggi ada di EXT 1 = 1.440 menit." in text
    assert "EXT 1 karena MPA error." in text


def test_build_other_label_uses_real_description():
    events = [make_event(machine="WM", menit=15, keterangan="perbaikan evakuator rak b error")]
    text = message.build(events, TARGET, _cfg())

    assert "perbaikan evakuator rak b error" in text
    assert "Other" not in text


def test_build_empty_date_returns_empty_string():
    events = [make_event(machine="WM", menit=10, keterangan="alarm")]
    assert message.build(events, dt.date(2026, 10, 28), _cfg()) == ""


def test_build_no_generic_ai_filler():
    events = [
        make_event(machine="TFM 1", menit=30, keterangan="tunggu bahan"),
        make_event(machine="TFM 2", menit=10, keterangan="stackingan"),
    ]
    text = message.build(events, TARGET, _cfg()).lower()
    for filler in ("monitoring durasi proses", "minta update status penanganan",
                   "evaluasi apabila downtime berulang", "diharapkan", "sebagai berikut"):
        assert filler not in text
