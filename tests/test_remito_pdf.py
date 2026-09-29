import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fasa_print_agent.remito_data import (  # noqa: E402
    RemitoCtaCte,
    RemitoItem,
    sample_fixture,
)
from fasa_print_agent.remito_layout import Position, RemitoLayout  # noqa: E402
from fasa_print_agent.remito_pdf import (  # noqa: E402
    MM_TO_PT,
    build_remito_pdf,
    page_size_pt,
)

REPO = Path(__file__).resolve().parent.parent


def test_page_size_is_exactly_210x148mm():
    w_pt, h_pt = page_size_pt()
    assert w_pt == 210.0 * MM_TO_PT
    assert h_pt == 148.0 * MM_TO_PT


def test_build_pdf_valid_header_and_mediabox(tmp_path):
    out = build_remito_pdf(sample_fixture(), tmp_path / "remito.pdf")
    raw = out.read_bytes()
    assert raw.startswith(b"%PDF")
    # MediaBox debe ser 210x148 mm en puntos (±0.5 pt).
    import re

    m = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]",
                  raw)
    assert m, "PDF sin MediaBox"
    x0, y0, x1, y1 = map(float, m.groups())
    assert (x0, y0) == (0.0, 0.0)
    assert abs(x1 - 210.0 * MM_TO_PT) < 0.5
    assert abs(y1 - 148.0 * MM_TO_PT) < 0.5


def test_build_pdf_text_extractable_with_fixture_data(tmp_path):
    out = build_remito_pdf(sample_fixture(), tmp_path / "r.pdf")
    import fitz

    doc = fitz.open(str(out))
    try:
        assert doc.page_count == 1
        page = doc[0]
        rect = page.rect
        assert abs(rect.width - 210.0 * 72 / 25.4) < 0.5
        assert abs(rect.height - 148.0 * 72 / 25.4) < 0.5
        text = page.get_text()
    finally:
        doc.close()
    for expected in ("0004-00000956", "29/09/2026", "VOGEL JOSE OSCAR",
                     "00040", "20-23347203-5", "10,00", "PE00037",
                     "Perfil T 25mm", "CENTRAL ARGENTINO S.A.",
                     "30-54650428-6", "AV BUCHARDO 2413"):
        assert expected in text, expected


def test_cliente_extendido_y_titulos_items(tmp_path):
    import fitz

    data = sample_fixture()
    data.cliente_domicilio = "AV MITRE 123"
    data.cliente_telefono = "3743-511809"
    data.cliente_cp = "3333"
    data.cliente_localidad = "PUERTO RICO"
    out = build_remito_pdf(data, tmp_path / "ext.pdf")
    doc = fitz.open(str(out))
    try:
        text = doc[0].get_text()
    finally:
        doc.close()
    assert "VOGEL JOSE OSCAR [00040]" in text
    assert "AV MITRE 123" in text
    assert "3743-511809" in text
    assert "3333 - PUERTO RICO" in text
    for title in ("CANTIDAD", "ARTICULO", "DETALLE"):
        assert title in text, title


def test_fixture_conforma_al_schema_erp():
    """El ejemplo del contrato trae la forma que el ERP debe enviar."""
    schema = json.loads((REPO / "schemas" / "remito_ctacte.schema.json")
                        .read_text(encoding="utf-8"))
    raw = json.loads((REPO / "fixtures" / "remito_ctacte_ejemplo.json")
                     .read_text(encoding="utf-8"))
    assert set(schema["properties"]) >= {
        "numero", "fecha", "cliente_nombre", "cliente_codigo",
        "cliente_cuit", "cliente_cond_iva", "cliente_domicilio",
        "cliente_telefono", "cliente_cp", "cliente_localidad",
        "items", "observaciones", "transp_nombre", "transp_cuit",
        "transp_domicilio", "transp_chofer",
    }
    assert set(raw) >= set(schema["properties"]) - set()
    for key in ("numero", "cliente_nombre", "items"):
        assert raw[key], key
    assert isinstance(raw["items"], list) and raw["items"]
    assert set(raw["items"][0]) >= {"cantidad", "articulo", "detalle"}


def _items_payload(n: int):
    raw = json.loads((REPO / "fixtures" / "remito_ctacte_ejemplo.json")
                     .read_text(encoding="utf-8"))
    raw["items"] = [{"cantidad": f"{i},00", "articulo": f"AR{i:05d}",
                     "detalle": f"Detalle sintético {i}"} for i in range(1, n + 1)]
    return RemitoCtaCte.from_dict(raw)


def test_10_11_12_items_generan_sin_salirse(tmp_path):
    import fitz

    for n in (10, 11, 12):
        out = build_remito_pdf(_items_payload(n), tmp_path / f"r{n}.pdf")
        doc = fitz.open(str(out))
        try:
            text = doc[0].get_text()
            bottoms = [r.y1 for r in doc[0].search_for(f"AR{n:05d}")]
        finally:
            doc.close()
        assert f"AR{n:05d}" in text
        # Última fila por encima del renglón de observaciones (y=121mm).
        # fitz usa origen arriba-izquierda en puntos.
        assert bottoms, n
        assert bottoms[0] < 121.0 * 72 / 25.4, n


def test_texto_largo_se_trunca_con_puntos(tmp_path):
    import fitz

    data = _items_payload(1)
    data.items[0].detalle = "X" * 200
    out = build_remito_pdf(data, tmp_path / "long.pdf")
    doc = fitz.open(str(out))
    try:
        text = doc[0].get_text()
    finally:
        doc.close()
    assert "…" in text
    assert "X" * 200 not in text


def test_mas_de_12_items_se_rechaza_sin_truncar(tmp_path):
    from fasa_print_agent.remito_pdf import TooManyItemsError

    try:
        build_remito_pdf(_items_payload(13), tmp_path / "r13.pdf")
    except TooManyItemsError as e:
        assert e.code == "PAYLOAD_INVALIDO"
    else:
        raise AssertionError("debió rechazar 13 ítems")
    assert not (tmp_path / "r13.pdf").exists()


def test_repo_fixture_matches_sample():
    raw = json.loads((REPO / "fixtures" / "remito_ctacte_ejemplo.json")
                     .read_text(encoding="utf-8"))
    data = RemitoCtaCte.from_dict(raw)
    assert data.numero == sample_fixture().numero == "0004-00000956"
    assert len(data.items) == 1
    assert data.to_dict() == sample_fixture().to_dict()


def test_data_roundtrip():
    data = sample_fixture()
    assert RemitoCtaCte.from_dict(data.to_dict()).to_dict() == data.to_dict()
    assert RemitoItem.from_dict({}).to_dict() == {"cantidad": "", "articulo": "",
                                                  "detalle": ""}


def test_build_pdf_rejects_non_pdf_extension(tmp_path):
    try:
        build_remito_pdf(sample_fixture(), tmp_path / "r.txt")
    except ValueError:
        pass
    else:
        raise AssertionError("debió rechazar extensión no .pdf")


def test_build_pdf_rejects_layout_out_of_bounds(tmp_path):
    bad = RemitoLayout(numero=Position(999, 9))
    try:
        build_remito_pdf(sample_fixture(), tmp_path / "r.pdf", bad)
    except ValueError:
        pass
    else:
        raise AssertionError("debió rechazar layout fuera del papel")


def test_build_pdf_deterministic_positions_with_offset(tmp_path):
    """Mismo dato + distinto offset → texto desplazado solo en Y/X esperados."""
    import fitz

    def origin_of(layout):
        out = tmp_path / f"r-{layout.offset_x_mm}-{layout.offset_y_mm}.pdf"
        build_remito_pdf(sample_fixture(), out, layout)
        doc = fitz.open(str(out))
        try:
            rects = doc[0].search_for("0004-00000956")
            assert rects, "número de remito no encontrado en el PDF"
            return (rects[0].x0, rects[0].y0)
        finally:
            doc.close()

    base_xy = origin_of(RemitoLayout())
    moved_xy = origin_of(RemitoLayout().with_offsets(2.0, 2.0))
    # El número de remito aparece en ambos; sus coordenadas difieren en
    # 2mm→puntos en X y +2mm→puntos en Y (fitz usa origen arriba-izquierda,
    # Y hacia abajo, igual que el layout físico).
    k = MM_TO_PT
    assert abs((moved_xy[0] - base_xy[0]) - 2.0 * k) < 1.0
    assert abs((moved_xy[1] - base_xy[1]) - 2.0 * k) < 1.0
