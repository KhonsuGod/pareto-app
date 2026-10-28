"""Helper log CLI (VERBOSE, OK, WARN, ERROR)."""
from __future__ import annotations

_VERBOSE = {"on": False}


def init(verbose: bool = False) -> None:
    """Aktifkan mode debug bila --verbose."""
    _VERBOSE["on"] = bool(verbose)


def debug(msg: str) -> None:
    if _VERBOSE["on"]:
        print(f"[DEBUG] {msg}")


def ok(msg: str) -> None:
    print(f"[OK] {msg}")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def err(msg: str) -> None:
    print(f"[ERROR] {msg}")

