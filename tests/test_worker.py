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


def _payload_job(payload, **kw):
    j = _job(archivo_path="", payload_json=payload)
    j.update(kw)
    return j


def _ok_conn(job):
    return FakeConn([
        one({"id": 1}), upd(1), one(job),                       # claim
        one({"impresora": "Alias"}), one({"nombre": "Imp_Real"}),  # resolve
        upd(1),                                                  # spooled
        upd(1),                                                  # printed
    ])


def _mock_print_env(monkeypatch):
    monkeypatch.setattr(windows_print, "list_printers", lambda: ["Imp_Real"])
    monkeypatch.setattr(windows_print, "printer_exists", lambda n: True)
    seen = {}
    monkeypatch.setattr(windows_print, "print_pdf",
                        lambda *a, **k: seen.setdefault("args", (a, k)))
    return seen


def _sample_payload():
    import json
    from pathlib import Path as P
    fix = P(__file__).resolve().parent.parent / "fixtures" / \
        "remito_ctacte_ejemplo.json"
    return json.loads(fix.read_text(encoding="utf-8"))


def test_payload_dict_genera_pdf_y_lo_imprime(monkeypatch, tmp_path):
    seen = _mock_print_env(monkeypatch)
    job = _payload_job(_sample_payload())
    assert worker.process_one(_ok_conn(job), _cfg()) is True
    (a, k) = seen["args"]
    assert a[0].endswith(".pdf") and "remito-1-956" in a[0]


def test_payload_string_json_tambien_vale(monkeypatch):
    import json
    seen = _mock_print_env(monkeypatch)
    job = _payload_job(json.dumps(_sample_payload()))
    assert worker.process_one(_ok_conn(job), _cfg()) is True
    assert seen["args"][0][0].endswith(".pdf")


def test_archivo_tiene_prioridad_sobre_payload(monkeypatch, tmp_path):
    seen = _mock_print_env(monkeypatch)
    pdf = tmp_path / "legado.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    job = _payload_job(_sample_payload(), archivo_path=str(pdf))
    assert worker.process_one(_ok_conn(job), _cfg()) is True
    assert seen["args"][0][0] == str(pdf)


def test_payload_invalido_es_error_terminal(monkeypatch):
    _mock_print_env(monkeypatch)
    job = _payload_job("{no-json")
    conn = FakeConn([one({"id": 1}), upd(1), one(job),
                     one({"impresora": "A"}), one({"nombre": "Imp_Real"}),
                     upd(1)])
    assert worker.process_one(conn, _cfg()) is True
    assert "PAYLOAD_INVALIDO" in str(conn.executed[-1][1])


def test_mas_de_12_items_no_se_imprime(monkeypatch):
    _mock_print_env(monkeypatch)
    items = [{"cantidad": "1,00", "articulo": f"A{i}",
              "detalle": f"D{i}"} for i in range(13)]
    payload = dict(_sample_payload(), items=items)
    job = _payload_job(payload)
    conn = FakeConn([one({"id": 1}), upd(1), one(job),
                     one({"impresora": "A"}), one({"nombre": "Imp_Real"}),
                     upd(1)])
    assert worker.process_one(conn, _cfg()) is True
    assert "PAYLOAD_INVALIDO" in str(conn.executed[-1][1])


def test_sin_documento_es_error_terminal():
    job = _job(archivo_path="", payload_json=None)
    conn = FakeConn([one({"id": 1}), upd(1), one(job), upd(1)])
    assert worker.process_one(conn, _cfg()) is True
    assert "DOCUMENTO_FALTANTE" in str(conn.executed[-1][1])


def test_payload_sin_generador_para_otro_documento(monkeypatch):
    _mock_print_env(monkeypatch)
    job = _job(documento_tipo="FACTURA", archivo_path="",
               payload_json={"a": 1},
               tipo_impresion="REMITO_CTACTE")
    job["documento_tipo"] = "FACTURA"
    cfg = _cfg(allowed_documento_tipos=["REMITO", "FACTURA"])
    conn = FakeConn([one({"id": 1}), upd(1), one(job),
                     one({"impresora": "A"}), one({"nombre": "Imp_Real"}),
                     upd(1)])
    assert worker.process_one(conn, cfg) is True
    assert "GENERADOR_NO_SOPORTADO" in str(conn.executed[-1][1])
