"""Test gambar chart pareto PNG (matplotlib Agg) + resolusi grup WA."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from src import wa_chart  # noqa: E402
from src import wa_send  # noqa: E402

DAY = dt.date(2026, 10, 30)


def _cfg_png(tmp_path):
    return {
        "process_key": "proses2",
        "process_label": "Proses 2",
        "output": {"output_dir": str(tmp_path / "out")},
        "whatsapp": {"groups": {"proses1": "Extruder Bolang",
                                "proses2": "Setter & t.s & produksi"}},
    }


def test_machine_chart_png_from_real_shape_events(tmp_path, monkeypatch):
    from src import workbook as wb_mod
    cfg = _cfg_png(tmp_path)
    events = [
        {"date": DAY, "machine": "VACUM 7", "machine_raw": "VACUM 7", "menit": 180,
         "issue_label": "pisau", "description_raw": "pisau"},
        {"date": DAY, "machine": "WM", "machine_raw": "WM", "menit": 135,
         "issue_label": "alarm", "description_raw": "alarm drives"},
        {"date": DAY - dt.timedelta(days=1), "machine": "TFM 1", "machine_raw": "TFM 1",
         "menit": 99, "issue_label": "x", "description_raw": "x"},  # hari lain
    ]
    monkeypatch.setattr(wb_mod, "find_current_workbook", lambda c: tmp_path / "wb.xlsx")
    monkeypatch.setattr(wb_mod, "read_events", lambda c: events)
    out = wa_chart.machine_chart(cfg, DAY)
    assert out is not None
    assert out.exists() and out.stat().st_size > 5000
    assert out.suffix == ".png"


def test_machine_chart_none_when_no_data_that_day(tmp_path, monkeypatch):
    from src import workbook as wb_mod
    cfg = _cfg_png(tmp_path)
    monkeypatch.setattr(wb_mod, "find_current_workbook", lambda c: tmp_path / "wb.xlsx")
    monkeypatch.setattr(wb_mod, "read_events", lambda c: [])
    assert wa_chart.machine_chart(cfg, DAY) is None


def test_spare_chart_none_when_no_transactions(tmp_path):
    cfg = _cfg_png(tmp_path)
    cfg["spare"] = {
        "workbook": str(tmp_path / "wb.xlsx"),
        "backup_dir": str(tmp_path / "b"),
        "backup_keep": 3,
        "state_file": str(tmp_path / "s.json"),
    }
    sys.path.insert(0, str(ROOT / "tests" / "tooling"))
    from fixture import build_spare_workbook  # noqa: E402
    build_spare_workbook(Path(cfg["spare"]["workbook"]), [], [])
    assert wa_chart.spare_chart(cfg, DAY) is None  # log kosong -> tanpa gambar


def test_spare_chart_png_with_transactions(tmp_path):
    cfg = _cfg_png(tmp_path)
    cfg["spare"] = {
        "workbook": str(tmp_path / "wb.xlsx"),
        "backup_dir": str(tmp_path / "b"),
        "backup_keep": 3,
        "state_file": str(tmp_path / "s.json"),
    }
    sys.path.insert(0, str(ROOT / "tests" / "tooling"))
    from fixture import build_spare_workbook  # noqa: E402
    import openpyxl  # noqa: E402
    wb_path = Path(cfg["spare"]["workbook"])
    build_spare_workbook(wb_path, [], [])
    wb = openpyxl.load_workbook(wb_path)
    log = wb["LOG PENGELUARAN"]
    for i, (comp, fam, qty) in enumerate([("MOULD", "CUP-16", 2), ("MOULD", "CUP-16", 1),
                                          ("EJECTOR", "CUP-CORN", 1)], start=5):
        log.cell(i, 1).value = DAY
        log.cell(i, 4).value = fam
        log.cell(i, 7).value = comp
        log.cell(i, 8).value = qty
        log.cell(i, 11).value = f"T2-OUT-X{i}"
    wb.save(wb_path)
    out = wa_chart.spare_chart(cfg, DAY)
    assert out is not None and out.exists() and out.stat().st_size > 5000


def test_group_for_resolves_and_missing_raises(tmp_path):
    cfg = _cfg_png(tmp_path)
    assert wa_send.group_for(cfg, "proses1") == "Extruder Bolang"
    assert wa_send.group_for(cfg, "proses2") == "Setter & t.s & produksi"
    # cfg per-proses (punya process_key)
    cfg2 = dict(cfg, process_key="proses2")
    assert wa_send.group_for(cfg2) == "Setter & t.s & produksi"
    # grup belum diisi -> error jelas
    cfg3 = _cfg_png(tmp_path)
    cfg3["whatsapp"] = {}
    with pytest.raises(wa_send.WaError) as e:
        wa_send.group_for(cfg3, "proses1")
    assert "config.yaml" in str(e.value)


def test_wa_settings_defaults_and_profile_abs(tmp_path):
    cfg = _cfg_png(tmp_path)
    s = wa_send.wa_settings(cfg)
    assert s["channel"] == "msedge"
    assert s["attach_chart"] is True
    assert Path(s["profile"]).name == "wa_profile"


def test_send_rejects_empty_text(tmp_path):
    cfg = _cfg_png(tmp_path)
    with pytest.raises(wa_send.WaError):
        wa_send.send_to_group(cfg, group_name="Grup X", text="   ")
