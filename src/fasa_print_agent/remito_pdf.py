"""Generación del PDF A5 apaisado del REMITO_CTACTE.

- Solo dibuja DATOS VARIABLES (el formulario preimpreso ya está en el papel).
- Página exacta de 210 x 148 mm.
- Coordenadas físicas en mm centralizadas en `remito_layout`.
- Multiplataforma: no importa nada de Windows. La impresión real vive en
  `print_backend` / `windows_print`.

Origen de coordenadas del layout: esquina superior izquierda, X→derecha,
Y→abajo. Conversión interna a puntos PDF (origen abajo-izquierda).
"""
from __future__ import annotations

from pathlib import Path

from .remito_data import RemitoCtaCte
from .remito_layout import (
    PAGE_HEIGHT_MM,
    PAGE_WIDTH_MM,
    RemitoLayout,
)

MM_TO_PT = 72.0 / 25.4


class TooManyItemsError(ValueError):
    """El payload supera items_max_rows: nunca truncar en silencio."""

    code = "PAYLOAD_INVALIDO"


def page_size_pt() -> tuple[float, float]:
    """Tamaño de página en puntos: (ancho, alto) = (210mm, 148mm)."""
    return (PAGE_WIDTH_MM * MM_TO_PT, PAGE_HEIGHT_MM * MM_TO_PT)


def _to_pt(x_mm: float, y_mm_down: float) -> tuple[float, float]:
    return (x_mm * MM_TO_PT, (PAGE_HEIGHT_MM - y_mm_down) * MM_TO_PT)


def build_remito_pdf(data: RemitoCtaCte, output_path: str | Path,
                     layout: RemitoLayout | None = None) -> Path:
    """Genera el PDF y lo guarda en `output_path`. Retorna la ruta."""
    from reportlab.pdfgen import canvas

    lay = layout or RemitoLayout()
    out = Path(output_path)
    if out.suffix.lower() != ".pdf":
        raise ValueError(f"La salida debe ser .pdf, recibido: {out}")
    if out.parent and str(out.parent) not in ("", "."):
        out.parent.mkdir(parents=True, exist_ok=True)

    errors = lay.check_bounds()
    if errors:
        raise ValueError("Layout fuera del papel: " + "; ".join(errors))
    if len(data.items) > lay.items_max_rows:
        raise TooManyItemsError(
            f"El remito trae {len(data.items)} ítems y el máximo es "
            f"{lay.items_max_rows}: se rechaza, no se trunca.")

    width_pt, height_pt = page_size_pt()
    c = canvas.Canvas(str(out), pagesize=(width_pt, height_pt))
    c.setTitle(f"Remito {data.numero}")
    c.setAuthor("FASA Print Agent")

    ox, oy = lay.offset_x_mm, lay.offset_y_mm

    def text(x_mm: float, y_mm: float, value: str, size: float,
             bold: bool = False, align: str = "left",
             max_width_mm: float = 0.0) -> None:
        value = value or ""
        if not value:
            return
        if max_width_mm > 0:
            value = _fit_to_width(c, value, bold, size, max_width_mm)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        px, py = _to_pt(x_mm + ox, y_mm + oy)
        if align == "right":
            c.drawRightString(px, py, value)
        else:
            c.drawString(px, py, value)

    # Número y fecha (zona superior derecha).
    p = lay.numero
    text(p.x_mm, p.y_mm, data.numero, lay.font_numero_size, bold=True)
    p = lay.fecha
    text(p.x_mm, p.y_mm, data.fecha, lay.font_base_size)

    # Cliente: nombre con código entre corchetes, más datos extendidos.
    nombre = data.cliente_nombre or ""
    if data.cliente_codigo:
        nombre = f"{nombre} [{data.cliente_codigo}]" if nombre else \
            f"[{data.cliente_codigo}]"
    text(lay.cliente_nombre.x_mm, lay.cliente_nombre.y_mm,
         nombre, lay.font_base_size, bold=True, max_width_mm=110.0)
    text(lay.cliente_domicilio.x_mm, lay.cliente_domicilio.y_mm,
         data.cliente_domicilio, lay.font_base_size, max_width_mm=110.0)
    text(lay.cliente_telefono.x_mm, lay.cliente_telefono.y_mm,
         data.cliente_telefono, lay.font_base_size, max_width_mm=65.0)
    localidad = data.cliente_localidad or ""
    if data.cliente_cp:
        localidad = f"{data.cliente_cp} - {localidad}" if localidad else \
            data.cliente_cp
    text(lay.cliente_localidad.x_mm, lay.cliente_localidad.y_mm,
         localidad, lay.font_base_size, max_width_mm=95.0)
    text(lay.cliente_cuit.x_mm, lay.cliente_cuit.y_mm,
         data.cliente_cuit, lay.font_base_size)
    text(lay.cliente_cond_iva.x_mm, lay.cliente_cond_iva.y_mm,
         data.cliente_cond_iva, lay.font_base_size)

    # Títulos de columnas del detalle.
    hy = lay.items_header_y_mm
    text(lay.col_cantidad_x_mm + lay.col_cantidad_w_mm, hy,
         "CANTIDAD", lay.font_items_size, bold=True, align="right")
    text(lay.col_articulo_x_mm, hy,
         "ARTICULO", lay.font_items_size, bold=True, max_width_mm=26.0)
    text(lay.col_detalle_x_mm, hy,
         "DETALLE", lay.font_items_size, bold=True, max_width_mm=130.0)

    # Ítems (zona central).
    for i, item in enumerate(data.items):
        row_y = lay.items_origin.y_mm + i * lay.items_row_height_mm
        text(lay.col_cantidad_x_mm + lay.col_cantidad_w_mm, row_y,
             item.cantidad, lay.font_items_size, align="right")
        text(lay.col_articulo_x_mm, row_y,
             item.articulo, lay.font_items_size, max_width_mm=26.0)
        text(lay.col_detalle_x_mm, row_y,
             item.detalle, lay.font_items_size, max_width_mm=130.0)

    # Observaciones.
    text(lay.observaciones.x_mm, lay.observaciones.y_mm,
         data.observaciones, lay.font_base_size, max_width_mm=185.0)

    # Pie: transportista.
    text(lay.transp_nombre.x_mm, lay.transp_nombre.y_mm,
         data.transp_nombre, lay.font_footer_size, max_width_mm=105.0)
    text(lay.transp_cuit.x_mm, lay.transp_cuit.y_mm,
         data.transp_cuit, lay.font_footer_size)
    text(lay.transp_domicilio.x_mm, lay.transp_domicilio.y_mm,
         data.transp_domicilio, lay.font_footer_size, max_width_mm=105.0)
    text(lay.transp_chofer.x_mm, lay.transp_chofer.y_mm,
         data.transp_chofer, lay.font_footer_size)

    c.showPage()
    c.save()
    return out


def _fit_to_width(c, value: str, bold: bool, size: float,
                  max_width_mm: float) -> str:
    """Trunca con '…' si el texto excede el ancho disponible."""
    font = "Helvetica-Bold" if bold else "Helvetica"
    max_pt = max_width_mm * MM_TO_PT
    if c.stringWidth(value, font, size) <= max_pt:
        return value
    ell = "…"
    while value and c.stringWidth(value + ell, font, size) > max_pt:
        value = value[:-1]
    return value + ell
