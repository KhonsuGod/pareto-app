"""Akses Google Sheet admin Proses 2.

Dua metode (config: google.fetcher):
    xlsx_export - export publik tanpa credential (default, paling sederhana & stabil)
    gspread     - pakai service account JSON di GOOGLE_CREDENTIALS_FILE

File yang sukses diunduh disimpan ke cache: data/cache/admin_<id>.xlsx.
Jika unduhan gagal (offline), fallback otomatis ke cache terakhir.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import shutil
import urllib.request
from pathlib import Path

import openpyxl


class SourceData:
    def __init__(self, rows: list[list], sheet_name: str, offline_cache: bool, meta: dict):
        self.rows = rows              # list baris values (row0 = header)
        self.sheet_name = sheet_name
        self.offline_cache = offline_cache
        self.meta = meta


def load_downtime(cfg: dict, verbose: bool = False) -> SourceData:
    method = cfg["google"].get("fetcher", "auto")
    if method == "gspread":
        return _load_gspread(cfg)
    return _load_xlsx_export(cfg)


# --------------------------------------------------------------------------- #
# Metode 1: export xlsx publik
# --------------------------------------------------------------------------- #
def _cache_path(cfg: dict) -> Path:
    cache_dir = Path(cfg["output"]["cache_dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    sid = cfg["google"].get("spreadsheet_id", "unknown").strip() or "unknown"
    return cache_dir / f"admin_{sid}.xlsx"


def _load_xlsx_export(cfg: dict) -> SourceData:
    sid = (cfg["google"].get("spreadsheet_id") or "").strip()
    if not sid:
        raise RuntimeError(
            "Spreadsheet ID kosong. Isi ADMIN_SHEET_URL / ADMIN_SPREADSHEET_ID di .env, "
            "atau google.spreadsheet_id / sheet_url di config.yaml.")
    url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"
    timeout = int(cfg["google"].get("timeout_seconds", 60))
    cache = _cache_path(cfg)
    tmp = cache.with_suffix(".tmp")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (proses2-monitor)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        with open(tmp, "wb") as fh:
            fh.write(data)
        shutil.move(tmp, cache)
        offline = False
    except Exception as exc:
        if not cache.exists():
            raise RuntimeError(f"Tidak bisa mengakses Google Sheet ({exc}) dan cache kosong.") from exc
        offline = True

    wb = openpyxl.load_workbook(cache, read_only=True, data_only=True)
    sheet_name = _find_sheet(wb, cfg["google"].get("sheet_name", "DOWNTIME"))
    ws = wb[sheet_name]
    rows = [[v for v in row] for row in ws.iter_rows(values_only=True)]
    rows = _trim(rows)
    return SourceData(rows, sheet_name, offline_cache=offline,
                      meta={"source": "xlsx_export", "id": sid, "file": str(cache)})


def _find_sheet(wb, wanted: str) -> str:
    wanted_u = wanted.strip().upper()
    for ws in wb.worksheets:
        if ws.title.strip().upper() == wanted_u:
            return ws.title
    raise RuntimeError(f"Tab '{wanted}' tidak ditemukan. Tab tersedia: {[w.title for w in wb.worksheets]}")


def _trim(rows: list[list]) -> list[list]:
    """Buang baris yang seluruh selnya kosong."""
    out = []
    for row in rows:
        if any(v not in (None, "") for v in row):
            out.append(row)
    return out


# --------------------------------------------------------------------------- #
# Metode 2: gspread + service account
# --------------------------------------------------------------------------- #
def _load_gspread(cfg: dict) -> SourceData:
    cred_file = cfg["google"].get("credentials_file", "")
    sid = (cfg["google"].get("spreadsheet_id") or "").strip()
    if not cred_file or not Path(cred_file).exists():
        raise RuntimeError(f"GOOGLE_CREDENTIALS_FILE tidak ditemukan: '{cred_file}'")
    if not sid:
        raise RuntimeError("Spreadsheet ID kosong (.env / config.yaml).")
    import gspread  # lazy import

    gc = gspread.service_account(filename=str(cred_file))
    sh = gc.open_by_key(sid)
    sheet_name = cfg["google"].get("sheet_name", "DOWNTIME")
    try:
        ws = sh.worksheet(sheet_name)
    except Exception:
        titles = [s.title for s in sh.worksheets()]
        raise RuntimeError(f"Tab '{sheet_name}' tidak ditemukan. Tab tersedia: {titles}")
    rows = ws.get_all_values()
    return SourceData(rows, sheet_name, offline_cache=False,
                      meta={"source": "gspread", "id": sid})
