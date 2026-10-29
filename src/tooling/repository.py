"""Akses workbook Tooling & Spare — baca/tulis aman, formula Excel tetap sumber kebenaran.

Akuntansi stock (hasil audit workbook):
    Stock Aktual (kolom F)  = Stock Awal (D) - SUMIFS(LOG Qty Keluar, family, komponen)
    Keluar Hari Ini (E)     = SUMIFS(..., tanggal = TODAY())
Formula ini milik Excel. Python TIDAK menulis hasil hitungan ke F; Python hanya:
    - menambah baris OUT ke LOG PENGELUARAN (+ ID Transaksi di kolom K),
    - mengisi Stock Awal (D) saat OPENING/ADJUSTMENT (opname),
    - menyalin formula Excel ke dalam perhitungan tampilan (mirror, read-only).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import LedgerEntry, OutTx, RoutingRow, StockItem

LOG_FIRST = 5
LOG_LAST = 654          # batas formula SUMIFS di STOCK SPARE / LOG (bisa diperpanjang)
LEDGER_SHEET = "LEDGER SPARE"
LEDGER_HEAD = ("ID", "Waktu", "Tipe", "Tooling Family", "Komponen", "Stock Awal Sblm",
               "Jumlah Fisik", "Selisih", "Stock Awal Baru", "PIC", "Catatan")
TXN_ID_HEADER = "ID Transaksi"


def _norm(value) -> str:
    return str(value).strip() if value is not None else ""


def _key(value) -> str:
    return _norm(value).casefold()


ROOT = Path(__file__).resolve().parent.parent.parent


class SpareStore:
    """Semua akses file workbook spare. Tool 1 tidak menyentuh modul ini."""

    def __init__(self, cfg: dict):
        spare = cfg.get("spare") or {}
        root = ROOT
        def _abs(p):
            path = Path(p)
            return path if path.is_absolute() else (root / path)
        self.workbook_path: Path = _abs(spare.get("workbook", "data/spare/monitorung_spare_proses2.xlsx"))
        self.source_path: Path | None = _abs(spare["source_workbook"]) if spare.get("source_workbook") else None
        self.backup_dir: Path = _abs(spare.get("backup_dir", "data/spare/backups"))
        self.backup_keep = int(spare.get("backup_keep", 10))
        self.state_path: Path = _abs(spare.get("state_file", "data/spare/state.json"))
        self.minimum_stock = spare.get("minimum_stock") or {}

    # ------------------------------------------------------------------ #
    # state kecil (sekuens ID, sha workbook)
    # ------------------------------------------------------------------ #
    def _state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_state(self, data: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _sha(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def next_txn_id(self, kind: str = "OUT") -> str:
        st = self._state()
        seq = int(st.get("seq", 0)) + 1
        self._save_state({**st, "seq": seq})
        stamp = dt.datetime.now().strftime("%Y%m%d")
        return f"T2-{kind}-{stamp}-{seq:05d}"

    # ------------------------------------------------------------------ #
    # buka / import workbook
    # ------------------------------------------------------------------ #
    def ensure_workbook(self) -> Path:
        """Workbook kerja lokal; kalau belum ada, impor dari source asli."""
        if self.workbook_path.exists():
            return self.workbook_path
        if self.source_path and self.source_path.exists():
            self.workbook_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.source_path, self.workbook_path)
            st = self._state()
            self._save_state({**st, "imported_from": str(self.source_path),
                              "imported_at": dt.datetime.now().isoformat(timespec="seconds")})
        else:
            raise RuntimeError(
                f"Workbook spare tidak ditemukan: {self.workbook_path}\n"
                f"       Taruh workbook di path itu atau isi spare.source_workbook di config.yaml.")
        return self.workbook_path

    def load(self) -> openpyxl.Workbook:
        path = self.ensure_workbook()
        try:
            return openpyxl.load_workbook(path)
        except PermissionError as exc:
            raise RuntimeError(
                f"Workbook sedang terkunci Windows: {path}\n"
                f"       Tutup workbook di Excel lalu ulangi.") from exc
        except Exception as exc:
            raise RuntimeError(f"Workbook spare rusak / tidak bisa dibaca: {path} ({exc})") from exc

    def check_external_changes(self) -> bool:
        """True kalau workbook berubah dari luar aplikasi sejak simpan terakhir."""
        st = self._state()
        last = st.get("workbook_sha256")
        if not last or not self.workbook_path.exists():
            return False
        return self._sha(self.workbook_path) != last

    # ------------------------------------------------------------------ #
    # baca master / stock / log
    # ------------------------------------------------------------------ #
    def read_routing(self, wb) -> list[RoutingRow]:
        ws = wb["MASTER TOOLING"]
        rows = []
        for r in range(5, ws.max_row + 1):
            family = _norm(ws.cell(r, 3).value)
            if not family and not _norm(ws.cell(r, 4).value):
                continue
            rows.append(RoutingRow(
                row=r,
                no=ws.cell(r, 1).value,
                mesin=_norm(ws.cell(r, 2).value),
                family=family,
                kode_bj=_norm(ws.cell(r, 4).value),
                nama_produk=_norm(ws.cell(r, 5).value),
                cavity=ws.cell(r, 6).value if isinstance(ws.cell(r, 6).value, (int, float)) else None,
                mould=_norm(ws.cell(r, 7).value),
                insert=_norm(ws.cell(r, 8).value),
                plug_assist=_norm(ws.cell(r, 9).value),
                ejector=_norm(ws.cell(r, 10).value),
                catatan=_norm(ws.cell(r, 11).value),
            ))
        return rows

    def read_stock_items(self, wb) -> list[StockItem]:
        ws = wb["STOCK SPARE"]
        items = []
        for r in range(5, ws.max_row + 1):
            family = _norm(ws.cell(r, 2).value)
            component = _norm(ws.cell(r, 3).value)
            if not family or not component:
                continue
            awal = ws.cell(r, 4).value
            if awal in (None, ""):
                stock_awal = None
            else:
                try:
                    stock_awal = int(awal)
                except (TypeError, ValueError):
                    stock_awal = None
            items.append(StockItem(
                row=r, family=family, component=component, stock_awal=stock_awal,
                lokasi=_norm(ws.cell(r, 7).value), catatan=_norm(ws.cell(r, 8).value),
                kondisi=_norm(ws.cell(r, 9).value),
            ))
        return items

    def read_log(self, wb) -> list[OutTx]:
        ws = wb["LOG PENGELUARAN"]
        txs = []
        for r in range(LOG_FIRST, ws.max_row + 1):
            vals = [ws.cell(r, c).value for c in range(1, 11)]
            if all(v in (None, "") for v in vals):
                continue
            d = vals[0] if isinstance(vals[0], dt.datetime) else None
            t = vals[1] if isinstance(vals[1], dt.datetime) else None
            qty_raw = vals[7]
            try:
                qty = int(qty_raw)
            except (TypeError, ValueError):
                qty = -1  # invalid; validator yang melaporkan
            txs.append(OutTx(
                row=r, txn_id=_norm(ws.cell(r, 11).value),
                date=d.date() if d else None,
                jam=t.time() if t else None,
                mesin=_norm(vals[2]), family=_norm(vals[3]), kode_bj=_norm(vals[4]),
                nama_produk=_norm(vals[5]), component=_norm(vals[6]),
                qty=qty, keterangan=_norm(vals[8]), pic=_norm(vals[9]),
            ))
        return txs

    def read_ledger(self, wb) -> list[LedgerEntry]:
        if LEDGER_SHEET not in wb.sheetnames:
            return []
        ws = wb[LEDGER_SHEET]
        entries = []
        for r in range(2, ws.max_row + 1):
            if ws.cell(r, 1).value in (None, ""):
                continue
            entries.append(LedgerEntry(
                row=r, entry_id=_norm(ws.cell(r, 1).value),
                time=ws.cell(r, 2).value,
                kind=_norm(ws.cell(r, 3).value),
                family=_norm(ws.cell(r, 4).value), component=_norm(ws.cell(r, 5).value),
                previous_awal=ws.cell(r, 6).value, physical=ws.cell(r, 7).value,
                diff=ws.cell(r, 8).value, new_awal=ws.cell(r, 9).value,
                pic=_norm(ws.cell(r, 10).value), note=_norm(ws.cell(r, 11).value),
            ))
        return entries

    # ------------------------------------------------------------------ #
    # struktur tambahan (ID header + LEDGER) — sekali saja
    # ------------------------------------------------------------------ #
    def ensure_structure(self, wb) -> None:
        """Tambah kolom K 'ID Transaksi' dan sheet LEDGER SPARE bila belum ada."""
        log = wb["LOG PENGELUARAN"]
        if _norm(log.cell(4, 11).value) != TXN_ID_HEADER:
            log.cell(4, 11).value = TXN_ID_HEADER
            log.cell(4, 11).font = Font(bold=True)
            log.column_dimensions["K"].width = 18.0
        if LEDGER_SHEET not in wb.sheetnames:
            ws = wb.create_sheet(LEDGER_SHEET)
            ws.append(list(LEDGER_HEAD))
            for c in range(1, len(LEDGER_HEAD) + 1):
                ws.cell(1, c).font = Font(bold=True)
            widths = [16, 19, 12, 24, 20, 14, 13, 10, 15, 14, 46]
            for i, w in enumerate(widths, start=1):
                ws.column_dimensions[get_column_letter(i)].width = w

    # ------------------------------------------------------------------ #
    # tulis transaksi
    # ------------------------------------------------------------------ #
    def append_out(self, wb, tx: OutTx, override: bool = False) -> int:
        """Tambah 1 baris OUT ke LOG. Idempotent: ID sama -> tidak ditulis dua kali."""
        log = wb["LOG PENGELUARAN"]
        existing = {t.txn_id for t in self.read_log(wb) if t.txn_id}
        if tx.txn_id in existing:
            return -1  # sudah pernah dicatat (replay) — jangan duplikat
        row = self._next_log_row(log)
        if row > LOG_LAST:
            self._extend_formula_ranges(wb, row)
        log.cell(row, 1).value = tx.date
        log.cell(row, 2).value = dt.datetime.combine(dt.date.today(), tx.jam) if tx.jam else None
        log.cell(row, 3).value = tx.mesin or None
        log.cell(row, 4).value = tx.family
        log.cell(row, 5).value = tx.kode_bj or None
        log.cell(row, 6).value = tx.nama_produk or None
        log.cell(row, 7).value = tx.component
        log.cell(row, 8).value = tx.qty
        log.cell(row, 9).value = tx.keterangan or None
        log.cell(row, 10).value = tx.pic or None
        log.cell(row, 11).value = tx.txn_id
        if override:
            self.append_ledger(wb, kind="OVERRIDE", family=tx.family, component=tx.component,
                               physical=None, new_awal=None, pic=tx.pic,
                               note=f"Stock negatif diizinkan untuk {tx.txn_id}: {tx.keterangan}")
        return row

    def set_opening(self, wb, item_row: int, value: int, lokasi: str | None = None,
                    kondisi: str | None = None, catatan: str | None = None) -> None:
        st = wb["STOCK SPARE"]
        st.cell(item_row, 4).value = value
        if lokasi:
            st.cell(item_row, 7).value = lokasi
        if kondisi:
            st.cell(item_row, 9).value = kondisi
        if catatan:
            st.cell(item_row, 8).value = catatan

    def append_ledger(self, wb, kind: str, family: str, component: str,
                      previous_awal: int | None = None, physical: int | None = None,
                      diff: int | None = None, new_awal: int | None = None,
                      pic: str = "", note: str = "") -> str:
        self.ensure_structure(wb)
        ws = wb[LEDGER_SHEET]
        entry_id = self.next_txn_id(kind[:3] or "LED")
        row = ws.max_row + 1 if ws.max_row > 1 else 2
        ws.cell(row, 1).value = entry_id
        ws.cell(row, 2).value = dt.datetime.now()
        ws.cell(row, 3).value = kind
        ws.cell(row, 4).value = family
        ws.cell(row, 5).value = component
        ws.cell(row, 6).value = previous_awal
        ws.cell(row, 7).value = physical
        ws.cell(row, 8).value = diff
        ws.cell(row, 9).value = new_awal
        ws.cell(row, 10).value = pic or None
        ws.cell(row, 11).value = note or None
        return entry_id

    def _next_log_row(self, log) -> int:
        row = LOG_FIRST
        for r in range(LOG_FIRST, log.max_row + 1):
            if any(log.cell(r, c).value not in (None, "") for c in range(1, 12)):
                row = r + 1
        return row

    def _extend_formula_ranges(self, wb, new_last: int) -> None:
        """Perpanjang jangkauan $654 di formula bila log melewati batas."""
        st = wb["STOCK SPARE"]
        for r in range(5, st.max_row + 1):
            for c in (5, 6):
                v = st.cell(r, c).value
                if isinstance(v, str) and "$654" in v:
                    st.cell(r, c).value = v.replace("$654", f"${new_last}")
        log = wb["LOG PENGELUARAN"]
        v = log.cell(3, 2).value
        if isinstance(v, str) and "654" in v:
            log.cell(3, 2).value = v.replace("654", str(new_last))

    # ------------------------------------------------------------------ #
    # simpan aman: backup -> tmp -> validate -> reopen -> replace
    # ------------------------------------------------------------------ #
    def backup(self) -> Path | None:
        if not self.workbook_path.exists():
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dest = self.backup_dir / f"spare_backup_{stamp}.xlsx"
        shutil.copy2(self.workbook_path, dest)
        backups = sorted(self.backup_dir.glob("spare_backup_*.xlsx"))
        for old in backups[: -self.backup_keep]:
            old.unlink(missing_ok=True)
        return dest

    def save(self, wb, validator=None) -> Path:
        """Simpan aman. Gagal validasi -> workbook asli tidak disentuh."""
        # ekstensi akhir harus .xlsx (openpyxl menolak .tmp saat reopen verifikasi)
        tmp = self.workbook_path.with_suffix(".tmp.xlsx")
        if validator:
            errors = validator(wb)
            if errors:
                raise RuntimeError("Validasi gagal, workbook tidak disimpan:\n" +
                                   "\n".join(f"  - {e}" for e in errors))
        self.backup()  # wajib: backup sebelum modifikasi workbook
        for attempt in range(3):
            try:
                wb.save(tmp)
                break
            except PermissionError:
                if attempt == 2:
                    tmp.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"File terkunci Windows: {self.workbook_path.name}\n"
                        f"       Tutup workbook di Excel lalu ulangi.")
                time.sleep(1.0)
        # verifikasi bisa dibaca lagi
        check = openpyxl.load_workbook(tmp)
        missing = [s for s in ("MASTER TOOLING", "STOCK SPARE", "LOG PENGELUARAN")
                   if s not in check.sheetnames]
        check.close()
        if missing:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"Hasil simpan tidak lengkap (sheet hilang: {missing}).")
        self._replace(tmp)
        self._save_state({**self._state(),
                          "workbook_sha256": self._sha(self.workbook_path),
                          "last_save": dt.datetime.now().isoformat(timespec="seconds")})
        return self.workbook_path

    def _replace(self, tmp: Path) -> None:
        for attempt in range(3):
            try:
                os.replace(tmp, self.workbook_path)
                return
            except PermissionError:
                if attempt == 2:
                    tmp.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"File terkunci Windows: {self.workbook_path.name}\n"
                        f"       Tutup workbook di Excel lalu ulangi.")
                time.sleep(1.0)

    # ------------------------------------------------------------------ #
    # minimum stock dari config
    # ------------------------------------------------------------------ #
    def minimum_for(self, family: str, component: str) -> int | None:
        fam = (self.minimum_stock or {}).get(family) or {}
        for k, v in fam.items():
            if _key(k) == _key(component):
                try:
                    return int(v)
                except (TypeError, ValueError):
                    return None
        return None


def clean_code(value) -> str:
    """Normalisasi Kode BJ untuk lookup (strip, uppercase)."""
    return _norm(value).upper()
