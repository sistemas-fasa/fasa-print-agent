import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fasa_print_agent import queue as q  # noqa: E402
from conftest_fake import FakeConn, one, upd  # noqa: E402


def test_claim_ok_atomico():
    job = {"id": 7, "estado": "TOMADO", "estacion": "VENTAS-07"}
    conn = FakeConn([one({"id": 7}), upd(1), one(job)])
    got = q.claim_next_job(conn, "SERVERFASA")
    assert got == job
    assert conn.committed >= 1
    # el UPDATE condicional usa estado=PENDIENTE
    update_sql = conn.executed[1][0]
    assert "AND estado" in update_sql


def test_claim_sin_pendientes():
    conn = FakeConn([one(None)])
    assert q.claim_next_job(conn, "SERVERFASA") is None


def test_claim_carrera_perdida_no_imprime():
    # Otro agente ganó el UPDATE (rowcount=0) → None, rollback.
    conn = FakeConn([one({"id": 9}), upd(0)])
    assert q.claim_next_job(conn, "SERVERFASA") is None
    assert conn.rolled_back >= 1


def test_mark_error_retry_reencola():
    conn = FakeConn([upd(1)])
    q.mark_error(conn, 5, "PRINTER_NOT_AVAILABLE", "x", retry=True)
    _sql, params = conn.executed[0]
    assert q.ESTADO_PENDIENTE in params and q.ESTADO_ERROR in params
