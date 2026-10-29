"""Test launcher dua tool, animasi, dan kompatibilitas Tool 1."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import anim, launcher, menu  # noqa: E402


def test_anim_disabled_when_not_tty(monkeypatch, capsys):
    monkeypatch.setattr(anim.sys.stdout, "isatty", lambda: False)
    assert anim.enabled() is False
    anim.progress("TEST", seconds=0.1)      # versi instan, tanpa escape
    anim.typewriter("HALO", seconds=0.05)
    out = capsys.readouterr().out
    assert "\x1b[" not in out
    assert "HALO" in out


def test_anim_disabled_by_env(monkeypatch):
    monkeypatch.setattr(anim.sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("MONITOR_NO_ANIMATION", "1")
    assert anim.enabled() is False
    monkeypatch.setenv("MONITOR_NO_ANIMATION", "")
    monkeypatch.setenv("NO_COLOR", "1")
    assert anim.enabled() is False


def test_launcher_navigation_and_back(monkeypatch):
    called = []

    def tool1():
        called.append("tool1")

    def tool2():
        called.append("tool2")

    answers = iter(["1", "0", "2", "0", "0"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    code = launcher.run({}, {"tool1": tool1, "tool2": tool2}, animate=False)
    assert called == ["tool1", "tool2"]
    assert code == 0


def test_tool1_menu_back_returns_to_launcher(cfg_tiny, monkeypatch):
    actions = {"update": lambda p, d: None, "status": lambda: None,
               "draft": lambda p, d: None, "validate": lambda p: None,
               "open_output": lambda p: None}
    monkeypatch.setattr("builtins.input", lambda *a: "0")
    result = menu.run(cfg_tiny, actions, title="DAILY PRODUCTION MONITORING", back=True)
    assert result == "back"


def test_tool1_menu_exit_when_not_nested(cfg_tiny, monkeypatch):
    actions = {"update": lambda p, d: None, "status": lambda: None,
               "draft": lambda p, d: None, "validate": lambda p: None,
               "open_output": lambda p: None}
    monkeypatch.setattr("builtins.input", lambda *a: "0")
    assert menu.run(cfg_tiny, actions) == 0


def test_tool2_menu_back_navigation(tmp_path, monkeypatch, capsys):
    from src.tooling import cli
    cfg = {"spare": {"workbook": str(tmp_path / "tidak_ada.xlsx"),
                     "backup_dir": str(tmp_path / "b"),
                     "state_file": str(tmp_path / "s.json")}}
    answers = iter(["0"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert cli.run(cfg) == "back"
