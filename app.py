#!/usr/bin/env python3
"""PROSES-MONITOR - CLI monitoring downtime Proses 1 & Proses 2 (Bolang).

Tanpa argumen  : menu interaktif
    python app.py

Perintah:
    python app.py update daily [--proses 1|2] [--latest | --date YYYY-MM-DD]
    python app.py draft [--proses 1|2] [--date YYYY-MM-DD] [--clip]
    python app.py status [--proses 1|2]
    python app.py validate [--proses 1|2]
    python app.py init [--proses 1|2] [--force]
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import (  # noqa: E402
    downtime as dow,
    extractor,
    google_sheet,
    logger,
    menu,
    message,
    pareto,
    processes,
    state,
    validator,
    workbook,
)
from src.config import load_config  # noqa: E402
from src.issue_mapper import IssueMapper  # noqa: E402


def _fmt_date(d: dt.date) -> str:
    return d.isoformat()


def _cfg(key: str | None) -> dict:
    """Config yang sudah disesuaikan untuk satu proses."""
    return processes.resolve(load_config(), key)


def _parse_date_arg(cfg: dict, text: str | None) -> dt.date | None:
    if not text:
        return None
    try:
        return dt.datetime.strptime(text, cfg["date"].get("input_format", "%Y-%m-%d")).date()
    except ValueError:
        raise SystemExit(f"Format tanggal tidak valid: {text} (gunakan YYYY-MM-DD)")


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #
def cmd_init(args) -> int:
    cfg = _cfg(getattr(args, "proses", None))
    path = workbook.ensure_template(cfg, force=getattr(args, "force", False))
    if path:
        logger.ok(f"Template {cfg['process_label']} dibuat:\n       {path}")
    else:
        logger.ok(f"Template {cfg['process_label']} sudah ada (pakai --force untuk menimpa).")
    return 0


# --------------------------------------------------------------------------- #
# update daily
# --------------------------------------------------------------------------- #
def _determine_target(cfg: dict, events: list, processed: set, args) -> dt.date | None:
    src_dates = sorted({e["date"] for e in events})
    if not src_dates:
        return None
    if getattr(args, "date", None):
        target = _parse_date_arg(cfg, args.date)
        if target not in src_dates:
            raise SystemExit(f"Tanggal {args.date} tidak ada di sheet sumber {cfg['process_label']}.")
        return target
    if getattr(args, "latest", False):
        return src_dates[-1]
    unprocessed = [d for d in src_dates if d not in processed]
    return unprocessed[-1] if unprocessed else None


def cmd_update(args) -> int:
    cfg = _cfg(getattr(args, "proses", None))
    key = cfg["process_key"]
    logger.ok(f"Proses: {cfg['process_short']}")

    if not processes.is_configured(cfg, key):
        logger.err(f"Sumber data {cfg['process_label']} belum dikonfigurasi "
                   f"(processes.{key}.spreadsheet_id di config.yaml).")
        return 2

    try:
        raw = google_sheet.load_downtime(cfg, verbose=getattr(args, "verbose", False))
    except Exception as exc:
        state.update(cfg, command="update daily", status="error", message=f"Gagal ambil source: {exc}")
        logger.err(f"Gagal mengambil sheet sumber: {exc}")
        return 3
    if raw.offline_cache:
        logger.warn("Koneksi gagal, memakai cache terakhir (data mungkin belum terbaru).")
    else:
        logger.ok("Connected to Google Sheet")

    events = extractor.dedup_events(extractor.extract_events(raw.rows, cfg))
    IssueMapper(cfg).apply(events)
    if not events:
        logger.err("Sheet downtime kosong / tidak dapat dibaca.")
        return 1
    src_dates = sorted({e["date"] for e in events})
    logger.ok(f"Latest date found: {_fmt_date(src_dates[-1])}")
    logger.ok(f"Source: {len(events)} downtime events "
              f"({_fmt_date(src_dates[0])} s/d {_fmt_date(src_dates[-1])})")

    processed = workbook.read_processed_dates(cfg)
    target = _determine_target(cfg, events, processed, args)
    if target is None:
        logger.ok("No new daily downtime data found.")
        state.update(cfg, command="update daily", status="ok",
                     message="No new daily downtime data found.")
        return 0
    already = target in processed
    logger.ok(f"Processing date: {_fmt_date(target)}" + ("  (replace / upsert)" if already else "  (new)"))

    day_events = extractor.dedup_events(extractor.day_events(events, target))
    if not day_events:
        logger.err(f"Tidak ada event downtime valid untuk {_fmt_date(target)}.")
        return 1
    for msg in extractor.invalid_rows(events, target)[:5]:
        logger.warn(f"Baris tidak valid: {msg}")
    total_minute = sum(e["menit"] for e in day_events)
    logger.ok(f"{len(day_events)} downtime events untuk {_fmt_date(target)}")
    logger.ok(f"Total downtime: {total_minute} menit")

    base = workbook.read_events(cfg)
    merged = extractor.dedup_events([e for e in base if e["date"] != target] + day_events)

    cur = [e for e in merged if e["date"] == target]
    pareto_mesin = pareto.pareto_machine(cur)
    pareto_issue = pareto.pareto_issue(cur)
    trend = dow.trend_rows(merged)
    rekap = dow.rekap_machine_rows(merged, cfg)
    summary = dow.summary(merged, target)
    followup = dow.followup_rows(merged, target, cfg)

    wb = workbook.load_or_create(cfg)
    workbook.build_sheets(wb, cfg, merged=merged, target=target,
                          pareto_mesin=pareto_mesin, pareto_issue=pareto_issue,
                          trend=trend, rekap=rekap, summary=summary, followup=followup)
    workbook.apply_charts(wb, cfg)
    workbook.finalize(wb, cfg)

    errors = validator.validate_workbook(wb, cfg, target=target)
    if errors:
        state.update(cfg, command="update daily", status="error", message="; ".join(errors))
        logger.err("VALIDASI GAGAL - workbook tidak disimpan, LATEST tidak diubah:")
        for e in errors:
            logger.err(f"  - {e}")
        return 1
    logger.ok("Pareto machine updated")
    logger.ok("Pareto issue updated")
    logger.ok("Trend harian updated")
    logger.ok("Workbook validation passed")

    dated_path, latest_path = workbook.save_workbook(wb, cfg, target)
    state.update(cfg, command="update daily", status="ok",
                 message=f"Processed {_fmt_date(target)}: {len(day_events)} events / {total_minute} menit",
                 processed_date=_fmt_date(target))
    logger.ok("Saved:")
    for p in (dated_path, latest_path):
        try:
            logger.ok(f"       {p.relative_to(ROOT)}")
        except ValueError:
            logger.ok(f"       {p}")
    return 0


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #
def _status_one(base_cfg: dict, key: str) -> int:
    cfg = processes.resolve(base_cfg, key)
    st = state.load(cfg)
    try:
        processed = workbook.read_processed_dates(cfg)
        last_proc = max(processed).isoformat() if processed else None
    except Exception:
        last_proc = None
    latest_src = None
    try:
        raw = google_sheet.load_downtime(cfg)
        events = extractor.extract_events(raw.rows, cfg)
        if events:
            latest_src = max(e["date"] for e in events)
    except Exception as exc:
        print(f"  [WARN] source tidak dapat dibaca: {exc}")
    wb_path = workbook.find_current_workbook(cfg)

    print(f"\n  {cfg['process_short']}")
    print(f"    Last processed date : {last_proc or '-'}")
    print(f"    Latest source date  : {latest_src.isoformat() if latest_src else '-'}")
    print(f"    Current workbook    : {wb_path if wb_path else '-'}")
    print(f"    Last update status  : {st.get('status', '-')}")
    print(f"    Last update time    : {st.get('time', '-')}")
    print(f"    Last update message : {st.get('message', '-')}")
    return 0


def cmd_status(args) -> int:
    base = load_config()
    print("STATUS PROSES-MONITOR")
    if getattr(args, "proses", None):
        keys = [processes.normalize_key(args.proses, base)]
    else:
        keys = [k for k, _ in processes.available(base)]
    for key in keys:
        _status_one(base, key)
    return 0


# --------------------------------------------------------------------------- #
# draft pesan
# --------------------------------------------------------------------------- #
def _save_draft(cfg: dict, text: str, target: dt.date) -> Path:
    out_dir = Path(cfg["output"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"Draft_WhatsApp_{cfg['process_label'].replace(' ', '')}_{target.isoformat()}.txt"
    path = out_dir / name
    path.write_text(text, encoding="utf-8")
    return path


def _copy_clipboard(text: str) -> bool:
    try:
        subprocess.run("clip", input=text, text=True, shell=True, check=True)
        return True
    except Exception:
        return False


def cmd_draft(args) -> int:
    cfg = _cfg(getattr(args, "proses", None))
    target = _parse_date_arg(cfg, getattr(args, "date", None))
    try:
        text, target = message.build_from_workbook(cfg, target)
    except Exception as exc:
        logger.err(str(exc))
        return 1

    print(f"\nDRAFT PESAN - {cfg['process_short']} - {dow.short_date(target)} {target.year}")
    print("-" * 64)
    print(text, end="")
    print("-" * 64)
    path = _save_draft(cfg, text, target)
    logger.ok(f"Disimpan: {path}")
    if getattr(args, "clip", False):
        logger.ok("Disalin ke clipboard." if _copy_clipboard(text) else "Gagal menyalin ke clipboard.")
    return 0


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #
def cmd_validate(args) -> int:
    cfg = _cfg(getattr(args, "proses", None))
    path = workbook.find_current_workbook(cfg)
    if path is None:
        logger.err(f"Belum ada workbook {cfg['process_label']} di {cfg['output']['output_dir']}.")
        return 1
    logger.ok(f"Validating: {path.name}")
    import openpyxl
    wb = openpyxl.load_workbook(path)
    errors = validator.validate_workbook(wb, cfg, wpath=path)
    if errors:
        logger.err("Workbook TIDAK valid:")
        for e in errors:
            logger.err(f"  - {e}")
        state.update(cfg, command="validate", status="error", message="; ".join(errors))
        return 1
    logger.ok("Workbook validation passed")
    state.update(cfg, command="validate", status="ok", message="Workbook valid.")
    return 0


# --------------------------------------------------------------------------- #
# menu callbacks
# --------------------------------------------------------------------------- #
class _Args:
    def __init__(self, **kw):
        self.proses = kw.get("proses")
        self.date = kw.get("date")
        self.latest = kw.get("latest", False)
        self.verbose = kw.get("verbose", False)
        self.force = kw.get("force", False)
        self.clip = kw.get("clip", False)


def _menu_update(key: str, date: str | None) -> None:
    cmd_update(_Args(proses=key, date=date))


def _menu_status() -> None:
    cmd_status(_Args())


def _menu_draft(key: str, date: str | None) -> None:
    cfg = _cfg(key)
    target = _parse_date_arg(cfg, date)
    text, target = message.build_from_workbook(cfg, target)
    print(f"\nDRAFT PESAN - {cfg['process_short']} - {dow.short_date(target)} {target.year}")
    print("-" * 64)
    print(text, end="")
    print("-" * 64)
    path = _save_draft(cfg, text, target)
    print(f"  Disimpan: {path}")
    try:
        if input("  Salin ke clipboard? [y/N]: ").strip().lower() == "y":
            print("  Disalin." if _copy_clipboard(text) else "  Gagal menyalin.")
    except EOFError:
        pass


def _menu_validate(key: str) -> None:
    cmd_validate(_Args(proses=key))


def _menu_open_output(key: str) -> None:
    cfg = _cfg(key)
    out_dir = Path(cfg["output"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    import os
    os.startfile(out_dir)  # type: ignore[attr-defined]
    print(f"  Membuka {out_dir}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _add_proses(p) -> None:
    p.add_argument("--proses", metavar="1|2", help="proses yang dipakai (default: config)")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        logger.init(False)
        cfg = load_config()
        return menu.run(cfg, {
            "update": _menu_update,
            "status": _menu_status,
            "draft": _menu_draft,
            "validate": _menu_validate,
            "open_output": _menu_open_output,
        })

    ap = argparse.ArgumentParser(
        prog="python app.py",
        description="Daily monitoring downtime Proses 1 & Proses 2 / Bolang",
        epilog="contoh:\n  python app.py\n  python app.py update daily --proses 2\n"
               "  python app.py draft --proses 2 --clip\n  python app.py status",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verbose", action="store_true", help="log debug lengkap")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="buat template workbook")
    _add_proses(p_init)
    p_init.add_argument("--force", action="store_true", help="timpa template yang ada")
    p_init.set_defaults(func=cmd_init)

    p_up = sub.add_parser("update", help="perbarui workbook monitoring")
    up_sub = p_up.add_subparsers(dest="update_cmd", required=True)
    p_daily = up_sub.add_parser("daily", help="update harian")
    _add_proses(p_daily)
    p_daily.add_argument("--latest", action="store_true", help="proses tanggal terbaru source (upsert)")
    p_daily.add_argument("--date", metavar="YYYY-MM-DD", help="upsert tanggal tertentu")
    p_daily.set_defaults(func=cmd_update)

    p_draft = sub.add_parser("draft", help="buat draft pesan WhatsApp")
    _add_proses(p_draft)
    p_draft.add_argument("--date", metavar="YYYY-MM-DD", help="tanggal draft (default: terakhir)")
    p_draft.add_argument("--clip", action="store_true", help="salin hasil ke clipboard")
    p_draft.set_defaults(func=cmd_draft)

    p_val = sub.add_parser("validate", help="validasi workbook")
    _add_proses(p_val)
    p_val.set_defaults(func=cmd_validate)

    p_st = sub.add_parser("status", help="status pipeline")
    _add_proses(p_st)
    p_st.set_defaults(func=cmd_status)

    args = ap.parse_args(argv)
    logger.init(verbose=bool(getattr(args, "verbose", False)))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
