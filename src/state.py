"""State pipeline kecil (data/cache/state.json) untuk command status."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import workbook as wbmod


def state_path(cfg: dict) -> Path:
    """Satu file state per proses (config: processes.<key>.state_file)."""
    custom = cfg.get("state_file")
    if custom:
        p = Path(custom)
    else:
        p = Path(cfg["output"].get("cache_dir", "data/cache")) / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load(cfg: dict) -> dict:
    p = state_path(cfg)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def update(cfg: dict, command: str, status: str, message: str, processed_date: str | None = None) -> None:
    data = load(cfg)
    data.update({
        "time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "command": command,
        "status": status,
        "message": message,
    })
    if processed_date:
        data["processed_dates"] = sorted(set(data.get("processed_dates", [])) | {processed_date})
    state_path(cfg).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def last_processed_date(cfg: dict) -> str | None:
    """Last processed date diambil dari workbook DETAIL_DOWNTIME (sumber kebenaran)."""
    if not wbmod.find_current_workbook(cfg):
        st = load(cfg)
        dates = st.get("processed_dates") or []
        return dates[-1] if dates else None
    try:
        dates = wbmod.read_processed_dates(cfg)
        return max(dates).isoformat() if dates else None
    except Exception:
        return None
