"""Mapping issue berbasis keyword config (case-insensitive), surviving description_raw."""
from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


class IssueMapper:
    """Keyword matcher: urutan group mengikuti config 'issue_mapping.order'."""

    def __init__(self, cfg: dict):
        im = cfg.get("issue_mapping", {}) or {}
        order = im.get("order") or []
        groups = im.get("groups") or {}
        if not order:
            order = list(groups.keys())
        self.rules = []
        for key in order:
            g = groups.get(key)
            if not g:
                continue
            kws = [normalize_text(k) for k in g.get("keywords", []) if k]
            self.rules.append((key, g.get("label", key), kws))
        self.labels = {key: label for key, label, _ in self.rules}
        self.fallback_label = groups.get("other", {}).get("label", "Other")
        self.fallback_key = "other"

    def map_text(self, text: str) -> tuple[str, str]:
        """Return (issue_group, issue_label). Fallback = Other."""
        norm = normalize_text(text)
        if norm:
            for key, label, kws in self.rules:
                for kw in kws:
                    if kw and kw in norm:
                        return key, label
        return self.fallback_key, self.fallback_label

    def apply(self, events: list[dict]) -> list[dict]:
        for ev in events:
            group, label = self.map_text(ev.get("keterangan", ""))
            ev["issue_group"] = group      # keterangan asli (description_raw) tetap ada
            ev["issue_label"] = label
        return events
