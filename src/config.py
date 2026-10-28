"""Loader konfigurasi (config.yaml + .env)."""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

SPREADSHEET_ID_RE = re.compile(r"/d/([A-Za-z0-9_-]{10,})")


def _resolve(p: str | None) -> Path:
    if p is None:
        return ROOT
    path = Path(p)
    return path if path.is_absolute() else (ROOT / path)


def load_config(path: str | None = None, verbose: bool = False) -> dict:
    load_dotenv(_resolve(".env") if _resolve(".env").exists() else None)
    cfg_path = _resolve(path) if path else _resolve("config.yaml")
    with open(cfg_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    google = cfg.setdefault("google", {})
    sheet_url = os.getenv("ADMIN_SHEET_URL", "") or google.get("sheet_url", "")
    spreadsheet_id = os.getenv("ADMIN_SPREADSHEET_ID", "") or google.get("spreadsheet_id", "")
    if not spreadsheet_id and sheet_url:
        m = SPREADSHEET_ID_RE.search(sheet_url)
        if m:
            spreadsheet_id = m.group(1)
    google["spreadsheet_id"] = spreadsheet_id
    google["credentials_file"] = os.getenv("GOOGLE_CREDENTIALS_FILE", "") or google.get("credentials_file", "")

    out = cfg.setdefault("output", {})
    for key in ("template", "output_dir", "backup_dir", "cache_dir"):
        out[key] = str(_resolve(out.get(key, f"data/{key.replace('_dir','')}") if key != "template"
                                else out.get(key, "data/template/Template_Monitoring_Proses2.xlsx")))
    return cfg


def out(cfg: dict, key: str, default: str = "") -> str:
    v = cfg.get("output", {}).get(key)
    return v if v else default
