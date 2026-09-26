"""Resolución estación + tipo → impresora Windows (SPEC §7, §15).

Flujo:
    estacion + tipo_impresion
        → impresora_maquina        → impresora lógica (alias)
        → impresoras               → destino utilizable por Windows

No se elige impresora arbitraria: si falta mapping → PRINTER_MAPPING_NOT_FOUND.
El esquema real de VFP debe auditarse (Fase 1); por eso la resolución es
tolerante a nombres de columna (mayúsculas/minúsculas) y a alias con
espacios. Ver `docs/INSTALL_SERVERFASA.md` y migración de ejemplo.
"""
from __future__ import annotations

from dataclasses import dataclass


class PrinterMappingNotFound(Exception):
    code = "PRINTER_MAPPING_NOT_FOUND"


class PrinterNotAvailable(Exception):
    code = "PRINTER_NOT_AVAILABLE"


@dataclass
class ResolvedPrinter:
    alias: str          # valor lógico de impresora_maquina (ej. Pedidos_Local_Comercial)
    windows_name: str   # destino utilizable por Windows (ej. Remito Cuenta Corriente / UNC / IP)


def _norm(s: object) -> str:
    return str(s or "").strip()


def _row_get(row: dict, *names: str) -> str:
    lower = {str(k).lower(): v for k, v in row.items()}
    for n in names:
        if n.lower() in lower and lower[n.lower()] not in (None, ""):
            return str(lower[n.lower()]).strip()
    return ""


def resolve_printer(conn, estacion: str, tipo_impresion: str) -> ResolvedPrinter:
    estacion = _norm(estacion)
    tipo_impresion = _norm(tipo_impresion)
    if not estacion or not tipo_impresion:
        raise PrinterMappingNotFound(
            f"Estación/tipo vacíos: estacion={estacion!r} tipo={tipo_impresion!r}"
        )

    with conn.cursor() as cur:
        # 1) alias lógico desde impresora_maquina (case-insensitive).
        cur.execute(
            """
            SELECT * FROM impresora_maquina
             WHERE UPPER(TRIM(maquina)) = UPPER(TRIM(%s))
               AND UPPER(TRIM(tipo_impresion)) = UPPER(TRIM(%s))
             LIMIT 1
            """,
            (estacion, tipo_impresion),
        )
        row = cur.fetchone()
        if row is None:
            # Fallback: algunas instalaciones usan columna `tipo` en vez de `tipo_impresion`.
            try:
                cur.execute(
                    """
                    SELECT * FROM impresora_maquina
                     WHERE UPPER(TRIM(maquina)) = UPPER(TRIM(%s))
                       AND UPPER(TRIM(tipo)) = UPPER(TRIM(%s))
                     LIMIT 1
                    """,
                    (estacion, tipo_impresion),
                )
                row = cur.fetchone()
            except Exception:
                row = None
        if row is None:
            raise PrinterMappingNotFound(
                f"Sin mapping para estacion={estacion!r} tipo={tipo_impresion!r}"
            )

        alias = _row_get(row, "impresora", "impresora_logica", "destino",
                         "printer", "nombre")
        if not alias:
            raise PrinterMappingNotFound(
                f"Mapping sin impresora lógica para {estacion!r}/{tipo_impresion!r}"
            )

        # 2) destino Windows desde impresoras.
        cur.execute(
            """
            SELECT * FROM impresoras
             WHERE UPPER(TRIM(nombre)) = UPPER(TRIM(%s))
                OR UPPER(TRIM(codigo)) = UPPER(TRIM(%s))
                OR UPPER(TRIM(alias)) = UPPER(TRIM(%s))
             LIMIT 1
            """,
            (alias, alias, alias),
        )
        irow = cur.fetchone()
        if irow is None:
            # El alias puede ser directamente el nombre Windows.
            return ResolvedPrinter(alias=alias, windows_name=alias)

        windows_name = _row_get(
            irow, "impresora_windows", "windows_name", "destino",
            "unc", "ip", "nombre", "codigo",
        )
        if not windows_name:
            raise PrinterMappingNotFound(
                f"Registro en impresoras sin destino para alias={alias!r}"
            )
        return ResolvedPrinter(alias=alias, windows_name=windows_name)
