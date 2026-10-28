"""Draft pesan WhatsApp dari angka aktual workbook.

Semua kalimat dibentuk dari data: mesin teratas + penyebab dominan per mesin
(hasil keyword mapping di config.message.drivers). Tidak ada teks karangan.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict

from . import pareto


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def fmt_minutes(minutes: int | float) -> str:
    """180 -> '180' ; 1440 -> '1.440' (format Indonesia)."""
    return f"{int(round(minutes)):,}".replace(",", ".")


def _join_top(rows: list[dict]) -> str:
    """'A = 1 menit, lanjut B = 2 menit, C = 3 menit, dan D = 4 menit.'"""
    parts = [f"{r['name']} = {fmt_minutes(r['minutes'])} menit" for r in rows]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} dan {parts[1]}"
    if len(parts) == 3:
        return f"{parts[0]}, lanjut {parts[1]}, dan {parts[2]}"
    return f"{parts[0]}, lanjut {parts[1]}, " + ", ".join(parts[2:-1]) + f", dan {parts[-1]}"


def _join_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} dan {items[1]}"
    return ", ".join(items[:-1]) + f", dan {items[-1]}"


def _phrase_from_text(text: str, limit: int = 46) -> str:
    """Deskripsi asli sebagai penyebab, dipotong di batas kata."""
    t = re.sub(r"\s+", " ", str(text or "")).strip(" .;-").lower()
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0]
    return t


def _rules(cfg: dict) -> list[tuple[str, list[str]]]:
    out = []
    for rule in ((cfg.get("message") or {}).get("drivers") or []):
        phrase = str(rule.get("phrase") or "").strip()
        kws = [_norm(k) for k in (rule.get("keywords") or []) if k]
        if phrase and kws:
            out.append((phrase, kws))
    return out


def machine_drivers(machine_events: list[dict], cfg: dict, limit: int = 4) -> list[str]:
    """Penyebab dominan satu mesin pada satu hari, urut menit terbesar.

    Urutan sumber: keyword spesifik di config.message.drivers, lalu label
    issue (issue_mapping), lalu deskripsi asli kalau labelnya "Other".
    """
    rules = _rules(cfg)
    minutes: dict[str, int] = defaultdict(int)
    for ev in machine_events:
        text = _norm(ev.get("keterangan", ""))
        phrase = None
        for candidate, keywords in rules:
            if any(kw in text for kw in keywords):
                phrase = candidate
                break
        if phrase is None:
            label = _phrase_from_text(ev.get("issue_label") or "")
            if label and label != "other":
                phrase = label
            else:
                phrase = _phrase_from_text(ev.get("keterangan"))
        if phrase:
            minutes[phrase] += int(ev.get("menit") or 0)
    ranked = sorted(minutes.items(), key=lambda kv: (-kv[1], kv[0]))
    return [name for name, _mins in ranked[:limit]]


def build(events: list[dict], target: dt.date, cfg: dict) -> str:
    """Teks draft siap kirim (string)."""
    msg = cfg.get("message") or {}
    day_events = [e for e in events if e.get("date") == target]
    if not day_events:
        return ""

    top_n = int(msg.get("top_machines", 4))
    driver_n = int(msg.get("driver_machines", 2))
    per_machine = int(msg.get("drivers_per_machine", 4))

    pareto_rows = pareto.pareto_machine(day_events)
    top = pareto_rows[:top_n]

    header = str(msg.get("header") or "Update Pareto {label} Pak {recipient} Di tanggal {day}:")
    header = header.format(
        label=cfg.get("process_label", "Proses 2"),
        recipient=msg.get("recipient", ""),
        day=target.day,
        date=target.isoformat(),
        month=target.strftime("%B"),
    )

    lines: list[str] = [header, ""]
    if top:
        lines.append(f"Downtime tertinggi ada di {_join_top(top)}.")
        lines.append("")

    # Penyebab dominan untuk mesin teratas (maks. driver_n mesin).
    by_machine: dict[str, list[dict]] = defaultdict(list)
    for ev in day_events:
        by_machine[ev.get("machine_raw") or "-"].append(ev)

    sentences: list[str] = []
    for row in top[:driver_n]:
        drivers = machine_drivers(by_machine.get(row["name"], []), cfg, per_machine)
        if not drivers:
            continue
        if len(drivers) == 1:
            sentences.append(f"{row['name']} karena {drivers[0]}.")
        else:
            sentences.append(f"{row['name']} banyak dari {_join_list(drivers)}.")
    if sentences:
        lines.append(" ".join(sentences))
        lines.append("")

    lines.append(str(msg.get("closing") or "Tolong dibantu follow up yang masih berulang."))
    cc = str(msg.get("cc") or "").strip()
    if cc:
        lines.append("")
        lines.append(f"CC {cc}")

    return "\n".join(lines).rstrip() + "\n"


def build_from_workbook(cfg: dict, target: dt.date | None = None) -> tuple[str, dt.date]:
    """Baca workbook proses aktif lalu buat draft tanggal terakhir (atau target)."""
    from . import workbook

    events = workbook.read_events(cfg)
    if not events:
        raise RuntimeError("Workbook belum berisi data downtime. Jalankan update dulu.")
    target = target or max(e["date"] for e in events)
    text = build(events, target, cfg)
    if not text:
        raise RuntimeError(f"Tidak ada data downtime untuk {target.isoformat()}.")
    return text, target
