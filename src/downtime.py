"""Kalkulasi downtdaily: rekap, trend, ringkasan, follow-up (deterministic, tanpa AI)."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

MONTH_ABBR_ID = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
    7: "Jul", 8: "Agt", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des",
}


def short_date(d: dt.date) -> str:
    """'2026-10-27' -> '27 Okt' (numerik dari tanggal, bukan teks AI)."""
    return f"{d.day:02d} {MONTH_ABBR_ID[d.month]}"


def daily_totals(events: list[dict]) -> dict[dt.date, dict]:
    out: dict[dt.date, dict] = {}
    for e in events:
        d = out.setdefault(e["date"], {"events": 0, "minutes": 0})
        d["events"] += 1
        d["minutes"] += e["menit"]
    return dict(sorted(out.items()))


def daily_minutes(events: list[dict], d: dt.date) -> int:
    return sum(e["menit"] for e in events if e["date"] == d)


def daily_count(events: list[dict], d: dt.date) -> int:
    return sum(1 for e in events if e["date"] == d)


def per_machine_minutes(events: list[dict], d: dt.date) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in events:
        if e["date"] != d:
            continue
        out[e["machine_raw"]] = out.get(e["machine_raw"], 0) + e["menit"]
    return out


def per_issue_minutes(events: list[dict], d: dt.date) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in events:
        if e["date"] != d:
            continue
        label = e.get("issue_label") or "-"
        out[label] = out.get(label, 0) + e["menit"]
    return out


def machine_top_issue(events: list[dict], d: dt.date, machine: str) -> tuple[str, int] | None:
    """Issue dominan sebuah mesin pada tanggal tertentu (untuk kolom Issue follow-up)."""
    out: dict[str, int] = defaultdict(int)
    for e in events:
        if e["date"] == d and e["machine_raw"] == machine:
            label = e.get("issue_label") or "-"
            out[label] += e["menit"]
    if not out:
        return None
    top = max(out.items(), key=lambda kv: (kv[1], kv[0]))
    return top[0], top[1]


def _dominant(dist: dict[str, int]) -> tuple[str | None, int]:
    """Item terbesar; tie-break nama asc (deterministic)."""
    if not dist:
        return None, 0
    top = max(dist.items(), key=lambda kv: (kv[1], kv[0]))
    return top[0], top[1]


def trend_rows(events: list[dict]) -> list[dict]:
    """TREND_HARIAN: Tanggal | Event | Menit, satu baris per tanggal (urut, unik)."""
    totals = daily_totals(events)
    return [{"date": d, "events": v["events"], "minutes": v["minutes"]} for d, v in totals.items()]


def rekap_machine_rows(events: list[dict], cfg: dict | None = None) -> list[dict]:
    """REKAP_MESIN: per tanggal x mesin, + breakdown kategori A..G."""
    kats = list((cfg or {}).get("kategori_labels", {}) or
                {"A": "MTC", "B": "PRD", "C": "TS", "D": "BAHAN", "E": "QC/RND", "F": "PPIC", "G": "WS"}.keys())
    day_map: dict[dt.date, dict[str, dict]] = defaultdict(lambda: defaultdict(
        lambda: {"minutes": 0, "events": 0, "kategori": defaultdict(int)}))
    for e in events:
        m = day_map[e["date"]][e["machine_raw"]]
        m["minutes"] += e["menit"]
        m["events"] += 1
        if e["kategori"] in kats:
            m["kategori"][e["kategori"]] += e["menit"]
    rows = []
    for d in sorted(day_map):
        mesin_list = sorted(day_map[d].items(), key=lambda kv: (-kv[1]["minutes"], kv[0]))
        for mesin, v in mesin_list:
            row = {"date": d, "machine": mesin, "machine_group": "",
                   "events": v["events"], "minutes": v["minutes"]}
            for k in kats:
                row[f"k_{k}"] = v["kategori"].get(k, 0)
            rows.append(row)
    return rows


def fokus_series(events: list[dict], cfg: dict) -> list[dict]:
    """Deret fokus RINGKASAN: N hari terakhir (Total, Frekuensi, Tunggu bahan,
    Plug assist, Kategori C)."""
    days = int((cfg.get("ringkasan", {}) or {}).get("fokus_days", 7))
    groups = (cfg.get("issue_mapping", {}) or {}).get("groups", {}) or {}
    tunggu_label = (groups.get("tunggu_bahan") or {}).get("label", "Tunggu Bahan")
    plug_label = (groups.get("plug_assist") or {}).get("label", "Plug Assist / Produk Nempel")
    totals = daily_totals(events)
    last_dates = sorted(totals)[-days:] if totals else []
    out = []
    for d in last_dates:
        day_ev = [e for e in events if e["date"] == d]
        out.append({
            "date": d,
            "minutes": totals[d]["minutes"],
            "events": totals[d]["events"],
            "tunggu_bahan": sum(e["menit"] for e in day_ev if e.get("issue_label") == tunggu_label),
            "plug_assist": sum(e["menit"] for e in day_ev if e.get("issue_label") == plug_label),
            "kategori_c": sum(e["menit"] for e in day_ev if e.get("kategori") == "C"),
        })
    return out


def summary(events: list[dict], target: dt.date) -> dict:
    """Semua metrik RINGKASAN dihitung dari data aktual."""
    totals = daily_totals(events)
    target_tot = totals.get(target, {"events": 0, "minutes": 0})
    mesin, mesin_menit = _dominant(per_machine_minutes(events, target))
    issue, issue_menit = _dominant(per_issue_minutes(events, target))

    kategori_minutes: dict[str, int] = defaultdict(int)
    for e in events:
        if e["date"] == target:
            kategori_minutes[e.get("kategori") or "-"] += e["menit"]
    kat, kat_menit = _dominant(dict(kategori_minutes))

    dates = sorted(totals)
    return {
        "date": target,
        "total_minutes": target_tot["minutes"],
        "total_events": target_tot["events"],
        "top_machine": mesin,
        "top_machine_minutes": mesin_menit,
        "top_issue": issue,
        "top_issue_minutes": issue_menit,
        "top_kategori": kat,
        "top_kategori_minutes": kat_menit,
        "period_start": dates[0] if dates else target,
        "period_end": dates[-1] if dates else target,
        "processed_days": len(dates),
    }


def followup_rows(events: list[dict], target: dt.date, cfg: dict) -> list[dict]:
    """Baris FOLLOW_UP untuk tanggal target (alarm produksi; idempotent per tanggal).

    - P1/P2: total downtime mesin pada tanggal target >= threshold config.
    - MONITOR: 1 baris arah total harian vs hari-tanggal processed sebelumnya.
    Evidence hanya menulis angka dari data; PIC/Update/Next Check kosong bila
    tidak dapat ditentukan dari data (jangan placeholder).
    """
    rules = (cfg.get("followup", {}) or {})
    priority_map: list[tuple[int, str]] = sorted(
        ((int(mins), prio) for prio, mins in (rules.get("priorities", {"P1": 120, "P2": 60})).items()),
        reverse=True)
    status = rules.get("status", "OPEN")
    action_tpl = rules.get("action_template", "Follow up alarm {machine} yang masih berulang.")

    per_machine = per_machine_minutes(events, target)
    rows = []
    for machine, menit in sorted(per_machine.items(), key=lambda kv: (-kv[1], kv[0])):
        minutes_total = int(menit)
        if minutes_total < priority_map[-1][0]:
            continue
        priority = next((p for threshold, p in priority_map if minutes_total >= threshold), None)
        if priority is None:
            continue
        issue_top = machine_top_issue(events, target, machine)
        issue_txt = issue_top[0] if issue_top else "-"
        evidence = f"{short_date(target)}: {machine} = {minutes_total} menit downtime"
        if issue_top:
            evidence += f"; {issue_txt} = {issue_top[1]} menit"
        rows.append({
            "priority": priority,
            "date": target,
            "machine": machine,
            "issue": issue_txt,
            "evidence": evidence,
            "pic": "",                    # kosong bila data tidak memuat owner
            "action": action_tpl.format(machine=machine),
            "status": status,
            "update": "",
            "next_check": "",
        })

    if rules.get("include_monitor_row", True):
        totals = daily_totals(events)
        target_tot = totals.get(target, {"events": 0, "minutes": 0})
        prevs = [d for d in totals if d < target]
        if prevs:
            prev_date = prevs[-1]
            prev_tot = totals[prev_date]
            direction = "TURUN" if target_tot["minutes"] <= prev_tot["minutes"] else "NAIK"
            evidence = (f"{short_date(target)}: {target_tot['events']} kejadian / {target_tot['minutes']} menit; "
                        f"{short_date(prev_date)}: {prev_tot['events']} kejadian / {prev_tot['minutes']} menit ({direction})")
            action = f"Monitor total downtime {short_date(target)} ({direction} vs {short_date(prev_date)})."
        else:
            evidence = f"{short_date(target)}: {target_tot['events']} kejadian / {target_tot['minutes']} menit (baseline)"
            action = "Monitoring baseline awal workbook monitoring."
            direction = "BASELINE"
        rows.append({
            "priority": "MONITOR",
            "date": target,
            "machine": "Semua mesin",
            "issue": f"Total downtime {direction}",
            "evidence": evidence,
            "pic": "",
            "action": action,
            "status": "MONITOR",
            "update": "",
            "next_check": "",
        })
    else:
        rows.sort(key=lambda r: (PRIORITY_ORDER.get(r["priority"], 5), -0))
    rows.sort(key=lambda r: (r["priority"], r["machine"]))
    return rows


PRIORITY_ORDER = {"P1": 0, "P2": 1, "P3": 2, "MONITOR": 9}   # urut baris sheet
