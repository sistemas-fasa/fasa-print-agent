import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fasa_print_agent.remito_layout import (  # noqa: E402
    DEFAULT_LAYOUT,
    PAGE_HEIGHT_MM,
    PAGE_WIDTH_MM,
    Position,
    RemitoLayout,
)


def test_page_is_a5_landscape():
    assert PAGE_WIDTH_MM == 210.0
    assert PAGE_HEIGHT_MM == 148.0
    assert PAGE_WIDTH_MM > PAGE_HEIGHT_MM


def test_default_layout_inside_paper():
    assert DEFAULT_LAYOUT.check_bounds() == []


def test_offsets_default_zero_and_applied():
    assert (DEFAULT_LAYOUT.offset_x_mm, DEFAULT_LAYOUT.offset_y_mm) == (0.0, 0.0)
    lay = DEFAULT_LAYOUT.with_offsets(1.5, -0.5)
    p = lay.apply_offset(Position(10.0, 20.0))
    assert (p.x_mm, p.y_mm) == (11.5, 19.5)
    # El original no muta (frozen).
    assert DEFAULT_LAYOUT.apply_offset(Position(10.0, 20.0)) == Position(10.0, 20.0)


def test_out_of_bounds_detected():
    lay = RemitoLayout(numero=Position(999.0, 9.0))
    errors = lay.check_bounds()
    assert any("numero.x_mm" in e for e in errors)


def test_layout_json_roundtrip_and_unknown_keys_ignored():
    d = DEFAULT_LAYOUT.to_dict()
    d["numero"] = {"x_mm": 160.0, "y_mm": 10.0}
    d["offset_x_mm"] = 2.0
    d["campo_futuro_desconocido"] = 123
    lay = RemitoLayout.from_dict(d)
    assert lay.numero == Position(160.0, 10.0)
    assert lay.offset_x_mm == 2.0
    assert lay.check_bounds() == []


def test_no_position_outside_after_offset():
    # Offset de calibración típico ±3 mm no debe sacar nada del papel.
    lay = DEFAULT_LAYOUT.with_offsets(3.0, -3.0)
    assert lay.check_bounds() == []
