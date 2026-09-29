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
                  dpi: int = 300, dc_mode: str = "auto") -> SpoolResult:
        """Envía el PDF al spooler. Retorna SpoolResult si Windows lo aceptó,
        lanza PrintError en caso contrario. `dc_mode` selecciona la
        estrategia de papel/orientación del DC (solo Windows)."""
        ...


class SimulatedBackend(PrintBackend):
    """Backend no-Windows (dev/tests): nunca finge éxito."""

    def list_printers(self) -> list[str]:
        return []

    def spool_pdf(self, pdf_path: str, printer_name: str, copies: int = 1,
                  dpi: int = 300, dc_mode: str = "auto") -> SpoolResult:
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
                  dpi: int = 300, dc_mode: str = "auto") -> SpoolResult:
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

            # 2) DC de impresora en A5 apaisado (DEVMODE por-job en
            #    memoria; nunca persiste cambios en la impresora).
            try:
                hdc, release_dc = self._open_printer_dc(printer_name, dc_mode)
            except PrintError:
                raise
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
                known_job_ids = self._snapshot_job_ids(printer_name)
                try:
                    # pywin32 retorna None: el job id real se recupera con
                    # EnumJobs después de EndDoc (best-effort).
                    hdc.StartDoc(doc_name)
                    job_id = 0
                except Exception as e:
                    raise PrintError(
                        "SPOOLER_REJECTED",
                        f"StartDoc rechazado en {printer_name!r}: {e}") from e
                try:
                    # Rect destino 1:1 en mm: la imagen cubre la hoja física
                    # completa; el origen se desplaza por los márgenes no
                    # imprimibles (GDI recorta lo que caiga fuera).
                    dx, dy, dw, dh = _page_dest_rect(hdc)
                    log.info("DEST_RECT printer=%s x=%d y=%d w=%d h=%ddev",
                             printer_name, dx, dy, dw, dh)
                    for _ in range(copies):
                        for bmp in bitmaps:
                            info = bmp.GetInfo()
                            bw, bh = info["bmWidth"], info["bmHeight"]
                            hdc.StartPage()
                            try:
                                old = memdc.SelectObject(bmp)
                                try:
                                    hdc.StretchBlt(
                                        (dx, dy), (dw, dh),
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
                job_id = self._find_spooled_job_id(printer_name,
                                                   known_job_ids) or job_id
            finally:
                try:
                    release_dc()
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

    def _open_printer_dc(self, printer_name: str, dc_mode: str = "auto"):
        """Abre un DC de impresora y retorna `(dc, release_dc)`.

        Prueba las estrategias de `dc_mode` con verificación de tamaño
        real; fallback a defaults del driver (advierte en logs).
        DEVMODE siempre por-job en memoria: nada persiste.

        Estrategias (etiqueta, orientación, papel, largo, ancho), con
        largo/ancho en décimas de mm (0 = no tocar). Verificado 29/09/2026:
        la Epson L395 no trae A5: solo acepta tamaño usuario; además rota
        los jobs apaisados, por eso existe "user-portrait" (vertical con
        el mismo tamaño: el DC queda 210x148 sin rotación del driver).
        """
        import win32ui  # type: ignore

        strategies: dict[str, list[tuple[str, int, int, int, int]]] = {
            "auto": [
                ("A5-enum", 2, _DMPAPER_A5, 0, 0),
                ("USER-210x148-apais", 2, _DMPAPER_USER, 2100, 1480),
            ],
            "a5": [("A5-enum", 2, _DMPAPER_A5, 0, 0)],
            "user-landscape": [
                ("USER-210x148-apais", 2, _DMPAPER_USER, 2100, 1480)],
            "user-portrait": [
                ("USER-210x148-vert", 1, _DMPAPER_USER, 1480, 2100)],
        }
        chosen = strategies.get(dc_mode)
        if chosen is None:
            raise PrintError("DC_MODE_INVALID",
                             f"dc_mode={dc_mode!r}, válidos: "
                             f"{sorted(strategies)}")

        for label, orient, paper, plen, pwid in chosen:
            try:
                buf = _devmode_buffer(printer_name, orient, paper, plen, pwid)
                raw_hdc = _create_dc_with_devmode(printer_name, buf)
            except Exception as e:
                log.warning("DC %s (%s) no disponible: %s",
                            printer_name, label, e)
                continue
            dc = win32ui.CreateDCFromHandle(raw_hdc)
            w_mm, h_mm = dc.GetDeviceCaps(4), dc.GetDeviceCaps(6)
            if _is_a5_size(w_mm, h_mm):
                log.info("DC %s con %s por-job %dx%dmm (sin persistir)",
                         printer_name, label, w_mm, h_mm)
                return dc, lambda h=raw_hdc: _delete_dc(h)
            log.warning("DC %s (%s) informa %dx%dmm, no es A5; pruebo siguiente",
                        printer_name, label, w_mm, h_mm)
            try:
                _delete_dc(raw_hdc)
            except Exception:
                pass

        dc = win32ui.CreateDC()
        dc.CreatePrinterDC(printer_name)
        log.warning("DC %s con defaults del driver (sin A5 explícito)",
                    printer_name)

        def _release() -> None:
            try:
                dc.DeleteDC()
            except Exception:
                pass

        return dc, _release

    def _snapshot_job_ids(self, printer_name: str) -> set[int]:
        """IDs de jobs actuales en la cola (best-effort, nunca lanza)."""
        try:
            import win32print  # type: ignore

            hprinter = win32print.OpenPrinter(printer_name)
            try:
                jobs = win32print.EnumJobs(hprinter, 0, 100, 1)
            finally:
                try:
                    win32print.ClosePrinter(hprinter)
                except Exception:
                    pass
            return {int(j.get("JobId", 0)) for j in jobs} - {0}
        except Exception:
            return set()

    def _find_spooled_job_id(self, printer_name: str,
                             known: set[int]) -> int:
        """Job nuevo aparecido tras EndDoc (best-effort, 0 si no se sabe)."""
        try:
            after = self._snapshot_job_ids(printer_name)
            new = sorted(after - known)
            return new[-1] if new else 0
        except Exception:
            return 0

    def _log_device_caps(self, hdc, printer_name: str) -> None:
        try:
            w_mm = hdc.GetDeviceCaps(4)    # HORZSIZE
            h_mm = hdc.GetDeviceCaps(6)    # VERTSIZE
            dx = hdc.GetDeviceCaps(88)     # LOGPIXELSX
            dy = hdc.GetDeviceCaps(90)     # LOGPIXELSY
            log.info("PRINTER_CAPS %s papel=%sx%smm dpi=%sx%s",
                     printer_name, w_mm, h_mm, dx, dy)
            if not _is_a5_size(w_mm, h_mm):
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


# --- DEVMODE por-job vía ctypes (solo Windows) ---
# pywin32 312: `CDC.CreatePrinterDC(nombre)` NO acepta DEVMODE (1 solo
# argumento) y `win32print.DocumentProperties` exige objetos PyDEVMODE,
# no buffers. Por eso se llama directo a winspool/gdi32: se obtiene el
# DEVMODE del driver (con su parte privada), se parchea papel/orientación
# en memoria y se crea el DC con él. Sin SetPrinter: nada persiste.
_DM_OUT_BUFFER = 2
_DM_PAPERSIZE = 0x2
_DM_ORIENTATION = 0x1
_DM_PAPERLENGTH = 0x4
_DM_PAPERWIDTH = 0x8
_DMPAPER_A5 = 11
_DMPAPER_USER = 256
_DMORIENT_LANDSCAPE = 2
_OFF_FIELDS = 72
_OFF_ORIENTATION = 76
_OFF_PAPERSIZE = 78
_OFF_PAPERLENGTH = 80
_OFF_PAPERWIDTH = 82
# Tolerancia de verificación A5: varios drivers informan área imprimible
# (física menos márgenes) en vez de hoja física.
_A5_TOLERANCE_MM = 8

_gdi32 = None
_winspool = None


def _win32_dlls():
    global _gdi32, _winspool
    import ctypes

    if _gdi32 is None:
        _gdi32 = ctypes.WinDLL("gdi32")
        _gdi32.CreateDCW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                                     ctypes.c_wchar_p, ctypes.c_void_p]
        _gdi32.CreateDCW.restype = ctypes.c_void_p
        _gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
        _gdi32.DeleteDC.restype = ctypes.c_int
        _gdi32.GetDeviceCaps.argtypes = [ctypes.c_void_p, ctypes.c_int]
        _gdi32.GetDeviceCaps.restype = ctypes.c_int
    if _winspool is None:
        _winspool = ctypes.WinDLL("winspool.drv")
        _winspool.DocumentPropertiesW.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
        ]
        _winspool.DocumentPropertiesW.restype = ctypes.c_long
    return _gdi32, _winspool


def _devmode_buffer(printer_name: str, orient: int, paper: int,
                    plen: int, pwid: int):
    """DEVMODE del driver parcheado (buffer ctypes, solo en memoria).

    `orient`: 1 vertical, 2 apaisado. `paper`: id DMPAPER_* (256 = usuario).
    `plen`/`pwid`: largo/ancho en décimas de mm (0 = no tocar; requiere
    flags DM_PAPERLENGTH/DM_PAPERWIDTH).
    Lanza excepción si el driver no lo permite (el caller hace fallback).
    """
    import ctypes
    import struct

    import win32print  # type: ignore

    _, winspool = _win32_dlls()
    hprinter = win32print.OpenPrinter(printer_name)
    try:
        size = winspool.DocumentPropertiesW(None, int(hprinter),
                                            printer_name, None, None, 0)
        if size <= 0:
            raise RuntimeError(f"DocumentProperties size={size}")
        buf = ctypes.create_string_buffer(size)
        rc = winspool.DocumentPropertiesW(None, int(hprinter), printer_name,
                                          buf, None, _DM_OUT_BUFFER)
        if rc != 1:  # IDOK
            raise RuntimeError(f"DocumentProperties rc={rc}")
    finally:
        try:
            win32print.ClosePrinter(hprinter)
        except Exception:
            pass
    fields, = struct.unpack_from("<I", buf, _OFF_FIELDS)
    flags = fields | _DM_PAPERSIZE | _DM_ORIENTATION
    if plen or pwid:
        flags |= _DM_PAPERLENGTH | _DM_PAPERWIDTH
        struct.pack_into("<H", buf, _OFF_PAPERLENGTH, plen)
        struct.pack_into("<H", buf, _OFF_PAPERWIDTH, pwid)
    struct.pack_into("<I", buf, _OFF_FIELDS, flags)
    struct.pack_into("<H", buf, _OFF_ORIENTATION, orient)
    struct.pack_into("<H", buf, _OFF_PAPERSIZE, paper)
    return buf


def _is_a5_size(w_mm: int, h_mm: int) -> bool:
    """Acepta hoja física o área imprimible de un A5 apaisado."""
    return (abs(w_mm - WindowsGdiBackend.PAPER_WIDTH_MM) <= _A5_TOLERANCE_MM
            and abs(h_mm - WindowsGdiBackend.PAPER_HEIGHT_MM) <= _A5_TOLERANCE_MM)


def _page_dest_rect(hdc) -> tuple[int, int, int, int]:
    """Rect destino en píxeles de dispositivo para tamaño físico 1:1.

    La imagen raster representa la hoja física completa (210x148 mm).
    El origen (0,0) de GDI es el área imprimible: se compensa con los
    offsets físicos para que cada píxel caiga en su milímetro real.
    Retorna (x, y, w, h). Testeable sin Windows vía fake de GetDeviceCaps.
    """
    dpi_x = hdc.GetDeviceCaps(88)    # LOGPIXELSX
    dpi_y = hdc.GetDeviceCaps(90)    # LOGPIXELSY
    off_x = hdc.GetDeviceCaps(112)   # PHYSICALOFFSETX
    off_y = hdc.GetDeviceCaps(113)   # PHYSICALOFFSETY
    w = round(WindowsGdiBackend.PAPER_WIDTH_MM * dpi_x / 25.4)
    h = round(WindowsGdiBackend.PAPER_HEIGHT_MM * dpi_y / 25.4)
    return (-off_x, -off_y, w, h)


def _create_dc_with_devmode(printer_name: str, buf) -> int:
    gdi32, _ = _win32_dlls()
    hdc = gdi32.CreateDCW(None, printer_name, None, buf)
    if not hdc:
        raise RuntimeError("CreateDCW retornó NULL")
    return hdc


def _delete_dc(raw_hdc: int) -> None:
    gdi32, _ = _win32_dlls()
    gdi32.DeleteDC(raw_hdc)


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
