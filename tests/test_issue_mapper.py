"""Test issue mapping (case-insensitive, urutan prioritas, fallback)."""
from __future__ import annotations

from tests.conftest import base_cfg
from src.issue_mapper import IssueMapper


def mapper() -> IssueMapper:
    return IssueMapper(base_cfg())


def test_plug_assist_variants():
    m = mapper()
    for text in ("produk nempel di plugassit", "SEMPROT produk Nempel",
                 "ganti plugassit 3 pcs", "alarm plugasit", "cabut bekuan nempel"):
        group, label = m.map_text(text)
        assert group == "plug_assist", text
        assert label == "Plug Assist / Produk Nempel"


def test_tunggu_bahan_before_others():
    m = mapper()
    assert m.map_text("tunggu bahan")[0] == "tunggu_bahan"
    assert m.map_text("TUNGGU BAHAN")[0] == "tunggu_bahan"


def test_group_priority_order():
    m = mapper()
    # 'alarm plugasit' harus jatuh ke plug_assist (lebih spesifik), bukan alarm
    assert m.map_text("alarm plugasit")[0] == "plug_assist"
    # 'perbaikan stackingan' -> stacking
    assert m.map_text("perbaikan stackingan")[0] == "stacking"
    # 'ganti selang robot' -> robot
    assert m.map_text("ganti selang robot sobek")[0] == "robot"
    # 'lap plate dan blanket' -> pisau/cutting
    assert m.map_text("lap plate dan blanket")[0] == "pisau_cutting"
    # 'perbaikan tali kompayer putus' -> conveyor
    assert m.map_text("perbaikan tali kompayer putus")[0] == "conveyor"
    # 'alarm produk ganda' -> alarm mesin
    assert m.map_text("alarm produk ganda")[0] == "alarm_mesin"


def test_fallback_other():
    m = mapper()
    group, label = m.map_text("perbaikan heater eror")
    assert group == "other"
    assert label == "Other"
    assert m.map_text("")[0] == "other"


def test_case_insensitive():
    m = mapper()
    assert m.map_text("  ALARM   STACKEr  ")[0] == "stacking"


def test_apply_sets_fields(tmp_path):
    from tests.conftest import make_event
    ev = make_event(keterangan="produk nempel di plugassit")
    m = mapper()
    m.apply([ev])
    assert ev["issue_group"] == "plug_assist"
    assert ev["keterangan"] == "produk nempel di plugassit"   # raw tetap ada
