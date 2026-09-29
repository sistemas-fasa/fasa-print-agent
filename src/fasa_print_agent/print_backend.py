"""Backends de impresión (SPEC §17, §21, §30).

Separación de responsabilidades:

- `remito_pdf` genera el PDF (multiplataforma, testeable sin Windows).
- Este módulo lo lleva al spooler de Windows.

Decisión documentada: NO se usa `ShellExecute("print")` porque delega en
el visor PDF asociado (Adobe/Edge), sus diálogos y sus asociaciones de
archivos: no es silencioso ni determinista desde un servicio. Tampoco se
envía el PDF en RAW al spooler porque la mayoría de las impresoras de
FASA no interpretan PDF directo.

Mecanismo: se rasteriza cada página del PDF a BMP con PyMuPDF al DPI
elegido y se pinta con GDI (`StretchBlt`) sobre un DC de impresora
configurado explícitamente en A5 apaisado vía DEVMODE en memoria
(sin modificar los defaults persistentes de la impresora). Sin Adobe,
sin navegador, sin diálogos.

Semántica de resultado (SPEC §10): `SpoolResult.windows_job_id` es el ID
que el spooler aceptó. "Enviado al spooler" NO afirma que el papel salió
físicamente: Windows no confirma eso de forma fiable.
"""
from __future__ import annotations

import abc
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


class PrintError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class SpoolResult:
    printer_name: str
    copies: int
    pages_spooled: int
    windows_job_id: int = 0


class PrintBackend(abc.ABC):
    """Interfaz de impresión. El código Windows vive solo en las
    implementaciones concretas."""

    @abc.abstractmethod
    def list_printers(self) -> list[str]:
        ...

    def printer_exists(self, name: str) -> bool:
        return any(p.lower() == name.lower() for p in self.list_printers())

    @abc.abstractmethod
    def spool_pdf(self, pdf_path: str, printer_name: str, copies: int = 1,
                  dpi: int = 300) -> SpoolResult:
        """Envía el PDF al spooler. Retorna SpoolResult si Windows lo aceptó,
        lanza PrintError en caso contrario."""
        ...


class SimulatedBackend(PrintBackend):
    """Backend no-Windows (dev/tests): nunca finge éxito."""

    def list_printers(self) -> list[str]:
        return []

    def spool_pdf(self, pdf_path: str, printer_name: str, copies: int = 1,
                  dpi: int = 300) -> SpoolResult:
        if not Path(pdf_path).is_file():
            raise PrintError("FILE_NOT_FOUND", f"PDF no existe: {pdf_path}")
        raise PrintError("NO_PRINT_BACKEND",
                         "Sin backend Windows: generar el PDF sí funciona, "
                         "imprimir requiere SERVERFASA/Windows")


class WindowsGdiBackend(PrintBackend):
    """Backend real: raster PyMuPDF → GDI sobre DC A5 apaisado."""

    PAPER_WIDTH_MM = 210.0
    PAPER_HEIGHT_MM = 148.0

    def list_printers(self) -> list[str]:
        try:
            import win32print  # type: ignore
        except ImportError:
            return []
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        return sorted({p[2] for p in printers if len(p) >= 3 and p[2]})

    def spool_pdf(self, pdf_path: str, printer_name: str, copies: int = 1,
                  dpi: int = 300) -> SpoolResult:
        import win32con  # type: ignore
        import win32ui  # type: ignore

        pdf = Path(pdf_path)
        if not pdf.is_file():
            raise PrintError("FILE_NOT_FOUND", f"PDF no existe: {pdf_path}")
        copies = max(1, int(copies or 1))
        dpi = max(72, min(600, int(dpi or 300)))

        if not self.printer_exists(printer_name):
            visible = self.list_printers()
            raise PrintError(
                "PRINTER_NOT_AVAILABLE",
                f"Impresora no visible: {printer_name!r}. "
                f"Visibles: {', '.join(visible[:10]) or '(ninguna)'}",
            )

        try:
            import fitz  # type: ignore  # PyMuPDF
        except ImportError as e:
            raise PrintError("MISSING_DEPENDENCY",
                             "Falta PyMuPDF (pip install pymupdf)") from e

        try:
            doc = fitz.open(str(pdf))
        except Exception as e:
            raise PrintError("PDF_INVALID", f"No se pudo abrir el PDF: {e}") from e
        try:
            pages = doc.page_count
            if pages < 1:
                raise PrintError("PDF_INVALID", "PDF sin páginas")
        finally:
            doc.close()

        # 1) Rasterizar páginas a BMP (origen arriba-izquierda = papel visto
        #    de frente; el formato BMP + GDI preserva la orientación).
        with tempfile.TemporaryDirectory(prefix="fasa-print-") as tmp:
            bmp_paths = self._render_pages_to_bmp(str(pdf), pages, dpi, tmp)

            # 2) DC de impresora en A5 apaisado (DEVMODE solo en memoria).
            hdc = win32ui.CreateDC()
            try:
                devmode = self._a5_landscape_devmode(printer_name)
                if devmode is not None:
                    hdc.CreatePrinterDC(printer_name, devmode)
                else:
                    hdc.CreatePrinterDC(printer_name)
            except Exception as e:
                raise PrintError("SPOOLER_ERROR",
                                 f"No se pudo crear DC para {printer_name!r}: "
                                 f"{type(e).__name__}: {e}") from e
            try:
                self._log_device_caps(hdc, printer_name)
                memdc = hdc.CreateCompatibleDC()
                bitmaps = []
                for bp in bmp_paths:
                    bmp = win32ui.CreateBitmap()
                    try:
                        with open(bp, "rb") as fh:
                            bmp.LoadBitmapFile(fh)
                    except Exception as e:
                        raise PrintError(
                            "RENDER_ERROR",
                            f"No se pudo cargar BMP renderizado: {e}") from e
                    bitmaps.append(bmp)

                # 3) Documento spooler: 1 StartDoc, N copias x M páginas.
                doc_name = f"FASA Remito {pdf.name}"
                try:
                    job_id = hdc.StartDoc(doc_name)
                except Exception as e:
                    raise PrintError(
                        "SPOOLER_REJECTED",
                        f"StartDoc rechazado en {printer_name!r}: {e}") from e
                try:
                    dev_w = hdc.GetDeviceCaps(110)  # PHYSICALWIDTH
                    dev_h = hdc.GetDeviceCaps(111)  # PHYSICALHEIGHT
                    for _ in range(copies):
                        for bmp in bitmaps:
                            info = bmp.GetInfo()
                            bw, bh = info["bmWidth"], info["bmHeight"]
                            hdc.StartPage()
                            try:
                                old = memdc.SelectObject(bmp)
                                try:
                                    hdc.StretchBlt(
                                        (0, 0), (dev_w, dev_h),
                                        memdc, (0, 0), (bw, bh),
                                        win32con.SRCCOPY)
                                finally:
                                    memdc.SelectObject(old)
                            finally:
                                hdc.EndPage()
                except Exception as e:
                    try:
                        hdc.AbortDoc()
                    except Exception:
                        pass
                    if isinstance(e, PrintError):
                        raise
                    raise PrintError(
                        "SPOOLER_ERROR",
                        f"Error durante spool en {printer_name!r}: "
                        f"{type(e).__name__}: {e}") from e
                try:
                    hdc.EndDoc()
                except Exception as e:
                    raise PrintError(
                        "SPOOLER_ERROR",
                        f"EndDoc falló en {printer_name!r}: {e}") from e
            finally:
                try:
                    hdc.DeleteDC()
                except Exception:
                    pass

        log.info("SPOOL_OK printer=%s copies=%d pages=%d job_id=%s",
                 printer_name, copies, pages, job_id)
        return SpoolResult(printer_name=printer_name, copies=copies,
                           pages_spooled=pages * copies,
                           windows_job_id=int(job_id or 0))

    def _render_pages_to_bmp(self, pdf_path: str, pages: int,
                             dpi: int, tmpdir: str) -> list[str]:
        import fitz  # type: ignore

        out: list[str] = []
        zoom = dpi / 72.0
        try:
            doc = fitz.open(pdf_path)
            try:
                for i in range(pages):
                    page = doc[i]
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom),
                                          alpha=False)
                    bp = str(Path(tmpdir) / f"page-{i + 1:03d}.bmp")
                    _save_pixmap_as_bmp(pix, bp)
                    out.append(bp)
            finally:
                doc.close()
        except Exception as e:
            raise PrintError("RENDER_ERROR",
                             f"No se pudo rasterizar el PDF: {e}") from e
        return out

    def _a5_landscape_devmode(self, printer_name: str):
        """DEVMODE en memoria con papel A5 apaisado. Retorna None si no se
        pudo (el caller usa defaults y lo advierte en logs). Nunca persiste
        cambios en la impresora (no se llama a SetPrinter)."""
        try:
            import win32con  # type: ignore
            import win32print  # type: ignore

            hprinter = win32print.OpenPrinter(printer_name)
            try:
                info = win32print.GetPrinter(hprinter, 2)
                devmode = info["pDevMode"]
            finally:
                try:
                    win32print.ClosePrinter(hprinter)
                except Exception:
                    pass
            if devmode is None:
                log.warning("Sin DEVMODE para %s; uso defaults", printer_name)
                return None
            devmode.PaperSize = win32con.DMPAPER_A5
            devmode.Orientation = win32con.DMORIENT_LANDSCAPE
            devmode.Fields = (devmode.Fields | win32con.DM_PAPERSIZE
                              | win32con.DM_ORIENTATION)
            return devmode
        except Exception as e:
            log.warning("No se pudo fijar A5 apaisado en %s (%s); "
                        "uso defaults de la impresora", printer_name, e)
            return None

    def _log_device_caps(self, hdc, printer_name: str) -> None:
        try:
            w_mm = hdc.GetDeviceCaps(4)    # HORZSIZE
            h_mm = hdc.GetDeviceCaps(6)    # VERTSIZE
            dx = hdc.GetDeviceCaps(88)     # LOGPIXELSX
            dy = hdc.GetDeviceCaps(90)     # LOGPIXELSY
            log.info("PRINTER_CAPS %s papel=%sx%smm dpi=%sx%s",
                     printer_name, w_mm, h_mm, dx, dy)
            if abs(w_mm - self.PAPER_WIDTH_MM) > 3 or \
               abs(h_mm - self.PAPER_HEIGHT_MM) > 3:
                log.warning("El papel del driver (%sx%smm) no es A5 210x148; "
                            "verificar bandeja/tamaño en %s",
                            w_mm, h_mm, printer_name)
        except Exception:
            pass


def get_backend() -> PrintBackend:
    """Backend apropiado para la plataforma actual."""
    if os.name == "nt":
        return WindowsGdiBackend()
    return SimulatedBackend()


def _save_pixmap_as_bmp(pix, path: str) -> None:
    """Escribe un `fitz.Pixmap` RGB sin alpha como BMP 24-bit.

    PyMuPDF no escribe BMP y GDI `LoadBitmapFile` lo requiere; este
    escritor mínimo evita sumar dependencias (sin Pillow).
    Filas de abajo hacia arriba, píxeles BGR, stride múltiplo de 4.
    """
    import struct

    if pix.alpha:
        raise ValueError("Pixmap con alpha no soportado")
    w, h, n = pix.width, pix.height, pix.n
    if n != 3:
        raise ValueError(f"Pixmap de {n} componentes, se esperan 3 (RGB)")
    stride = (w * 3 + 3) // 4 * 4
    raw = bytes(pix.samples)
    with open(path, "wb") as f:
        pixel_size = stride * h
        f.write(struct.pack("<2sIHHI", b"BM", 54 + pixel_size, 0, 0, 54))
        f.write(struct.pack("<IIIHHIIIIII", 40, w, h, 1, 24, 0,
                            pixel_size, 2835, 2835, 0, 0))
        pad = b"\x00" * (stride - w * 3)
        for y in range(h - 1, -1, -1):
            row = raw[y * w * 3:(y + 1) * w * 3]
            f.write(bytes(b for triplet in
                          (row[i:i + 3] for i in range(0, len(row), 3))
                          for b in (triplet[2], triplet[1], triplet[0])))
            f.write(pad)
