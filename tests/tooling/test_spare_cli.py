"""Test perintah CLI Tool 2 (tanpa jaringan, tanpa animasi)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as appmod  # noqa: E402

from tests.tooling.fixture import make_store  # noqa: E402


def _cli_cfg(tmp_path):
    store, wb_path = make_store(tmp_path)
    return {"spare": {
        "workbook": str(wb_path),
        "source_workbook": "",
        "backup_dir": str(tmp_path / "backups"),
        "backup_keep": 3,
        "state_file": str(tmp_path / "state.json"),
        "minimum_stock": {},
    }}, store


def test_cli_tooling_find_smoke(tmp_path, capsys):
    cfg, _ = _cli_cfg(tmp_path)
    # stub load_config supaya CLI memakai workbook uji
    orig = appmod.load_config
    appmod.load_config = lambda: cfg
    try:
        code = appmod.main(["tooling", "find", "BJ-PP00246-0"])
    finally:
        appmod.load_config = orig
    assert code == 0
    out = capsys.readouterr().out
    assert "CUP-16" in out and "CLEAR COLD CUP 16 OZ" in out


def test_cli_spare_status_smoke(tmp_path, capsys):
    cfg, _ = _cli_cfg(tmp_path)
    orig = appmod.load_config
    appmod.load_config = lambda: cfg
    try:
        code = appmod.main(["spare", "status"])
    finally:
        appmod.load_config = orig
    assert code == 0
    assert "Stock belum diinput" in capsys.readouterr().out


def test_cli_spare_pareto_empty_month(tmp_path, capsys):
    cfg, _ = _cli_cfg(tmp_path)
    orig = appmod.load_config
    appmod.load_config = lambda: cfg
    try:
        code = appmod.main(["spare", "pareto", "month"])
    finally:
        appmod.load_config = orig
    assert code == 0
    assert "Belum ada transaksi" in capsys.readouterr().out


def test_cli_help_lists_new_commands(capsys):
    try:
        appmod.main(["--help"])
    except SystemExit:
        pass
    out = capsys.readouterr().out
    for token in ("tooling", "spare", "update", "draft", "status", "validate", "init"):
        assert token in out, token
