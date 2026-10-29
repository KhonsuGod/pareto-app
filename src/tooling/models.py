"""Model data Tooling & Spare. Nilai diambil persis dari workbook — tanpa rekayasa."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum


class StockStatus(str, Enum):
    UNKNOWN = "UNKNOWN"          # Stock Awal belum diinput (kosong, bukan nol)
    OUT = "OUT"                  # stock terverifikasi = 0
    LOW = "LOW"                  # 0 < stock <= minimum
    OK = "OK"                    # stock > minimum
    NOT_CONFIGURED = "NOT CONFIGURED"  # stock positif, threshold belum diisi
    DEFICIT = "DEFICIT"          # negatif, hanya lewat override tercatat


@dataclass(frozen=True)
class RoutingRow:
    """Satu baris MASTER TOOLING (routing produk -> komponen tooling)."""
    row: int
    no: int | None
    mesin: str            # "Mesin (PPIC)"; bisa kosong di source
    family: str
    kode_bj: str          # bisa kosong di source
    nama_produk: str
    cavity: int | None
    mould: str
    insert: str
    plug_assist: str
    ejector: str
    catatan: str

    def unverified(self) -> bool:
        """True kalau source masih 'CEK TS' (belum terverifikasi)."""
        parts = (self.mould, self.insert, self.plug_assist, self.ejector)
        checked = [p for p in parts if p]
        return bool(checked) and all("CEK TS" in str(p).upper() for p in checked)


@dataclass(frozen=True)
class StockItem:
    """Satu baris STOCK SPARE."""
    row: int
    family: str
    component: str
    stock_awal: int | None    # None = belum diinput (BKN nol)
    lokasi: str
    catatan: str
    kondisi: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.family.casefold(), self.component.casefold())


@dataclass(frozen=True)
class OutTx:
    """Satu transaksi keluar dari LOG PENGELUARAN."""
    row: int
    txn_id: str
    date: dt.date | None
    jam: dt.time | None
    mesin: str
    family: str
    kode_bj: str
    nama_produk: str
    component: str
    qty: int
    keterangan: str
    pic: str


@dataclass(frozen=True)
class LedgerEntry:
    """Satu entri LEDGER SPARE (OPENING / ADJUSTMENT / OVERRIDE)."""
    row: int
    entry_id: str
    time: dt.datetime | None
    kind: str
    family: str
    component: str
    previous_awal: int | None
    physical: int | None
    diff: int | None
    new_awal: int | None
    pic: str
    note: str


@dataclass(frozen=True)
class StockView:
    """Hasil perhitungan stock satu item (mirror formula Excel)."""
    item: StockItem
    keluar_total: int          # total OUT dari LOG
    keluar_today: int
    stock: int | None          # None = belum diinput
    status: StockStatus
    minimum: int | None
