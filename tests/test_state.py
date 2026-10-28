"""Test state file per proses."""
from __future__ import annotations

from src import state


def test_state_path_uses_state_file(tmp_path):
    cfg = {"output": {"cache_dir": str(tmp_path / "cache")},
           "state_file": str(tmp_path / "s" / "state_proses1.json")}
    path = state.state_path(cfg)
    assert path == tmp_path / "s" / "state_proses1.json"
    assert path.parent.is_dir()


def test_state_path_falls_back_to_cache_dir(tmp_path):
    cfg = {"output": {"cache_dir": str(tmp_path / "cache")}}
    assert state.state_path(cfg) == tmp_path / "cache" / "state.json"


def test_update_and_load_roundtrip(tmp_path):
    cfg = {"output": {"cache_dir": str(tmp_path / "cache")},
           "state_file": str(tmp_path / "cache" / "state_p1.json")}
    state.update(cfg, command="update daily", status="ok",
                 message="Processed 2026-10-27", processed_date="2026-10-27")
    data = state.load(cfg)
    assert data["status"] == "ok"
    assert data["processed_dates"] == ["2026-10-27"]
