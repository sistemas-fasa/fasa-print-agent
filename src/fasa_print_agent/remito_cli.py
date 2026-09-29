"""Comandos spike REMITO_CTACTE (generar PDF A5 / imprimirlo).

Tres etapas bien diferenciadas (SPEC §10):

1. GENERACIÓN (`--save-remito-pdf`, `--print-remito-test --no-print`):
   produce el PDF de 210x148 mm. Funciona en cualquier plataforma.
2. ENVÍO AL SPOOLER (`--print-remito-pdf`, `--print-remito-test --printer`):
   solo Windows/SERVERFASA, vía backend GDI. Informa el job id aceptado.
3. RESULTADO: "IMPRESO" = aceptado por el spooler, no papel confirmado.

Calibración: `--offset-x/--offset-y` (mm) o `--layout-json` (ver
`--write-remito-layout`). Nunca hay que tocar código para calibrar.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from .remito_data import RemitoCtaCte, sample_fixture
from .remito_layout import RemitoLayout
from .remito_pdf import build_remito_pdf

log = logging.getLogger(__name__)


def add_remito_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--save-remito-pdf", default=None, metavar="PDF",
                   help="Genera el remito A5 y lo guarda (sin imprimir)")
    p.add_argument("--print-remito-pdf", default=None, metavar="PDF",
                   help="Imprime un PDF existente en la impresora indicada")
    p.add_argument("--print-remito-test", action="store_true",
                   help="Genera el remito de prueba y lo imprime "
                        "(o solo lo genera con --no-print)")
    p.add_argument("--printer", default="", help='Impresora destino, ej. "L395 Series(Network)"')
    p.add_argument("--remito-json", default=None, metavar="JSON",
                   help="Datos del remito (JSON). Si se omite: fixture de prueba")
    p.add_argument("--layout-json", default=None, metavar="JSON",
                   help="Layout de calibración (JSON). Si se omite: defaults")
    p.add_argument("--offset-x", type=float, default=None, metavar="MM",
                   help="Calibración global X en mm (sobreescribe layout)")
    p.add_argument("--offset-y", type=float, default=None, metavar="MM",
                   help="Calibración global Y en mm (sobreescribe layout)")
    p.add_argument("--out", default=None, metavar="PDF",
                   help="Ruta del PDF a generar (defecto: ./remito-test.pdf)")
    p.add_argument("--copies", type=int, default=1)
    p.add_argument("--dpi", type=int, default=300,
                   help="DPI de rasterizado GDI (72-600, defecto 300)")
    p.add_argument("--dc-mode", default="auto",
                   choices=["auto", "a5", "user-landscape", "user-portrait"],
                   help="Estrategia papel/orientacion del DC "
                        "(user-portrait: Epson sin A5 que rota apaisados)")
    p.add_argument("--no-print", action="store_true",
                   help="Con --print-remito-test: solo genera, no imprime")
    p.add_argument("--write-remito-fixture", default=None, metavar="JSON",
                   help="Escribe el fixture de datos de prueba y sale")
    p.add_argument("--write-remito-layout", default=None, metavar="JSON",
                   help="Escribe el layout default editable y sale")


def has_remito_args(args: argparse.Namespace) -> bool:
    return bool(args.save_remito_pdf or args.print_remito_pdf
                or args.print_remito_test or args.write_remito_fixture
                or args.write_remito_layout)


def load_remito_data(path: str | None) -> RemitoCtaCte:
    if not path:
        return sample_fixture()
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise SystemExit(f"ERROR: no se pudo leer --remito-json: {e}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"ERROR: JSON inválido en {path}: {e}")
    if not isinstance(raw, dict):
        raise SystemExit(f"ERROR: {path} debe ser un objeto JSON")
    return RemitoCtaCte.from_dict(raw)


def load_layout(args: argparse.Namespace) -> RemitoLayout:
    if args.layout_json:
        try:
            raw = json.loads(Path(args.layout_json).read_text(encoding="utf-8"))
        except OSError as e:
            raise SystemExit(f"ERROR: no se pudo leer --layout-json: {e}")
        except json.JSONDecodeError as e:
            raise SystemExit(f"ERROR: JSON inválido en {args.layout_json}: {e}")
        layout = RemitoLayout.from_dict(raw if isinstance(raw, dict) else {})
    else:
        layout = RemitoLayout()
    dx = args.offset_x if args.offset_x is not None else layout.offset_x_mm
    dy = args.offset_y if args.offset_y is not None else layout.offset_y_mm
    return layout.with_offsets(float(dx), float(dy))


def dispatch_remito(args: argparse.Namespace, hpath=None) -> int | None:
    """Retorna código de salida si se consumió un comando remito, None si no."""
    if args.write_remito_fixture:
        out = Path(args.write_remito_fixture)
        out.write_text(json.dumps(sample_fixture().to_dict(), indent=2,
                                  ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"FIXTURE_OK: {out}")
        return 0
    if args.write_remito_layout:
        out = Path(args.write_remito_layout)
        out.write_text(json.dumps(RemitoLayout().to_dict(), indent=2,
                                  ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"LAYOUT_OK: {out} (editar posiciones y reusar con --layout-json)")
        return 0
    if args.save_remito_pdf:
        return cmd_save_remito(args)
    if args.print_remito_pdf:
        return cmd_print_pdf(args, hpath)
    if args.print_remito_test:
        return cmd_print_test(args, hpath)
    return None


def cmd_save_remito(args: argparse.Namespace) -> int:
    t0 = time.monotonic()
    data = load_remito_data(args.remito_json)
    layout = load_layout(args)
    try:
        out = build_remito_pdf(data, args.save_remito_pdf, layout)
    except (ValueError, OSError) as e:
        print(f"GENERACION_ERROR: {e}", file=sys.stderr)
        return 1
    dt = time.monotonic() - t0
    size = out.stat().st_size
    print(f"GENERADO_OK: {out} ({size} bytes, {dt:.1f}s) "
          f"remito={data.numero} offset=({layout.offset_x_mm},{layout.offset_y_mm})mm")
    print("Inspeccionar el PDF antes de imprimir. Para calibrar: "
          "--offset-x/--offset-y o --layout-json.")
    return 0


def cmd_print_pdf(args: argparse.Namespace, hpath=None) -> int:
    from . import windows_print
    from .print_backend import resolve_dc_mode
    from .print_history import record

    printer = args.printer
    if not printer:
        print('ERROR: indicar impresora con --printer "Nombre" '
              '(ver --list-printers)', file=sys.stderr)
        return 2
    t0 = time.monotonic()
    try:
        res = windows_print.spool_pdf_with_result(
            args.print_remito_pdf, printer, copies=args.copies, dpi=args.dpi,
            dc_mode=args.dc_mode)
    except windows_print.PrintError as e:
        print(f"SPOOL_ERROR code={e.code}: {e}", file=sys.stderr)
        log.error("RESULT=ERROR code=%s printer=%s pdf=%s err=%s",
                  e.code, printer, args.print_remito_pdf, e)
        record(hpath, {"source": "cli", "doc": Path(args.print_remito_pdf).name,
                       "pdf": args.print_remito_pdf, "printer": printer,
                       "copies": args.copies, "result": "ERROR",
                       "code": e.code, "error": str(e)[:500]})
        return 1
    dt = time.monotonic() - t0
    print(f"SPOOL_OK: {args.print_remito_pdf} -> {res.printer_name!r} "
          f"copias={res.copies} paginas={res.pages_spooled} "
          f"windows_job_id={res.windows_job_id} ({dt:.1f}s)")
    print("ENVIADO_SPOOLER: Windows aceptó el trabajo. Verificar papel físico.")
    record(hpath, {"source": "cli", "doc": Path(args.print_remito_pdf).name,
                   "pdf": args.print_remito_pdf, "printer": res.printer_name,
                   "copies": res.copies, "dpi": args.dpi,
                   "dc_mode": resolve_dc_mode(printer, args.dc_mode),
                   "result": "OK", "windows_job_id": res.windows_job_id})
    return 0


def cmd_print_test(args: argparse.Namespace, hpath=None) -> int:
    data = load_remito_data(args.remito_json)
    layout = load_layout(args)
    out_path = args.out or "remito-test.pdf"
    try:
        out = build_remito_pdf(data, out_path, layout)
    except (ValueError, OSError) as e:
        print(f"GENERACION_ERROR: {e}", file=sys.stderr)
        return 1
    print(f"GENERADO_OK: {out} remito={data.numero} "
          f"offset=({layout.offset_x_mm},{layout.offset_y_mm})mm")
    if args.no_print or not args.printer:
        if not args.printer:
            print("Sin --printer: solo se generó (agregar --printer para imprimir "
                  "o --no-print para silenciar este aviso).")
        return 0
    args.print_remito_pdf = str(out)
    return cmd_print_pdf(args, hpath)
