"""Tests del backend de impresión: sin Windows, sin impresoras, sin diálogos."""
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fasa_print_agent.print_backend import (  # noqa: E402
    PrintBackend,
    PrintError,
    SimulatedBackend,
    SpoolResult,
    _is_a5_size,
    _page_dest_rect,
    _save_pixmap_as_bmp,
    get_backend,
)


class FakePixmap:
    """Mínimo compatible con lo que usa _save_pixmap_as_bmp."""

    def __init__(self, w, h):
        self.width, self.height, self.n, self.alpha = w, h, 3, False
        # Patrón determinista: R=x%256, G=y%256, B=(x+y)%256.
        buf = bytearray()
        for y in range(h):
            for x in range(w):
                buf += bytes((x % 256, y % 256, (x + y) % 256))
        self.samples = bytes(buf)


def test_simulated_backend_lists_nothing_and_never_fakes_success(tmp_path):
    b = SimulatedBackend()
    assert b.list_printers() == []
    assert not b.printer_exists("Cualquiera")
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(PrintError) as e:
        b.spool_pdf(str(pdf), "X")
    assert e.value.code == "NO_PRINT_BACKEND"
    with pytest.raises(PrintError) as e2:
        b.spool_pdf(str(tmp_path / "noexiste.pdf"), "X")
    assert e2.value.code == "FILE_NOT_FOUND"


def test_bmp_writer_valid_24bit_bottom_up(tmp_path):
    p = tmp_path / "p.bmp"
    _save_pixmap_as_bmp(FakePixmap(5, 3), str(p))
    raw = p.read_bytes()
    magic, size, _, _, off = struct.unpack("<2sIHHI", raw[:14])
    assert magic == b"BM" and size == len(raw) and off == 54
    (dib_size, w, h, planes, bpp) = struct.unpack("<IiiHH", raw[14:30])
    assert dib_size == 40
    assert (w, h, planes, bpp) == (5, 3, 1, 24)
    stride = (5 * 3 + 3) // 4 * 4  # 16 (1 byte pad)
    assert len(raw) == 54 + stride * 3
    # Primera fila del archivo = última fila lógica (y=2), píxel (0,2) en BGR.
    first = raw[54:57]
    assert first == bytes((2, 2, 0))
    # Padding cero.
    assert raw[54 + 15:54 + 16] == b"\x00"


def test_bmp_writer_rejects_alpha():
    class Alpha:
        width, height, n, alpha = 2, 2, 4, True
        samples = b"\x00" * 16

    try:
        _save_pixmap_as_bmp(Alpha(), "x.bmp")
    except ValueError:
        pass
    else:
        raise AssertionError("debió rechazar pixmap con alpha")


class RecordingBackend(PrintBackend):
    """Fake que respeta la interfaz: útil como contrato para tests/integración."""

    def __init__(self):
        self.calls = []

    def list_printers(self):
        return ["PRN-TEST"]

    def spool_pdf(self, pdf_path, printer_name, copies=1, dpi=300):
        self.calls.append((pdf_path, printer_name, copies, dpi))
        if printer_name != "PRN-TEST":
            raise PrintError("PRINTER_NOT_AVAILABLE", printer_name)
        return SpoolResult(printer_name, copies, 1, windows_job_id=42)


def test_backend_interface_contract():
    b = RecordingBackend()
    assert b.printer_exists("prn-test")  # case-insensitive
    res = b.spool_pdf("r.pdf", "PRN-TEST", copies=2)
    assert (res.copies, res.windows_job_id) == (2, 42)
    with pytest.raises(PrintError):
        b.spool_pdf("r.pdf", "OTRA")


def test_get_backend_returns_simulated_off_windows(monkeypatch):
    import fasa_print_agent.print_backend as pb

    monkeypatch.setattr(pb.os, "name", "posix")
    assert isinstance(get_backend(), SimulatedBackend)


def test_is_a5_size_accepts_physical_and_printable_area():
    assert _is_a5_size(210, 148)          # hoja física exacta
    assert _is_a5_size(204, 142)          # Epson L395: área imprimible A5
    assert _is_a5_size(202, 140)          # RICOH: área imprimible A5
    assert not _is_a5_size(291, 204)      # A4 apaisado: rechazar
    assert not _is_a5_size(210, 297)      # A4 vertical: rechazar


def test_page_dest_rect_is_1_to_1_mm_with_margin_offsets():
    class FakeDC:
        def __init__(self, caps):
            self.caps = caps

        def GetDeviceCaps(self, n):
            return self.caps[n]

    # L395: 360 dpi, márgenes no imprimibles 42/43 px.
    dc = FakeDC({88: 360, 90: 360, 112: 42, 113: 43})
    x, y, w, h = _page_dest_rect(dc)
    assert (x, y) == (-42, -43)
    assert w == round(210 * 360 / 25.4) == 2976
    assert h == round(148 * 360 / 25.4) == 2098
    # Sin márgenes (borderless): origen en cero.
    dc2 = FakeDC({88: 600, 90: 600, 112: 0, 113: 0})
    assert _page_dest_rect(dc2) == (0, 0, round(210 * 600 / 25.4),
                                    round(148 * 600 / 25.4))
