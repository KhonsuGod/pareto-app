"""Test inti Tool 2: lookup, stock, transaksi OUT, opname, ledger."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture import DEFAULT_ITEMS, make_store  # noqa: E402

from src.tooling import service
from src.tooling.models import StockStatus


def test_find_tooling_by_kode_bj_multi_match(tmp_path):
    store, _ = make_store(tmp_path)
    rows = service.find_tooling(store, "BJ-PP00526-0")
    assert len(rows) == 1
    # satu produk dua routing -> semua hasil ditampilkan
    rows = service.find_tooling(store, "BJ-PP00527-0")
    assert len(rows) == 1
    # partial nama produk, case-insensitive
    rows = service.find_tooling(store, "cold cup")
    assert len(rows) == 1 and rows[0].family == "CUP-16"


def test_find_tooling_unknown_returns_empty(tmp_path):
    store, _ = make_store(tmp_path)
    assert service.find_tooling(store, "BJ-TIDAKADA-9") == []


def test_stock_blank_is_unknown_zero_is_out(tmp_path):
    store, _ = make_store(tmp_path)
    views = {v.item.key: v for v in service.stock_views(store)}
    plug = views[("datar-12", "plug assist")]
    assert plug.stock is None and plug.status == StockStatus.UNKNOWN
    insert16 = views[("cup-16", "insert")]
    assert insert16.stock == 0 and insert16.status == StockStatus.OUT
    mould16 = views[("cup-16", "mould")]
    assert mould16.stock == 5 and mould16.status == StockStatus.NOT_CONFIGURED


def test_record_out_happy_path(tmp_path):
    store, wb_path = make_store(tmp_path)
    tx = service.record_out(store, family="CUP-16", component="MOULD", qty=2,
                            kode_bj="BJ-PP00246-0", mesin="WM", pic="Davi",
                            keterangan="ganti mould")
    wb = store.load()
    log = service.history(store)
    assert len(log) == 1
    assert log[0].qty == 2 and log[0].component == "MOULD"
    assert log[0].nama_produk == "CLEAR COLD CUP 16 OZ"  # dari MASTER TOOLING
    assert log[0].txn_id == tx.txn_id
    views = {v.item.key: v for v in service.stock_views(store, wb)}
    assert views[("cup-16", "mould")].stock == 3
    # workbook asli tetap punya formula di E/F
    st = wb["STOCK SPARE"]
    assert str(st.cell(9, 6).value).startswith("=IF(")


def test_record_out_replay_same_id_not_duplicated(tmp_path):
    store, _ = make_store(tmp_path)
    tx1 = service.record_out(store, family="CUP-16", component="MOULD", qty=1, txn_id="T2-OUT-TEST-001")
    tx2 = service.record_out(store, family="CUP-16", component="MOULD", qty=1, txn_id="T2-OUT-TEST-001")
    assert tx1.txn_id == tx2.txn_id
    assert len(service.history(store)) == 1


def test_record_out_two_genuine_same_values_allowed(tmp_path):
    store, _ = make_store(tmp_path)
    service.record_out(store, family="CUP-16", component="MOULD", qty=1)
    service.record_out(store, family="CUP-16", component="MOULD", qty=1)
    assert len(service.history(store)) == 2


def test_record_out_blocks_invalid_family_qty_and_bj(tmp_path):
    store, _ = make_store(tmp_path)
    for kwargs in (
        {"family": "TIDAK-ADA", "component": "MOULD", "qty": 1},
        {"family": "CUP-16", "component": "MOULD", "qty": 0},
        {"family": "CUP-16", "component": "MOULD", "qty": -3},
        {"family": "CUP-16", "component": "MOULD", "qty": 1, "kode_bj": "BJ-PP00526-0"},  # routing beda family
    ):
        try:
            service.record_out(store, **kwargs)
            assert False, f"harusnya ditolak: {kwargs}"
        except ValueError:
            pass


def test_record_out_blocks_unknown_stock(tmp_path):
    store, _ = make_store(tmp_path)
    try:
        service.record_out(store, family="DATAR-12", component="MOULD", qty=1)
        assert False, "stock belum diinput harusnya memblok"
    except ValueError as exc:
        assert "opname" in str(exc).casefold()


def test_record_out_negative_blocked_then_override(tmp_path):
    store, _ = make_store(tmp_path)
    service.opname(store, family="CUP-16", component="MOULD", physical=1)
    try:
        service.record_out(store, family="CUP-16", component="MOULD", qty=3)
        assert False
    except ValueError as exc:
        assert "negatif" in str(exc)
    tx = service.record_out(store, family="CUP-16", component="MOULD", qty=3,
                            override_negative=True, keterangan="emergency")
    assert tx.qty == 3
    entries = store.read_ledger(store.load())
    assert any(e.kind == "OVERRIDE" for e in entries)


def test_opname_opening_then_adjustment(tmp_path):
    store, _ = make_store(tmp_path)
    res = service.opname(store, family="DATAR-12", component="PLUG ASSIST", physical=4, pic="Davi")
    assert res["kind"] == "OPENING" and res["new_awal"] == 4
    views = {v.item.key: v for v in service.stock_views(store)}
    assert views[("datar-12", "plug assist")].stock == 4

    service.record_out(store, family="DATAR-12", component="PLUG ASSIST", qty=1)
    res2 = service.opname(store, family="DATAR-12", component="PLUG ASSIST", physical=2, pic="Davi")
    assert res2["kind"] == "ADJUSTMENT"
    # sistem 4-1=3, fisik 2 -> selisih -1, Stock Awal baru 3
    assert res2["previous"] == 4 and res2["diff"] == -1 and res2["new_awal"] == 3

    entries = store.read_ledger(store.load())
    assert [e.kind for e in entries] == ["OPENING", "ADJUSTMENT"]
    # history opname utuh, stock konsisten
    views = {v.item.key: v for v in service.stock_views(store)}
    assert views[("datar-12", "plug assist")].stock == 2


def test_opname_unknown_family_rejected(tmp_path):
    store, _ = make_store(tmp_path)
    try:
        service.opname(store, family="XX", component="MOULD", physical=1)
        assert False
    except ValueError:
        pass


def test_master_tooling_never_modified_by_transactions(tmp_path):
    store, wb_path = make_store(tmp_path)
    before = store.load()["MASTER TOOLING"]["A5"].value
    service.opname(store, family="CUP-16", component="MOULD", physical=2)
    service.record_out(store, family="CUP-16", component="MOULD", qty=1)
    after = store.load()["MASTER TOOLING"]["A5"].value
    assert before == after
