"""Test resolusi config per proses (Proses 1 vs Proses 2)."""
from __future__ import annotations

import pytest

from conftest import base_cfg
from src import processes


def test_aliases():
    base = base_cfg()
    assert processes.normalize_key("1", base) == "proses1"
    assert processes.normalize_key("proses 1", base) == "proses1"
    assert processes.normalize_key("p1", base) == "proses1"
    assert processes.normalize_key("2", base) == "proses2"
    assert processes.normalize_key("p2", base) == "proses2"
    assert processes.normalize_key(None, base) == "proses2"


def test_unknown_process_raises():
    with pytest.raises(KeyError):
        processes.normalize_key("9", base_cfg())


def test_resolve_proses1_overrides_columns_and_output():
    p1 = processes.resolve(base_cfg(), "1")
    p2 = processes.resolve(base_cfg(), "2")

    assert p1["process_key"] == "proses1"
    assert p1["process_label"] == "Proses 1"
    assert p1["columns"]["jam_mulai"] == "JAM"
    assert p1["columns"]["keterangan"] == "DESCRIPTION"
    assert p1["columns"]["kode_barang"] == ""      # tidak ada di sheet Proses 1
    assert p2["columns"]["jam_mulai"] == "JAM MULAI"

    assert p1["output"]["latest_name"] == "Monitoring_Proses1_LATEST.xlsx"
    assert p2["output"]["latest_name"] == "Monitoring_Proses2_LATEST.xlsx"
    assert "proses1" in p1["output"]["output_dir"]
    assert p1["state_file"] != p2["state_file"]


def test_resolve_keeps_global_config_intact():
    base = base_cfg()
    processes.resolve(base, "proses1")
    assert "process_key" not in base
    assert base["columns"]["jam_mulai"] == "JAM MULAI"


def test_workbook_optional_only_for_proses1():
    p1 = processes.resolve(base_cfg(), "1")
    p2 = processes.resolve(base_cfg(), "2")
    assert p1["workbook_optional"] == {"plug_assist": False, "tunggu_bahan": False}
    assert not (p2.get("workbook_optional") or {})


def test_both_processes_configured():
    base = base_cfg()
    assert processes.is_configured(base, "proses1")
    assert processes.is_configured(base, "proses2")


def test_available_lists_two_processes():
    labels = dict(processes.available(base_cfg()))
    assert labels["proses1"] == "Proses 1"
    assert labels["proses2"] == "Proses 2"
