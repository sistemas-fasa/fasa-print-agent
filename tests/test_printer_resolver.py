import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fasa_print_agent import printer_resolver as pr  # noqa: E402
from fasa_print_agent.printer_resolver import PrinterMappingNotFound  # noqa: E402

from conftest_fake import FakeConn, one  # noqa: E402


def test_resolve_ok_via_impresoras():
    conn = FakeConn([
        one({"impresora": "Pedidos_Local_Comercial"}),
        one({"impresora_windows": "Remito Cuenta Corriente"}),
    ])
    r = pr.resolve_printer(conn, "VENTAS-07", "REMITO_REP_99")
    assert r.alias == "Pedidos_Local_Comercial"
    assert r.windows_name == "Remito Cuenta Corriente"


def test_resolve_alias_directo_sin_fila_impresoras():
    conn = FakeConn([
        one({"impresora": "HP_Local"}),
        one(None),
    ])
    r = pr.resolve_printer(conn, "CAJA-04", "REMITO_CTACTE")
    assert r.windows_name == "HP_Local"


def test_resolve_sin_mapping():
    conn = FakeConn([one(None), one(None)])
    with pytest.raises(PrinterMappingNotFound):
        pr.resolve_printer(conn, "NADIE", "REMITO_CTACTE")


def test_resolve_case_insensitive_columns():
    conn = FakeConn([
        one({"IMPREsora": "  Alias_X  "}),
        one({"UNC": "\\\\SRV\\Imp"}),
    ])
    r = pr.resolve_printer(conn, "ventas-07", "remito_ctacte")
    assert r.windows_name == "\\\\SRV\\Imp"
