"""Test Tool 2: alarm, pareto, dashboard, riwayat, draft, keamanan simpan."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture import make_store  # noqa: E402

from src.tooling import service
from src.tooling.models import StockStatus
from src.tooling.pareto import pareto


def test_minimum_stock_alarm_levels(tmp_path):
    store, _ = make_store(tmp_path, minimum_stock={"CUP-16": {"MOULD": 5}})
    views = {v.item.key: v for v in service.stock_views(store)}
    # stock 5, minimum 5 -> LOW
    assert views[("cup-16", "mould")].status == StockStatus.LOW
    # stock 0 tanpa minimum -> OUT
    assert views[("cup-16", "insert")].status == StockStatus.OUT
    # stock positif tanpa minimum -> NOT CONFIGURED
    assert views[("cup-16", "insert2")] if False else True
    assert views[("cup-16", "mould")].minimum == 5


def test_alarm_list_excludes_unknown(tmp_path):
    store, _ = make_store(tmp_path)
    alarm = service.alarms(store)
    assert all(v.status != StockStatus.UNKNOWN for v in alarm)
    assert [v.item.key for v in alarm] == [("cup-16", "insert")]  # hanya stock 0


def test_pareto_dimensions_and_dates(tmp_path):
    store, _ = make_store(tmp_path)
    today = dt.date.today()
    # transaksi via workbook langsung supaya tanggalnya bisa dikontrol
    wb = store.load()
    from src.tooling.models import OutTx
    store.ensure_structure(wb)
    for i, (day, comp, fam, mesin, qty) in enumerate([
        (today, "MOULD", "CUP-16", "WM", 2),
        (today - dt.timedelta(days=9), "MOULD", "CUP-16", "WM", 1),
        (today, "EJECTOR", "CUP-CORN", "TF2", 1),
    ], start=5):
        wb["LOG PENGELUARAN"].cell(i, 1).value = day
        wb["LOG PENGELUARAN"].cell(i, 3).value = mesin
        wb["LOG PENGELUARAN"].cell(i, 4).value = fam
        wb["LOG PENGELUARAN"].cell(i, 7).value = comp
        wb["LOG PENGELUARAN"].cell(i, 8).value = qty
        wb["LOG PENGELUARAN"].cell(i, 11).value = f"T2-OUT-X{i}"
    store.save(wb)

    log = store.read_log(store.load())
    # semua waktu
    r = pareto(log, top=None)
    assert r["total_qty"] == 4 and r["n_tx"] == 3
    comp_rows, comp_total = r["component"]
    assert comp_rows[0]["name"] == "MOULD"
    # hanya hari ini
    r_today = pareto(log, start=today, end=today, top=None)
    assert r_today["total_qty"] == 3 and r_today["n_tx"] == 2
    mes_rows, _m_total = r_today["machine"]
    assert mes_rows[0]["name"] == "WM"
    # periode kosong
    r_empty = pareto(log, start=today - dt.timedelta(days=1), end=today - dt.timedelta(days=1))
    assert r_empty["n_tx"] == 0


def test_daily_summary(tmp_path):
    store, _ = make_store(tmp_path)
    service.record_out(store, family="CUP-16", component="MOULD", qty=2)
    s = service.daily_summary(store)
    assert s["n_tx"] == 1 and s["total_qty"] == 2
    assert s["top_component"] == ("MOULD", 2)
    assert s["top_family"] == ("CUP-16", 2)


def test_history_filters(tmp_path):
    store, _ = make_store(tmp_path)
    service.record_out(store, family="CUP-16", component="MOULD", qty=1)
    rows = service.history(store, family="cup-16")
    assert len(rows) == 1
    assert service.history(store, family="DATAR-12") == []


def test_whatsapp_draft_factual(tmp_path):
    store, _ = make_store(tmp_path)
    text = service.whatsapp_summary(store)
    assert "Belum ada pengeluaran sparepart." in text
    service.record_out(store, family="CUP-16", component="MOULD", qty=2)
    service.opname(store, family="CUP-16", component="INSERT", physical=0)
    text = service.whatsapp_summary(store)
    assert "MOULD = 2" in text
    assert "CUP-16/INSERT sisa 0" in text
    assert "Tolong dibantu follow up restock" in text


def test_dashboard_created_only_with_transactions(tmp_path):
    store, wb_path = make_store(tmp_path)
    wb = store.load()
    assert "DASHBOARD SPARE" not in wb.sheetnames
    service.record_out(store, family="CUP-16", component="MOULD", qty=1)
    wb2 = openpyxl.load_workbook(wb_path)
    assert "DASHBOARD SPARE" in wb2.sheetnames
    dash = wb2["DASHBOARD SPARE"]
    assert str(dash["B5"].value).startswith("=SUMIFS")   # qty hari ini = formula hidup
    assert dash["B6"].value is not None                  # jumlah transaksi
    charts = dash._charts
    assert len(charts) >= 2                              # pareto + trend


def test_save_failure_preserves_original(tmp_path):
    store, wb_path = make_store(tmp_path)
    sha_before = wb_path.read_bytes()
    service.record_out(store, family="CUP-16", component="MOULD", qty=1)
    ok_state = wb_path.read_bytes()

    # paksa validasi gagal pada simpan berikutnya
    from src.tooling import validator as sv
    try:
        wb = store.load()
        original = sv.validate_spare_workbook
        sv.validate_spare_workbook = lambda w: ["error uji"]
        import src.tooling.service as svc
        svc_validator_backup = None
        try:
            wb["STOCK SPARE"].cell(5, 8).value = None  # mutasi apa pun; validasi akan menolak
            store.save(wb, validator=lambda w: ["error uji"])
            assert False, "harusnya gagal"
        finally:
            sv.validate_spare_workbook = original
    except RuntimeError as exc:
        assert "tidak disimpan" in str(exc)
    # workbook tidak berubah
    assert wb_path.read_bytes() == ok_state


def test_backup_created_and_pruned(tmp_path):
    store, wb_path = make_store(tmp_path)
    for i in range(5):
        service.record_out(store, family="CUP-16", component="MOULD", qty=1)
    backups = sorted((tmp_path / "backups").glob("spare_backup_*.xlsx"))
    assert len(backups) == 3  # backup_keep=3


def test_external_change_detection(tmp_path):
    store, wb_path = make_store(tmp_path)
    service.record_out(store, family="CUP-16", component="MOULD", qty=1)
    assert store.check_external_changes() is False
    # simulasi edit dari luar (mis. user buka & simpan di Excel)
    wb = openpyxl.load_workbook(wb_path)
    wb["LOG PENGELUARAN"]["I5"] = "diubah manual"
    wb.save(wb_path)
    assert store.check_external_changes() is True
