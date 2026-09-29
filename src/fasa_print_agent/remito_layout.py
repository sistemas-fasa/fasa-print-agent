"""Layout físico del REMITO_CTACTE sobre papel preimpreso A5 apaisado.

El papel ya contiene logo, datos fiscales, letra R, rótulos, líneas y
cuadros. Este módulo solo describe DÓNDE van los datos variables.

Convención:
- Página: 210 mm (ancho) x 148 mm (alto), apaisada.
- Origen: esquina SUPERIOR IZQUIERDA de la hoja.
- Eje X: crece hacia la derecha. Eje Y: crece hacia ABAJO.
  (Es como se mide con regla sobre el papel físico; la conversión a
  coordenadas PDF —origen abajo-izquierda— la hace `remito_pdf`.)
- Todas las posiciones están centralizadas ACÁ. No poner números de
  coordenadas en otro módulo.

Calibración: imprimir, medir el desvío con regla (±1/2 mm) y ajustar
`OFFSET_X_MM` / `OFFSET_Y_MM` (desvío global) o la posición individual.
Sin tocar la lógica del documento.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

PAGE_WIDTH_MM = 210.0
PAGE_HEIGHT_MM = 148.0

OFFSET_X_MM = 0.0
OFFSET_Y_MM = 0.0


@dataclass(frozen=True)
class Position:
    """Posición física en mm desde la esquina superior izquierda."""

    x_mm: float
    y_mm: float


@dataclass(frozen=True)
class RemitoLayout:
    """Todas las posiciones de datos variables del remito. Valores iniciales
    de calibración: estimados desde la referencia visual, a corregir con
    impresiones físicas."""

    offset_x_mm: float = OFFSET_X_MM
    offset_y_mm: float = OFFSET_Y_MM

    # Zona superior derecha (número bajado 15 mm el 29/09/2026: tapaba
    # el Nº preimpreso).
    numero: Position = Position(163.0, 30.0)
    fecha: Position = Position(163.0, 37.0)

    # Cabecera de cliente. El código se dibuja entre corchetes luego del
    # nombre ("NOMBRE [CODIGO]"), no en renglón propio.
    cliente_nombre: Position = Position(28.0, 36.0)
    cliente_domicilio: Position = Position(28.0, 42.0)
    cliente_telefono: Position = Position(28.0, 47.0)
    cliente_localidad: Position = Position(100.0, 47.0)
    # Columna derecha alineada a la misma izquierda (x=163).
    cliente_cuit: Position = Position(163.0, 41.0)
    cliente_cond_iva: Position = Position(163.0, 48.0)

    # Detalle de artículos (tabla, zona central).
    items_header_y_mm: float = 53.0
    items_origin: Position = Position(12.0, 58.0)
    items_row_height_mm: float = 6.0
    items_max_rows: int = 10
    col_cantidad_x_mm: float = 12.0
    col_cantidad_w_mm: float = 22.0
    col_articulo_x_mm: float = 36.0
    col_articulo_w_mm: float = 28.0
    col_detalle_x_mm: float = 66.0
    col_detalle_w_mm: float = 132.0

    # Mensajes / observaciones hacia el pie.
    observaciones: Position = Position(12.0, 121.0)

    # Pie: transportista (bajado 10 mm el 29/09/2026; CUIT además
    # 50 mm a la izquierda).
    transp_nombre: Position = Position(28.0, 139.0)
    transp_cuit: Position = Position(90.0, 139.0)
    transp_domicilio: Position = Position(28.0, 145.0)
    transp_chofer: Position = Position(140.0, 145.0)

    # Tipografías (pt).
    font_numero_size: float = 13.0
    font_base_size: float = 9.0
    font_items_size: float = 9.0
    font_footer_size: float = 8.5

    def apply_offset(self, pos: Position) -> Position:
        """Aplica la calibración global X/Y a una posición."""
        return Position(pos.x_mm + self.offset_x_mm,
                        pos.y_mm + self.offset_y_mm)

    def with_offsets(self, dx_mm: float, dy_mm: float) -> "RemitoLayout":
        """Copia del layout con offsets globales reemplazados."""
        from dataclasses import replace

        return replace(self, offset_x_mm=dx_mm, offset_y_mm=dy_mm)

    def variable_positions(self) -> dict[str, Position]:
        """Posiciones puntuales (con offset aplicado) para chequeo de bordes."""
        names = [
            "numero", "fecha",
            "cliente_nombre", "cliente_domicilio",
            "cliente_telefono", "cliente_localidad",
            "cliente_cuit", "cliente_cond_iva",
            "observaciones",
            "transp_nombre", "transp_cuit",
            "transp_domicilio", "transp_chofer",
        ]
        return {n: self.apply_offset(getattr(self, n)) for n in names}

    def check_bounds(self) -> list[str]:
        """Devuelve lista de errores si alguna posición cae fuera del papel."""
        errors: list[str] = []
        for name, p in self.variable_positions().items():
            if not (0.0 <= p.x_mm <= PAGE_WIDTH_MM):
                errors.append(f"{name}.x_mm={p.x_mm} fuera de [0, {PAGE_WIDTH_MM}]")
            if not (0.0 <= p.y_mm <= PAGE_HEIGHT_MM):
                errors.append(f"{name}.y_mm={p.y_mm} fuera de [0, {PAGE_HEIGHT_MM}]")
        ox = self.apply_offset(self.items_origin)
        bottom = ox.y_mm + self.items_row_height_mm * self.items_max_rows
        if bottom > PAGE_HEIGHT_MM:
            errors.append(f"items exceden el pie: fin={bottom} > {PAGE_HEIGHT_MM}")
        right = self.col_detalle_x_mm + self.col_detalle_w_mm + self.offset_x_mm
        if right > PAGE_WIDTH_MM:
            errors.append(f"col_detalle excede ancho: fin={right} > {PAGE_WIDTH_MM}")
        return errors

    def to_dict(self) -> dict:
        """Serializa a dict plano (para --layout-json)."""
        out: dict = {
            "offset_x_mm": self.offset_x_mm,
            "offset_y_mm": self.offset_y_mm,
            "items_header_y_mm": self.items_header_y_mm,
            "items_row_height_mm": self.items_row_height_mm,
            "items_max_rows": self.items_max_rows,
            "col_cantidad_x_mm": self.col_cantidad_x_mm,
            "col_cantidad_w_mm": self.col_cantidad_w_mm,
            "col_articulo_x_mm": self.col_articulo_x_mm,
            "col_articulo_w_mm": self.col_articulo_w_mm,
            "col_detalle_x_mm": self.col_detalle_x_mm,
            "col_detalle_w_mm": self.col_detalle_w_mm,
            "font_numero_size": self.font_numero_size,
            "font_base_size": self.font_base_size,
            "font_items_size": self.font_items_size,
            "font_footer_size": self.font_footer_size,
        }
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, Position):
                out[f.name] = {"x_mm": v.x_mm, "y_mm": v.y_mm}
        out["items_origin"] = {"x_mm": self.items_origin.x_mm,
                               "y_mm": self.items_origin.y_mm}
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "RemitoLayout":
        """Crea un layout desde dict plano (claves desconocidas se ignoran)."""
        kwargs: dict = {}
        known = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key not in known:
                continue
            if isinstance(value, dict) and "x_mm" in value and "y_mm" in value:
                kwargs[key] = Position(float(value["x_mm"]), float(value["y_mm"]))
            else:
                kwargs[key] = value
        return cls(**kwargs)


DEFAULT_LAYOUT = RemitoLayout()
