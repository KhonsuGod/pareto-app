"""Resolusi konfigurasi per proses (Proses 1 / Proses 2).

config.yaml menyimpan konfigurasi umum di root dan override per proses di
`processes.<key>`. `resolve()` mengembalikan salinan config yang sudah
"dipersonalisasi" sehingga modul lain (google_sheet, workbook, dst.) tidak
perlu tahu soal multi-proses.
"""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPREADSHEET_ID_RE = re.compile(r"/d/([A-Za-z0-9_-]{10,})")

# Key yang boleh dioverride per proses (sisanya global).
OVERRIDABLE = (
    "columns",
    "date",
    "kategori_labels",
    "machine_grouping",
    "issue_mapping",
    "followup",
    "ringkasan",
    "message",
    "workbook_optional",
    "sheet_header_row",
)

ALIASES = {
    "1": "proses1", "proses1": "proses1", "proses 1": "proses1", "p1": "proses1",
    "2": "proses2", "proses2": "proses2", "proses 2": "proses2", "p2": "proses2",
}


def _abs(path: str | None) -> str | None:
    if not path:
        return path
    p = Path(path)
    return str(p if p.is_absolute() else (ROOT / p))


def normalize_key(key: str | None, cfg: dict | None = None) -> str:
    """'1' / 'proses 1' / 'p1' -> 'proses1'."""
    if not key:
        if cfg:
            return cfg.get("default_process", "proses2")
        return "proses2"
    k = str(key).strip().lower()
    if k in ALIASES:
        return ALIASES[k]
    if cfg and k in (cfg.get("processes") or {}):
        return k
    raise KeyError(f"Proses tidak dikenal: '{key}'. Pilihan: 1 / 2.")


def available(cfg: dict) -> list[tuple[str, str]]:
    procs = cfg.get("processes") or {}
    return [(k, (v or {}).get("label", k)) for k, v in procs.items()]


def is_configured(cfg: dict, key: str) -> bool:
    p = (cfg.get("processes") or {}).get(key) or {}
    return bool(_spreadsheet_id(cfg, key, p))


def _spreadsheet_id(cfg: dict, key: str, p: dict) -> str:
    env_id = os.getenv(p.get("env_id", ""), "").strip()
    if env_id:
        return env_id
    env_url = os.getenv(p.get("env_url", ""), "").strip()
    if env_url:
        m = SPREADSHEET_ID_RE.search(env_url)
        if m:
            return m.group(1)
    sid = (p.get("spreadsheet_id") or "").strip()
    if sid:
        return sid
    url = (p.get("sheet_url") or "").strip()
    m = SPREADSHEET_ID_RE.search(url)
    return m.group(1) if m else ""


def resolve(cfg: dict, key: str | None = None) -> dict:
    """Config yang sudah disesuaikan untuk satu proses."""
    key = normalize_key(key, cfg)
    procs = cfg.get("processes") or {}
    proc = procs.get(key)
    if not proc:
        raise KeyError(f"Proses '{key}' belum ada di config.yaml (processes.{key}).")

    out = copy.deepcopy(cfg)
    out["process_key"] = key
    out["process_label"] = proc.get("label", key.upper())
    out["process_short"] = proc.get("short", key)

    # Override blok global (dictionary digabung, bukan ditimpa total).
    for field in OVERRIDABLE:
        if field in proc:
            base = out.get(field)
            if isinstance(base, dict) and isinstance(proc[field], dict):
                merged = copy.deepcopy(base)
                merged.update(copy.deepcopy(proc[field]))
                out[field] = merged
            else:
                out[field] = copy.deepcopy(proc[field])

    # Google Sheet
    google = {**(cfg.get("google") or {})}
    google["spreadsheet_id"] = _spreadsheet_id(cfg, key, proc)
    google["sheet_name"] = proc.get("sheet_name", google.get("sheet_name", "DOWNTIME"))
    out["google"] = google

    # Output & template khusus proses
    output = {**(cfg.get("output") or {})}
    output.update(copy.deepcopy(proc.get("output") or {}))
    for k in ("template", "output_dir", "backup_dir", "cache_dir"):
        if k in output:
            output[k] = _abs(output[k])
    if not output.get("template"):
        output["template"] = _abs(f"data/template/Template_{key.capitalize()}.xlsx")
    out["output"] = output
    out["state_file"] = _abs(proc.get("state_file", f"data/cache/state_{key}.json"))
    return out


def describe(cfg: dict, key: str | None = None) -> str:
    """Label singkat untuk ditampilkan di CLI, mis. 'Proses 2 / Bolang'."""
    key = normalize_key(key, cfg)
    p = (cfg.get("processes") or {}).get(key) or {}
    return p.get("label", key)
