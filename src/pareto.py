"""Kalkulasi Pareto (mesin & issue) - deterministic.

Urutan: downtime menit desc, lalu nama asc (tie-break stabil).
Contribution & cumulative dihitung sebagai fraksi; kumulatif terakhir = 1.0.
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict


def _aggregate(events: list[dict], field: str) -> list[tuple[str, int, int]]:
    thr = defaultdict(lambda: {"minutes": 0, "count": 0})
    for e in events:
        name = str(e.get(field) or "-").strip() or "-"
        thr[name]["minutes"] += int(e["menit"])
        thr[name]["count"] += 1
    rows = [(name, v["count"], v["minutes"]) for name, v in thr.items()]
    rows.sort(key=lambda r: (-r[2], r[0]))
    return rows


def _pareto(agg: list[tuple[str, int, int]]) -> list[dict]:
    total = sum(r[2] for r in agg)
    out = []
    run = 0
    for name, count, minutes in agg:
        contribution = (minutes / total) if total else 0.0
        run += minutes
        cumulative = (run / total) if total else 0.0
        out.append({
            "name": name,
            "event_count": count,
            "minutes": minutes,
            "contribution": contribution,
            "cumulative": round(cumulative, 6),
        })
    if out and total:
        out[-1]["cumulative"] = 1.0   # kumulatif terakhir selalu 100%
    return out


def pareto_machine(events: list[dict]) -> list[dict]:
    """Pareto berdasar mesin (nama asli, tanpa penggabungan)."""
    return _pareto(_aggregate(events, "machine"))


def pareto_issue(events: list[dict]) -> list[dict]:
    """Pareto berdasar issue group (label)."""
    return _pareto(_aggregate(events, "issue_label"))


def pareto_group(events: list[dict]) -> list[dict]:
    """Pareto berdasar machine_group (opsional/analisa keluarga mesin)."""
    return _pareto(_aggregate(events, "machine_group"))


def top_rows(pareto_rows: list[dict], n: int = 5) -> list[dict]:
    return pareto_rows[:n]
