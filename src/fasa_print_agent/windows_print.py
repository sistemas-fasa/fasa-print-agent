"""Interacción con el spooler de Windows (SPEC §17, §21, §30).

Backend primario: GDI directo (`print_backend.WindowsGdiBackend`):
raster del PDF → DC de impresora A5 apaisado → spooler. Sin Adobe, sin
navegador, sin diálogos, sin `ShellExecute`.

Compatibilidad: si `SUMATRA_PDF_PATH` está configurado se mantiene como
fallback explícito (instalaciones que ya lo usan). `ShellExecute(print)`
se eliminó: dependía del visor asociado y no es apto para un servicio.

En no-Windows (dev/tests) estas funciones degradan a errores claros.
La generación del PDF vive en `remito_pdf` y no depende de Windows.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .print_backend import PrintError, SpoolResult, get_backend

__all__ = ["PrintError", "SpoolResult", "list_printers", "printer_exists",
           "print_pdf", "spool_pdf_with_result"]


def list_printers() -> list[str]:
    return get_backend().list_printers()


def printer_exists(name: str) -> bool:
    return get_backend().printer_exists(name)


def spool_pdf_with_result(pdf_path: str, printer_name: str, copies: int = 1,
                          dpi: int = 300,
                          sumatra_path: str = "") -> SpoolResult:
    """Envía al spooler y retorna detalle (incluye job id de Windows)."""
    pdf = Path(pdf_path)
    if not pdf.is_file():
        raise PrintError("FILE_NOT_FOUND", f"PDF no existe: {pdf_path}")
    copies = max(1, int(copies or 1))

    if sumatra_path and Path(sumatra_path).is_file():
        _print_via_sumatra(str(pdf), printer_name, copies, sumatra_path)
        return SpoolResult(printer_name=printer_name, copies=copies,
                           pages_spooled=0, windows_job_id=0)

    return get_backend().spool_pdf(str(pdf), printer_name,
                                   copies=copies, dpi=dpi)


def print_pdf(pdf_path: str, printer_name: str, copies: int = 1,
              sumatra_path: str = "", timeout: int = 60,
              dpi: int = 300) -> None:
    """Compatibilidad con `worker`: lanza PrintError si falla."""
    spool_pdf_with_result(pdf_path, printer_name, copies=copies, dpi=dpi,
                          sumatra_path=sumatra_path)


def _print_via_sumatra(pdf_path: str, printer_name: str, copies: int,
                       sumatra_path: str, timeout: int = 60) -> None:
    for _ in range(copies):
        cmd = [sumatra_path, "-print-to", printer_name,
               "-print-settings", "noscale", "-silent", pdf_path]
        try:
            proc = subprocess.run(cmd, capture_output=True,
                                  timeout=timeout, check=False)
        except subprocess.TimeoutExpired as e:
            raise PrintError("PRINT_TIMEOUT",
                             f"SumatraPDF timeout en {printer_name}") from e
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", "replace")[:500]
            raise PrintError("SPOOLER_REJECTED",
                             f"SumatraPDF rc={proc.returncode}: {err}")
