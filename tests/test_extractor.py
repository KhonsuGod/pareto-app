"""Test parser extractor: tanggal, jam, menit, machine_group."""
from __future__ import annotations

import datetime as dt

from src.extractor import (
    extract_events,
    machine_group,
    parse_date,
    parse_minutes,
    parse_time,
)


def test_parse_date_datetime_and_str():
    assert parse_date(dt.datetime(2026, 10, 27, 8, 0)) == dt.date(2026, 10, 27)
    assert parse_date(dt.date(2026, 10, 27)) == dt.date(2026, 10, 27)
    assert parse_date("2026-10-27") == dt.date(2026, 10, 27)
    assert parse_date("27/10/2026") == dt.date(2026, 10, 27)
    assert parse_date("2026-10-27 00:00:00") == dt.date(2026, 10, 27)


def test_parse_date_invalid_returns_none():
    assert parse_date(None) is None
    assert parse_date("") is None
    assert parse_date(1) is None             # serial tidak masuk akal (row sampah)
    assert parse_date(1.5) is None
    assert parse_date("tanggal salah") is None


def test_parse_time_variants():
    assert parse_time(dt.time(8, 50)) == dt.time(8, 50)
    t = dt.datetime(2026, 1, 1, 8, 50, 10)
    assert parse_time(t) == dt.time(8, 50, 10)
    assert parse_time("08:50") == dt.time(8, 50)
    assert parse_time("8:50") == dt.time(8, 50)
    assert parse_time("8.50") == dt.time(8, 50)
    assert parse_time("22:15:00") == dt.time(22, 15)
    assert parse_time(None) is None
    assert parse_time("25:00") is None


def test_parse_minutes_from_value_and_fallback():
    assert parse_minutes(10) == 10
    assert parse_minutes("15") == 15
    assert parse_minutes("", "08:50", "09:00") == 10
    assert parse_minutes(None, "13:40", "13:50") == 10


def test_parse_minutes_with_unit_suffix():
    # sheet Proses 1 kadang berisi "90 Menit" / "1.440 menit"
    assert parse_minutes("90 Menit") == 90
    assert parse_minutes("90 menit") == 90
    assert parse_minutes(" 45 mnt ") == 45
    assert parse_minutes("12,6 menit") == 13


def test_parse_minutes_overnight():
    # 23:00 -> 01:30 lintas hari = 150 menit
    assert parse_minutes(None, "23:00", "01:30") == 150


def test_parse_minutes_invalid():
    assert parse_minutes("abc", None, None) is None
    assert parse_minutes(-5) is None


def test_machine_group_keeps_original_family():
    assert machine_group("TFM 1.1") == "TFM 1"
    assert machine_group("TFM 4.3") == "TFM 4"
    assert machine_group("WM.2") == "WM"
    assert machine_group("PRT 4.1") == "PRT 4"
    # nama dasar tidak berubah
    assert machine_group("TFM 1") == "TFM 1"
    assert machine_group("TFM 2") == "TFM 2"
    assert machine_group("VACUM 7") == "VACUM 7"
    assert machine_group("TLB-7") == "TLB-7"   # bukan dot suffix
    assert machine_group("WM") == "WM"


def test_machine_group_trims_space():
    assert machine_group("  TFM 1.3  ") == "TFM 1"


# --------------------------------------------------------------------------- #
# Format sheet Proses 1: header di baris 3, kolom opsional, "90 Menit"
# --------------------------------------------------------------------------- #
def _proses1_cfg() -> dict:
    from conftest import base_cfg
    from src import processes
    return processes.resolve(base_cfg(), "proses1")


def _proses1_rows() -> list[list]:
    return [
        ["REKAP DOWNTIME PROSES 1", None, None, None, None, None, None, None],
        ["LT = Lost Time | A = Maintenance", None, None, None, None, None, None, None],
        ["TGL", "MESIN", "JAM", "SELESAI", "TOTAL (JAM)", "TOTAL (MENIT)",
         "DESCRIPTION", "Jenis Downtime"],
        [dt.datetime(2026, 10, 27), "EXT 1", "08:00", "09:30", None, "90 Menit",
         "mpa error", "LT Maintenance"],
        [dt.datetime(2026, 10, 27), "EXT 4", "10:00", "10:44", None, 44,
         "calender 1 panas", "A"],
        [None, None, None, None, None, None, None, None],
    ]


def test_extract_events_finds_header_row_below_legends():
    events = extract_events(_proses1_rows(), _proses1_cfg())
    assert len(events) == 2
    assert events[0]["machine_raw"] == "EXT 1"
    assert events[0]["menit"] == 90
    assert events[1]["menit"] == 44


def test_extract_events_optional_columns_blank():
    # Proses 1 tidak punya KODE BARANG / NAMA PRODUK -> harus jadi string kosong
    events = extract_events(_proses1_rows(), _proses1_cfg())
    assert events[0]["kode_barang"] == ""
    assert events[0]["nama_produk"] == ""


def test_normalize_kategori_proses1():
    from src.extractor import normalize_kategori
    cfg = _proses1_cfg()
    assert normalize_kategori("LT Maintenance", cfg) == "LT"
    assert normalize_kategori("LT QC", cfg) == "LT"
    assert normalize_kategori("A", cfg) == "A"
    assert normalize_kategori("", cfg) == ""
