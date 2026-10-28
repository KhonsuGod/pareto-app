"""Ekstraksi, parsing & normalisasi data DOWNTIME.

Semua parsing deterministic (tanpa AI): tanggal, jam, menit, nama mesin,
kategori. device: machine_raw dipertahankan; machine_group dibuat bila perlu.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import OrderedDict

EXCEL_MIN_DATE = dt.datetime(1899, 12, 30)  # basis serial Excel (openpyxl-compatible)

DATE_RETRY_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y", "%d.%m.%Y",
)

TIME_INPUT_FORMATS = (
    "%H:%M:%S", "%H:%M", "%H.%M.%S", "%H.%M", "%H:%M:%S.%f", "%H%M%S",
)

EVENT_KEY_FIELDS = ("date", "machine_raw", "kode_barang", "jam_mulai", "jam_selesai", "keterangan")


def _cell(row: list, index: int | None):
    if index is None or index >= len(row):
        return None
    return row[index]


# --------------------------------------------------------------------------- #
# PARSER TANGGAL / JAM / MENIT
# --------------------------------------------------------------------------- #
def parse_date(value, fmt: str = "%Y-%m-%d") -> dt.date | None:
    """Parse TGL. Menerima datetime/date/str/serial Excell (>= 40.000 saja)."""
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (int, float)):
        # Serial Excel ratusan/ribuan tidak berlaku sebagai tanggal (mis. 1/40179);
        # hanya terima serial historians valid (> 40000 ~ > 2009).
        if isinstance(value, float):
            if int(value) != value:
                return None
            value = int(value)
        if isinstance(value, int) and value > 40000:
            return (EXCEL_MIN_DATE + dt.timedelta(days=int(value))).date()
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return dt.datetime.strptime(text, fmt).date()
    except ValueError:
        pass
    # string datetime "2026-10-27 00:00:00"
    for f in (" ".join([fmt, "%H:%M:%S"]), " ".join([fmt, "%H:%M"]), ""):
        if f:
            try:
                return dt.datetime.strptime(text, f).date()
            except ValueError:
                continue
    for f in DATE_RETRY_FORMATS:
        try:
            return dt.datetime.strptime(text, f).date()
        except ValueError:
            continue
    # ISO dengan waktu
    try:
        return dt.datetime.fromisoformat(text).date()
    except ValueError:
        return None


def parse_time(value) -> dt.time | None:
    """Parse JAM MULAI / JAM SELESAI."""
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.time()
    if isinstance(value, dt.time):
        return value
    if isinstance(value, (int, float)):
        # fraksi hari (0..1)
        frac = float(value) % 1.0
        if frac < 0:
            return None
        secs = round(frac * 86400)
        if secs >= 86400:
            secs = 86399
        return (dt.datetime(2000, 1, 1) + dt.timedelta(seconds=secs)).time()
    text = str(value).strip().replace(",", ":").replace(".", ":")
    text = re.sub(r"(\d)h(\d)", r"\1:\2", text)
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?$", text)
    if m:
        h, mi, sec = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        if h < 24 and mi < 60 and sec < 60:
            return dt.time(h, mi, sec)
        return None
    if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", text) is None and re.fullmatch(r"\d{5,6}", text):
        try:
            fmt = TIME_INPUT_FORMATS[-1]
            return dt.datetime.strptime(text, fmt).time()
        except ValueError:
            return None
    for f in TIME_INPUT_FORMATS:
        try:
            return dt.datetime.strptime(text, f).time()
        except ValueError:
            continue
    return None


def _minutes_between(start: dt.time | None, end: dt.time | None) -> int | None:
    if start is None or end is None:
        return None
    s = start.hour * 60 + start.minute + start.second / 60
    e = end.hour * 60 + end.minute + end.second / 60
    if e < s:  # lintas tengah malam
        e += 1440
    return int(round(e - s))


def parse_minutes(value, start=None, end=None) -> int | None:
    """TOTAL (MENIT). Kalau source tidak numerik, hitung dari jam mulai/selesai."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minutes = int(round(float(value)))
        if minutes < 0:
            minutes = None  # negatif dianggap tidak valid
        return minutes
    if value in (None, ""):
        return _minutes_between(parse_time(start), parse_time(end))
    text = str(value).strip().lower()
    # "90 Menit" / "1.440 menit" / "90 mnt"
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*(?:menit|mnt|min|mins|minutes)?$", text)
    if m:
        raw = m.group(1).replace(",", ".")
        return int(round(float(raw)))
    return _minutes_between(parse_time(start), parse_time(end))


# --------------------------------------------------------------------------- #
# MESIN: nama asli + group
# --------------------------------------------------------------------------- #
def clean_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def machine_group(raw: str, mode: str = "strip_dot") -> str:
    """Grouping keluarga mesin mengikuti config (default: buang suffix '.N').

    TFM 1.1 -> TFM 1 | WM.2 -> WM | PRT 4.1 -> PRT 4 | TLB-7 -> TLB-7
    """
    name = clean_text(raw)
    if not name:
        return ""
    if mode == "strip_dot":
        base, sep, _suffix = name.rpartition(".")
        if sep and re.fullmatch(r"\d+", _suffix) and len(base) >= 1:
            return clean_text(base)
        return name
    return name


# --------------------------------------------------------------------------- #
# EKSTRAKSI EVENT
# --------------------------------------------------------------------------- #
def _header_index(header_row: list, colmap: dict) -> dict | None:
    """Posisi kolom berdasarkan header sesuai config.columns.

    Kolom yang labelnya dikosongkan di config (mis. Proses 1 tidak punya
    KODE BARANG) dianggap opsional dan dipetakan ke None.
    """
    idx = {}
    for i, h in enumerate(header_row):
        if h is None:
            continue
        idx[clean_text(h).upper()] = i
    required = ("tgl", "mesin", "jam_mulai", "jam_selesai", "total_menit", "keterangan")
    missing = []
    out = {}
    for key, label in colmap.items():
        label = clean_text(label)
        if not label:
            out[key] = None
            continue
        j = idx.get(label.upper())
        out[key] = j
        if j is None and key in required:
            missing.append(label)
    if missing:
        return None
    return out


def _find_header_row(rows: list[list], colmap: dict, fallback: int = 0) -> int:
    """Cari baris header (TGL & MESIN ada di baris yang sama).

    Sheet admin Proses 1 punya 2 baris judul/legend sebelum header, jadi
    posisi header tidak boleh diasumsikan di baris pertama.
    """
    want_tgl = clean_text(colmap.get("tgl", "")).upper()
    want_mesin = clean_text(colmap.get("mesin", "")).upper()
    for i, row in enumerate(rows[:30]):
        cells = {clean_text(v).upper() for v in row if v is not None}
        if want_tgl and want_mesin and want_tgl in cells and want_mesin in cells:
            return i
    return max(0, min(fallback, len(rows) - 1))


def normalize_kategori(value: str, cfg: dict) -> str:
    """'LT Maintenance' -> 'LT' ; 'A' -> 'A' (kunci kategori di config)."""
    v = clean_text(value).upper()
    if not v:
        return ""
    keys = list((cfg.get("kategori_labels") or {}).keys())
    if v in keys:
        return v
    for k in sorted(keys, key=len, reverse=True):
        if v == k or v.startswith(k + " ") or v.startswith(k + "/"):
            return k
    return v


def extract_events(rows: list[list], cfg: dict) -> list[dict]:
    """Baris sheet DOWNTIME -> list event bersih.

    Event: >= tanggal valid, mesin terisi, menit >= 0. Baris rusak dilewati.
    """
    columns = cfg["columns"]
    fmt_in = cfg["date"].get("input_format", "%Y-%m-%d")
    group_mode = cfg.get("machine_grouping", {}).get("mode", "strip_dot")
    if not rows:
        return []
    hrow = _find_header_row(rows, columns, int(cfg.get("sheet_header_row", 1)) - 1)
    pos = _header_index(rows[hrow], columns)
    if pos is None:
        raise RuntimeError(
            "Kolom tidak sesuai antara config.yaml.columns dan header sheet sumber: "
            f"header baris {hrow + 1} = {rows[hrow][:12]}")

    events = []
    rejected = 0
    for n, row in enumerate(rows[hrow + 1:], start=hrow + 2):
        date = parse_date(_cell(row, pos["tgl"]), fmt_in)
        machine_raw = clean_text(_cell(row, pos["mesin"]))
        if date is None or not machine_raw:
            rejected += 1
            continue
        menit = parse_minutes(_cell(row, pos["total_menit"]),
                              _cell(row, pos["jam_mulai"]), _cell(row, pos["jam_selesai"]))
        if menit is None:
            rejected += 1
            continue
        ev = {
            "date": date,
            "machine_raw": machine_raw,
            "machine": machine_raw,
            "machine_group": machine_group(machine_raw, group_mode),
            "kode_barang": clean_text(_cell(row, pos["kode_barang"])),
            "nama_produk": clean_text(_cell(row, pos["nama_produk"])),
            "jam_mulai": parse_time(_cell(row, pos["jam_mulai"])),
            "jam_selesai": parse_time(_cell(row, pos["jam_selesai"])),
            "menit": int(menit),
            "keterangan": clean_text(_cell(row, pos["keterangan"])),
            "kategori": normalize_kategori(_cell(row, pos["kategori"]), cfg),
            "row": n,
        }
        ev["event_key"] = event_key(ev)
        events.append(ev)
    if rejected:
        from . import logger
        logger.debug(f"{rejected} baris source tidak valid (tanpa TGL/MESIN/menit) dilewati.")
    return events


def event_key(ev: dict) -> str:
    parts = [
        ev["date"].isoformat(),
        ev.get("machine_raw", "") or "",
        ev.get("kode_barang", "") or "",
        ev["jam_mulai"].isoformat() if ev.get("jam_mulai") else "",
        ev["jam_selesai"].isoformat() if ev.get("jam_selesai") else "",
        (ev.get("keterangan", "") or "").lower(),
    ]
    return "|".join(parts)  # unique key spec R


def dedup_events(events: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for ev in events:
        k = ev.get("event_key") or event_key(ev)
        if k in seen:
            continue
        seen.add(k)
        out.append(ev)
    return out


def day_events(events: list[dict], target: dt.date) -> list[dict]:
    return sorted((e for e in events if e["date"] == target),
                  key=lambda e: (e["jam_mulai"] or dt.time(0, 0), e["machine_raw"], e["row"]),
                  reverse=False)


def invalid_rows(events: list[dict], target: dt.date) -> list[str]:
    """Rangkuman baris tanggal target yang tidak valid atau menit tidak masuk akal."""
    warnings = []
    for e in events:
        if e["date"] != target:
            continue
        if e["menit"] < 0:
            warnings.append(f"mesin={e['machine_raw']} menit={e['menit']} < 0")
        elif e["menit"] > 1440:
            warnings.append(f"mesin={e['machine_raw']} menit={e['menit']} > 24 jam")
    return warnings


def normalize_manual_date(text: str | None) -> str | None:
    if not text:
        return text
    return text.strip()


def process_target_dates(events: list[dict]) -> OrderedDict:
    out = OrderedDict()
    for ev in events:
        out.setdefault(ev["date"], []).append(ev)
    return out
