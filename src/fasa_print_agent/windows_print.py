"""Interacción con el spooler de Windows (SPEC §17, §21, §30).

- `list_printers()`: impresoras que Windows ve desde la cuenta del agente.
- `print_pdf()`: imprime un PDF en una impresora dada, N copias.
  - Si hay SumatraPDF configurado → `SumatraPDF.exe -print-to "Printer" ...`
  - Si no → `ShellExecute(print)` (fallback, 1 copia).
En no-Windows (dev/tests) estas funciones degradan a errores claros.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


class PrintError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def list_printers() -> list[str]:
    try:
        import win32print  # type: ignore
    except ImportError:
        return []
    printers = win32print.EnumPrinters(
        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    )
    # EnumPrinters retorna tuplas (flags, desc, name, comment)
    return sorted({p[2] for p in printers if len(p) >= 3 and p[2]})


def printer_exists(name: str) -> bool:
    return any(p.lower() == name.lower() for p in list_printers())


def print_pdf(pdf_path: str, printer_name: str, copies: int = 1,
              sumatra_path: str = "", timeout: int = 60) -> None:
    pdf = Path(pdf_path)
    if not pdf.is_file():
        raise PrintError("FILE_NOT_FOUND", f"PDF no existe: {pdf_path}")
    copies = max(1, int(copies or 1))

    if sumatra_path and Path(sumatra_path).is_file():
        for _ in range(copies):
            cmd = [sumatra_path, "-print-to", printer_name,
                   "-print-settings", "noscale", "-silent", str(pdf)]
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
        return

    # Fallback ShellExecute (solo Windows, 1 copia efectiva).
    if os.name != "nt":
        raise PrintError("NO_PRINT_BACKEND",
                         "Sin SumatraPDF y fuera de Windows: no hay backend")
    try:
        import win32api  # type: ignore
        import win32print  # type: ignore
        # Fija impresora por defecto temporalmente para respetar destino.
        current = win32print.GetDefaultPrinter()
        try:
            win32print.SetDefaultPrinter(printer_name)
            for _ in range(copies):
                rc = win32api.ShellExecute(0, "print", str(pdf), None, ".", 0)
                if rc is not None and int(rc) <= 32:
                    raise PrintError("SPOOLER_REJECTED",
                                     f"ShellExecute(print) rc={rc}")
        finally:
            try:
                win32print.SetDefaultPrinter(current)
            except Exception:
                pass
    except PrintError:
        raise
    except Exception as e:
        raise PrintError("SPOOLER_ERROR", f"{type(e).__name__}: {e}") from e
