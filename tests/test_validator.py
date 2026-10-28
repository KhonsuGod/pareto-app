"""Test validator menolak data rusak."""
from __future__ import annotations

import datetime as dt

import pytest

from tests.conftest import make_event
from src import validator, pareto, downtime as dow, extractor, workbook
from src.issue_mapper import IssueMapper


def build(cfg, events, target):
    IssueMapper(cfg).apply(events)
    merged = events
    wb = workbook.load_or_create(cfg)
    cur = [e for e in merged if e["date"] == target]
    workbook.build_sheets(wb, cfg, merged=merged, target=target,
                          pareto_mesin=pareto.pareto_machine(cur),
                          pareto_issue=pareto.pareto_issue(cur),
                          trend=dow.trend_rows(merged),
                          rekap=dow.rekap_machine_rows(merged, cfg),
                          summary=dow.summary(merged, target),
                          followup=dow.followup_rows(merged, target, cfg))
    workbook.apply_charts(wb, cfg)
    return wb


def test_validate_clean_workbook_ok(cfg_tiny):
    target = dt.date(2026, 10, 27)
    evs = [make_event(target, machine="TFM 1", menit=40)]
    wb = build(cfg_tiny, evs, target)
    assert validator.validate_workbook(wb, cfg_tiny, target=target) == []


def test_validate_negative_minutes(tmp_path, cfg_tiny):
    target = dt.date(2026, 10, 27)
    evs = [make_event(target, machine="TFM 1", menit=40)]
    wb = build(cfg_tiny, evs, target)
    ws = wb["DETAIL_DOWNTIME"]
    ws.cell(row=3, column=8, value=-40)       # kolom menit jadi negatif
    errors = validator.validate_workbook(wb, cfg_tiny, target=target)
    assert any("negatif" in e for e in errors)


def test_validate_detects_duplicate_events(tmp_path, cfg_tiny):
    target = dt.date(2026, 10, 27)
    evs = [
        make_event(target, machine="TFM 1", menit=40, keterangan="tunggu bahan"),
        make_event(target, machine="TFM 1", menit=40, keterangan="tunggu bahan"),  # identik
    ]
    evs = extractor.dedup_events(evs)
    assert len(evs) == 1                      # dedup extractor bekerja


def test_validate_pareto_contribution(tmp_path, cfg_tiny):
    target = dt.date(2026, 10, 27)
    evs = [make_event(target, machine="TFM 1", menit=40),
           make_event(target, machine="WM", menit=60)]
    wb = build(cfg_tiny, evs, target)
    ws = wb["PARETO_MESIN"]
    ws.cell(row=3, column=4, value=0.9)       # kontribusi dirusak
    ws.cell(row=4, column=4, value=0.9)
    errors = validator.validate_workbook(wb, cfg_tiny, target=target)
    assert any("contribution" in e.lower() for e in errors)


def test_validate_error_literal(tmp_path, cfg_tiny):
    target = dt.date(2026, 10, 27)
    evs = [make_event(target, machine="TFM 1", menit=40)]
    wb = build(cfg_tiny, evs, target)
    wb["RINGKASAN"].cell(row=4, column=2, value="#REF!")
    errors = validator.validate_workbook(wb, cfg_tiny, target=target)
    assert any("#REF!" in e for e in errors)
