from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from src.config import load_config


def base_cfg() -> dict:
    return load_config()


def make_event(date="2026-10-27", machine="TFM 1", kode="BJ-PP00001-0",
               nama="Cup PP 16 oz", jam_mulai="08:00", jam_selesai="09:00",
               menit=60, keterangan="tunggu bahan", kategori="B", issue_label=None,
               issue_group=None) -> dict | None:
    """Event sintetis untuk unit test (BUKAN data produksi)."""
    from src import extractor
    from src.issue_mapper import IssueMapper
    ev = {
        "date": date if isinstance(date, dt.date) else dt.datetime.strptime(str(date), "%Y-%m-%d").date(),
        "machine_raw": machine,
        "machine": machine,
        "kode_barang": kode,
        "nama_produk": nama,
        "jam_mulai": extractor.parse_time(jam_mulai),
        "jam_selesai": extractor.parse_time(jam_selesai),
        "menit": menit,
        "keterangan": keterangan,
        "kategori": kategori,
    }
    from src.extractor import machine_group
    ev["machine_group"] = machine_group(machine)
    ev["event_key"] = extractor.event_key(ev)
    if issue_label is None:
        m = IssueMapper(base_cfg())
        issue_group, issue_label = m.map_text(keterangan)
    ev["issue_group"] = issue_group
    ev["issue_label"] = issue_label
    return ev


def tiny_cfg(tmp_path: Path) -> dict:
    """Config minimal, semua path ke direktori test sementara."""
    cfg = base_cfg()
    cfg["output"] = {
        "template": str(tmp_path / "template" / "Template_Monitoring_Proses2.xlsx"),
        "output_dir": str(tmp_path / "out"),
        "latest_name": "Monitoring_Proses2_LATEST.xlsx",
        "dated_name": "Monitoring_Proses2_{date}.xlsx",
        "backup_dir": str(tmp_path / "out" / "backups"),
        "backup_keep": 10,
        "cache_dir": str(tmp_path / "cache"),
    }
    return cfg


import pytest  # noqa: E402


@pytest.fixture()
def cfg_tiny(tmp_path) -> dict:
    return tiny_cfg(tmp_path)
