"""Test rekap downtime bulanan: template sintetis mini per layout.

Layout mini mengikuti struktur template asli:
- proses2 (thick-wall): header DATA DOWNTIME r1, 10 kolom, PARETO MESIN 3 rank,
  TREND 31 baris, judul bulan di A1 tiap sheet.
- proses1 (extrusion): judul r1/r3, header DATA r5, 9 kolom (Tipe Durasi),
  PARETO MESIN rank + TOTAL + breakdown, PARETO ISSUE lebih banyak rank.

Excel yang menghitung (formula dibiarkan hidup), Python hanya isi nilai.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import openpyxl  # noqa: E402
import pytest  # noqa: E402

from src import recap  # noqa: E402

MONTH = (2026, 11)


def _ev(date: dt.date, machine: str, menit: int, issue: str = "pisau",
        kat: str = "A", jam: str = "08:00", key: str | None = None,
        ket: str = "perbaikan", kode: str = "BJ-X", produk: str = "Cup 12") -> dict:
    hm = dt.time(int(jam[:2]), int(jam[3:]))
    return {
        "date": date, "machine_raw": machine, "machine": machine,
        "kode_barang": kode, "nama_produk": produk,
        "jam_mulai": hm, "jam_selesai": dt.time(10, 0), "menit": menit,
        "keterangan": ket, "kategori": kat, "issue_label": issue,
        "event_key": key or f"{date}-{machine}-{jam}-{menit}",
    }


# --------------------------------------------------------------------------- #
# template mini proses 2 (thick-wall)
# --------------------------------------------------------------------------- #
def _build_tpl_p2(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SUMMARY BULANAN"
    ws["A1"] = "REKAP DOWNTIME PROSES 2 — OKTOBER 2026"
    ws["A4"] = "TOTAL DOWNTIME (MENIT)"
    ws["A5"] = "=SUM('DATA DOWNTIME'!G2:G3)"
    ws["B5"] = "=COUNTA('DATA DOWNTIME'!A2:A3)"

    pm = wb.create_sheet("PARETO MESIN")
    pm["A1"] = "PARETO DOWNTIME MESIN — OKTOBER 2026"
    pm["A4"], pm["B4"] = "Rank", "Mesin"
    pm["C4"], pm["D4"] = "Event", "Menit"
    # 3 slot rank template, baris terakhir penuh formula (acuan klon)
    for i, r in enumerate(range(5, 8)):
        pm.cell(r, 1).value = i + 1
        pm.cell(r, 3).value = (f"=COUNTIF('DATA DOWNTIME'!$B$2:$B$3,B{r})")
        pm.cell(r, 4).value = (f"=SUMIF('DATA DOWNTIME'!$B$2:$B$3,B{r},"
                               f"'DATA DOWNTIME'!$G$2:$G$3)")

    pi = wb.create_sheet("PARETO ISSUE")
    pi["A1"] = "PARETO DOWNTIME ISSUE — OKTOBER 2026"
    pi["A4"], pi["B4"] = "Rank", "Issue"
    pi["C4"], pi["D4"] = "Event", "Menit"
    for i in range(5, 7):
        pi.cell(i, 1).value = 5 - i + 5 - 5 + (i - 4)  # 1, 2
        pi.cell(i, 3).value = f"=COUNTIF('DATA DOWNTIME'!$J$2:$J$3,B{i})"
        pi.cell(i, 4).value = (f"=SUMIF('DATA DOWNTIME'!$J$2:$J$3,B{i},"
                               f"'DATA DOWNTIME'!$G$2:$G$3)")

    th = wb.create_sheet("TREND HARIAN")
    th["A1"] = "TREND DOWNTIME HARIAN — OKTOBER 2026"
    th["A4"], th["B4"] = "Tanggal", "Menit"
    for i in range(31):
        r = 5 + i
        th.cell(r, 1).value = dt.datetime(2026, 10, i + 1)
        th.cell(r, 2).value = (f"=SUMIF('DATA DOWNTIME'!$A$2:$A$3,A{r},"
                               f"'DATA DOWNTIME'!$G$2:$G$3)")

    dd = wb.create_sheet("DATA DOWNTIME")
    heads = ["Tanggal", "Mesin", "Kode BJ", "Nama Produk", "Jam Mulai",
             "Jam Selesai", "Downtime Menit", "Keterangan", "Kategori",
             "Issue Group"]
    for c, h in enumerate(heads, start=1):
        dd.cell(1, c).value = h
    # 2 baris data contoh Oktober (bakal dibersihkan saat build)
    for r, (d, m, men) in enumerate(
            [(dt.datetime(2026, 10, 1), "TFM 1", 30),
             (dt.datetime(2026, 10, 2), "WM", 20)], start=2):
        dd.cell(r, 1).value = d
        dd.cell(r, 2).value = m
        dd.cell(r, 7).value = men
    wb.save(path)


def _cfg_p2(tmp_path: Path) -> dict:
    tpl = tmp_path / "tpl_p2.xlsx"
    _build_tpl_p2(tpl)
    return {
        "process_key": "proses2",
        "process_label": "Proses 2",
        "output": {"output_dir": str(tmp_path / "out")},
        "recap": {"templates": {"proses2": str(tpl)}},
        "workbook": {},
    }


# --------------------------------------------------------------------------- #
# template mini proses 1 (extrusion)
# --------------------------------------------------------------------------- #
def _build_tpl_p1(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SUMMARY BULANAN"
    ws["A1"] = "REKAP DOWNTIME PROSES 1 — OKTOBER 2026"
    ws["A3"] = "PLANT BOLANG  /  EXTRUSION  /  PERIODE 01–31 OKTOBER 2026"
    ws["A6"] = "=SUM('DATA DOWNTIME'!E6:E6)"

    pm = wb.create_sheet("PARETO MESIN")
    pm["A1"] = "PARETO MESIN — PROSES 1 | OKTOBER 2026"
    pm["A5"], pm["B5"], pm["D5"] = "Rank", "Mesin", "Menit"
    # 3 slot rank (r6..r8), TOTAL r10, breakdown (header "Mesin" r12, 3 slot r13..15)
    for i, r in enumerate(range(6, 9)):
        pm.cell(r, 1).value = i + 1
        pm.cell(r, 4).value = f"=SUMIF('DATA DOWNTIME'!$B$6:$B$6,B{r},'DATA DOWNTIME'!$E$6:$E$6)"
    pm["B10"] = "TOTAL"
    pm["A12"], pm["B12"] = "Mesin", "Reguler (menit)"
    pm["A13"], pm["A14"], pm["A15"] = "EXT 4", "EXT 1", "EXT 3"

    pi = wb.create_sheet("PARETO ISSUE")
    pi["A1"] = "PARETO ISSUE — PROSES 1 | OKTOBER 2026"
    pi["A5"], pi["B5"], pi["D5"] = "Rank", "Issue", "Menit"
    for i in range(6, 11):
        pi.cell(i, 1).value = i - 5
        pi.cell(i, 4).value = f"=SUMIF('DATA DOWNTIME'!$H$6:$H$6,B{i},'DATA DOWNTIME'!$E$6:$E$6)"

    th = wb.create_sheet("TREND HARIAN")
    th["A1"] = "TREND HARIAN — PROSES 1 | OKTOBER 2026"
    th["A3"] = "PERIODE 01–31 OKTOBER 2026  |  TANGGAL TANPA RECORD KOSONG"
    th["A5"], th["B5"] = "Tanggal", "Menit"
    for i in range(31):
        r = 6 + i
        th.cell(r, 1).value = dt.datetime(2026, 10, i + 1)
        th.cell(r, 2).value = f"=SUMIF('DATA DOWNTIME'!$A$6:$A$6,A{r},'DATA DOWNTIME'!$E$6:$E$6)"

    dd = wb.create_sheet("DATA DOWNTIME")
    dd["A1"] = "DATA DOWNTIME — EXTRUSION | OKTOBER 2026"
    dd["A3"] = "SUMBER: DAILY REPORT PROSES 1 — SHEET DOWNTIME  |  01–31 OKTOBER 2026"
    heads = ["Tanggal", "Mesin", "Jam Mulai", "Jam Selesai", "Menit",
             "Description Asli", "Kategori Asli", "Issue Group", "Tipe Durasi"]
    for c, h in enumerate(heads, start=1):
        dd.cell(5, c).value = h
    dd.cell(6, 1).value = dt.datetime(2026, 10, 1)
    dd.cell(6, 2).value = "EXT 1"
    dd.cell(6, 5).value = 90
    wb.save(path)


def _cfg_p1(tmp_path: Path) -> dict:
    tpl = tmp_path / "tpl_p1.xlsx"
    _build_tpl_p1(tpl)
    return {
        "process_key": "proses1",
        "process_label": "Proses 1",
        "output": {"output_dir": str(tmp_path / "out1")},
        "recap": {"templates": {"proses1": str(tpl)}},
        "workbook": {},
    }


# --------------------------------------------------------------------------- #
# helper: monkeypatch sumber event
# --------------------------------------------------------------------------- #
def _stub_events(monkeypatch, events: list[dict]) -> None:
    import src.workbook as wb_mod
    monkeypatch.setattr(wb_mod, "read_events", lambda cfg: list(events))


EVENTS_NOV = [
    _ev(dt.date(2026, 11, 1), "TFM 1", 60, issue="pisau"),
    _ev(dt.date(2026, 11, 1), "WM", 30, issue="alarm"),
    _ev(dt.date(2026, 11, 2), "TFM 1.1", 120, issue="tunggu bahan"),
    _ev(dt.date(2026, 11, 3), "VACUM 2", 15, issue="pisau", kat="LT"),
]
# urutan rank mesin: TFM 1.1 (120), TFM 1 (60), WM (30), VACUM 2 (15)
# urutan rank issue: pisau (75), tunggu bahan (120->2), alarm (30)
# -> pisau 75, tunggu bahan 120, alarm 30 => tunggu bahan, pisau, alarm


# --------------------------------------------------------------------------- #
# test: parse bulan & label
# --------------------------------------------------------------------------- #
def test_parse_month_variants():
    assert recap.parse_month("2026-11") == (2026, 11)
    assert recap.parse_month("2026-11-05") == (2026, 11)
    assert recap.parse_month("2026-2") == (2026, 2)
    with pytest.raises(recap.RecapError):
        recap.parse_month("november 2026")
    with pytest.raises(recap.RecapError):
        recap.parse_month("2026-13")


# --------------------------------------------------------------------------- #
# test: build proses 2
# --------------------------------------------------------------------------- #
def test_build_p2_writes_data_titles_and_extend(tmp_path, monkeypatch):
    _stub_events(monkeypatch, EVENTS_NOV)
    cfg = _cfg_p2(tmp_path)
    info = recap.build(cfg, "2026-11")

    assert info["n_events"] == 4
    assert info["month"] == "NOVEMBER 2026"
    out = Path(info["path"])
    assert out.exists()
    wb = openpyxl.load_workbook(out)

    # data 4 baris mulai r2, tanggal Nov 2026
    dd = wb["DATA DOWNTIME"]
    assert dd.cell(2, 1).value == dt.datetime(2026, 11, 1)
    assert dd.cell(2, 2).value == "TFM 1"
    assert dd.cell(2, 7).value == 60
    assert dd.cell(5, 1).value == dt.datetime(2026, 11, 3)
    assert dd.cell(6, 1).value is None  # baris ke-5 kosong

    # judul: OKTOBER -> NOVEMBER di semua zona judul
    assert "NOVEMBER 2026" in wb["SUMMARY BULANAN"]["A1"].value
    assert "NOVEMBER 2026" in wb["PARETO MESIN"]["A1"].value
    assert "OKTOBER" not in wb["SUMMARY BULANAN"]["A1"].value

    # data contoh Oktober terkikis
    assert dd.cell(2, 2).value == "TFM 1"
    assert wb["DATA DOWNTIME"].cell(99, 1).value is None

    # PARETO MESIN: 4 mesin > 3 slot template -> baris ke-4 klon
    pm = wb["PARETO MESIN"]
    names = [pm.cell(r, 2).value for r in range(5, 9)]
    assert names == ["TFM 1.1", "TFM 1", "WM", "VACUM 2"]
    # formula baris klon di-translasi referensinya (B3 -> B8)
    assert "B8" in str(pm.cell(8, 4).value)
    assert "#REF" not in str(pm.cell(8, 4).value)

    # rentang formula diperpanjang: old_end 3 -> new_end 105
    assert "G105" in str(wb["SUMMARY BULANAN"]["A5"].value)


def test_build_p2_rank_names_order_and_clear(tmp_path, monkeypatch):
    _stub_events(monkeypatch, EVENTS_NOV[:2])  # hanya 2 mesin
    cfg = _cfg_p2(tmp_path)
    info = recap.build(cfg, "2026-11")
    wb = openpyxl.load_workbook(info["path"])
    pm = wb["PARETO MESIN"]
    # mesin: TFM 1 (60), WM (30)
    assert pm.cell(5, 2).value == "TFM 1"
    assert pm.cell(6, 2).value == "WM"
    # slot rank 3 template kosong tapi nomor rank & formula utuh
    assert pm.cell(7, 2).value is None
    assert pm.cell(7, 1).value == 3
    assert str(pm.cell(7, 4).value).startswith("=SUMIF")
    assert info["warnings"] == []


def test_build_p2_trend_dates_and_blank_after_month(tmp_path, monkeypatch):
    _stub_events(monkeypatch, EVENTS_NOV)
    cfg = _cfg_p2(tmp_path)
    info = recap.build(cfg, "2026-11")  # Nov = 30 hari
    wb = openpyxl.load_workbook(info["path"])
    th = wb["TREND HARIAN"]
    assert th.cell(5, 1).value == dt.datetime(2026, 11, 1)
    assert th.cell(34, 1).value == dt.datetime(2026, 11, 30)
    # baris 31 template (r35) dikosongkan
    assert th.cell(35, 1).value is None
    assert th.cell(35, 2).value is None
    info2 = recap.build(cfg, "2027-02")  # Feb non-kabisat = 28 hari
    wb2 = openpyxl.load_workbook(info2["path"])
    th2 = wb2["TREND HARIAN"]
    assert th2.cell(5, 1).value == dt.datetime(2027, 2, 1)
    assert th2.cell(32, 1).value == dt.datetime(2027, 2, 28)
    assert th2.cell(33, 1).value is None
    # tahun di judul ikut berganti
    assert "2027" in wb2["SUMMARY BULANAN"]["A1"].value


def test_build_creates_backup_on_rerun(tmp_path, monkeypatch):
    _stub_events(monkeypatch, EVENTS_NOV)
    cfg = _cfg_p2(tmp_path)
    recap.build(cfg, "2026-11")
    out_dir = Path(cfg["output"]["output_dir"])
    first = next(p for p in out_dir.iterdir() if p.suffix == ".xlsx")
    recap.build(cfg, "2026-11")
    bdir = out_dir / "backups"
    backups = list(bdir.glob("*.xlsx"))
    assert len(backups) == 1
    assert first.stem in backups[0].name


def test_build_empty_month_ok_with_warning(tmp_path, monkeypatch):
    _stub_events(monkeypatch, [])
    cfg = _cfg_p2(tmp_path)
    info = recap.build(cfg, "2026-12")
    assert info["n_events"] == 0
    assert any("Tidak ada event" in w for w in info["warnings"])
    wb = openpyxl.load_workbook(info["path"])
    assert "DESEMBER 2026" in wb["SUMMARY BULANAN"]["A1"].value
    dd = wb["DATA DOWNTIME"]
    assert dd.cell(2, 1).value is None  # data contoh dibersihkan


def test_month_events_filters_month_and_dedupes(tmp_path, monkeypatch):
    events = [
        _ev(dt.date(2026, 10, 31), "TFM 1", 30, key="a"),
        _ev(dt.date(2026, 11, 1), "WM", 30, key="b"),
        _ev(dt.date(2026, 11, 1), "WM", 30, key="b"),  # duplikat event_key
        _ev(dt.date(2026, 12, 1), "TFM 1", 10, key="c"),
    ]
    _stub_events(monkeypatch, events)
    cfg = _cfg_p2(tmp_path)
    out = recap.month_events(cfg, 2026, 11)
    assert len(out) == 1
    assert out[0]["machine_raw"] == "WM"


# --------------------------------------------------------------------------- #
# test: build proses 1 (extrusion, REGULER/LT)
# --------------------------------------------------------------------------- #
def test_build_p1_writes_columns_and_tipe_durasi(tmp_path, monkeypatch):
    _stub_events(monkeypatch, EVENTS_NOV)
    cfg = _cfg_p1(tmp_path)
    info = recap.build(cfg, "2026-11")
    wb = openpyxl.load_workbook(info["path"])
    dd = wb["DATA DOWNTIME"]
    # data mulai r6; kolom: Tanggal, Mesin, Jam Mulai, Jam Selesai, Menit,
    # Description, Kategori, Issue Group, Tipe Durasi
    assert dd.cell(6, 1).value == dt.datetime(2026, 11, 1)
    assert dd.cell(6, 2).value == "TFM 1"
    r2 = [dd.cell(7, c).value for c in range(1, 10)]
    assert r2[1] == "WM" and r2[4] == 30
    assert r2[8] == "REGULER"
    # event kelima (VACUM 2, kategori LT) -> Tipe Durasi LT
    rows = [[dd.cell(r, c).value for c in range(1, 10)] for r in range(6, 10)]
    assert dict((row[1], row[8]) for row in rows)["VACUM 2"] == "LT"
    # judul & periode
    assert "NOVEMBER 2026" in dd["A1"].value
    assert "01–30 NOVEMBER 2026" in dd["A3"].value
    assert "01-30 NOVEMBER 2026" in wb["TREND HARIAN"]["A3"].value or \
        "30 NOVEMBER 2026" in wb["TREND HARIAN"]["A3"].value
    # TOTAL & breakdown tetap di posisinya (tidak digeser)
    pm = wb["PARETO MESIN"]
    assert pm["B10"].value == "TOTAL"
    # breakdown: nama mesin mengikuti urutan rank, 3 slot template
    assert pm.cell(12, 1).value == "Mesin"
    assert pm.cell(13, 1).value == "TFM 1.1"
    assert pm.cell(14, 1).value == "TFM 1"
    # 4 mesin > uraian slot karena breakdown cuma 3 -> slot rank pun overflow
    assert any("mesin tidak muat" in w for w in info["warnings"])


def test_p1_too_many_machines_not_error(tmp_path, monkeypatch):
    extra = EVENTS_NOV + [_ev(dt.date(2026, 11, 5), "EXT 2", 45, issue="mould")]
    _stub_events(monkeypatch, extra)
    cfg = _cfg_p1(tmp_path)
    info = recap.build(cfg, "2026-11")  # 5 mesin, template hanya 3 slot
    assert info["n_machines"] == 5
    assert any("mesin tidak muat" in w for w in info["warnings"])


# --------------------------------------------------------------------------- #
# test: validasi
# --------------------------------------------------------------------------- #
def test_validate_flags_out_of_month_and_broken_ref(tmp_path, monkeypatch):
    _stub_events(monkeypatch, EVENTS_NOV)
    cfg = _cfg_p2(tmp_path)
    wb = openpyxl.load_workbook(cfg["recap"]["templates"]["proses2"])
    layout = recap.detect_layout(wb)
    # telanjang: tulis tanggal Oktober -> harus kena
    wb["DATA DOWNTIME"].cell(2, 1).value = dt.datetime(2026, 10, 5)
    errors = recap.validate_recap(wb, layout, [], 2026, 11)
    assert any("di luar bulan" in e for e in errors)
    wb["PARETO MESIN"]["B5"] = "=SUM('DATA'!#REF!)"
    errors = recap.validate_recap(wb, layout, [], 2026, 11)
    assert any("#REF" in e for e in errors)


def test_validate_counts_mismatch(tmp_path):
    tpl = tmp_path / "tpl_p2.xlsx"
    _build_tpl_p2(tpl)
    cfg = _cfg_p2(tmp_path)
    wb = openpyxl.load_workbook(tpl)
    layout = recap.detect_layout(wb)
    # template masih punya 2 baris contoh, event kosong -> jumlah tak cocok
    errors = recap.validate_recap(wb, layout, [], 2026, 11)
    assert any("jumlah" in e.lower() for e in errors)
