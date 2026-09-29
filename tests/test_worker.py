import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fasa_print_agent import worker, windows_print  # noqa: E402
from fasa_print_agent.config import AgentConfig  # noqa: E402
from conftest_fake import FakeConn, one, upd  # noqa: E402


def _cfg(**kw):
    base = dict(agent_name="SERVERFASA",
                allowed_tipos_impresion=["REMITO_CTACTE"],
                allowed_documento_tipos=["REMITO"], max_copias=5,
                history_file="off")
    base.update(kw)
    return AgentConfig(**base)


def _job(**kw):
    j = dict(id=1, estacion="VENTAS-07", tipo_impresion="REMITO_CTACTE",
             documento_tipo="REMITO", documento_id="956",
             copias=1, archivo_path="x.pdf", intentos=1, max_intentos=3)
    j.update(kw)
    return j


def test_rechaza_tipo_no_permitido(monkeypatch):
    conn = FakeConn([one({"id": 1}), upd(1), one(_job(tipo_impresion="FACTURA")), upd(1)])
    assert worker.process_one(conn, _cfg()) is True
    _last_sql, last_params = conn.executed[-1]
    assert "TIPO_NO_PERMITIDO" in str(last_params)


def test_rechaza_copias_excesivas(monkeypatch):
    conn = FakeConn([one({"id": 1}), upd(1), one(_job(copias=99)), upd(1)])
    assert worker.process_one(conn, _cfg()) is True
    assert "COPIAS_INVALIDAS" in str(conn.executed[-1][1])


def test_flujo_ok(monkeypatch, tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    job = _job(archivo_path=str(pdf))
    conn = FakeConn([
        one({"id": 1}), upd(1), one(job),                       # claim
        one({"impresora": "Alias"}), one({"nombre": "Imp_Real"}),  # resolve
        upd(1),                                                  # spooled
        upd(1),                                                  # printed
    ])
    monkeypatch.setattr(windows_print, "list_printers", lambda: ["Imp_Real"])
    monkeypatch.setattr(windows_print, "printer_exists", lambda n: True)
    printed = {}
    monkeypatch.setattr(windows_print, "print_pdf",
                        lambda *a, **k: printed.setdefault("ok", True))
    assert worker.process_one(conn, _cfg()) is True
    assert printed.get("ok") is True


def test_mapping_faltante_es_error_terminal(monkeypatch):
    job = _job()
    conn = FakeConn([one({"id": 1}), upd(1), one(job),
                     one(None), one(None), upd(1)])
    assert worker.process_one(conn, _cfg()) is True
    assert "PRINTER_MAPPING_NOT_FOUND" in str(conn.executed[-1][1])
