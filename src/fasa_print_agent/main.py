"""Entry point: fasa-print-agent [--health-check|--list-printers|--test-printer X|--run-once]."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import load_config
from .logging_config import setup_logging


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fasa-print-agent",
                                description="FASA Print Agent (SERVERFASA)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--env-file", default=None, help="Archivo .env alternativo")
    p.add_argument("--health-check", action="store_true")
    p.add_argument("--list-printers", action="store_true")
    p.add_argument("--test-printer", nargs="?", const="", default=None,
                   help='Impresora a probar, ej. --test-printer "Remito Cuenta Corriente"')
    p.add_argument("--run-once", action="store_true",
                   help="Procesa un trabajo y sale")
    p.add_argument("--panel", action="store_true",
                   help="Abre el panel de escritorio (trabajos enviados)")
    from .remito_cli import add_remito_args
    add_remito_args(p)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.env_file)
    setup_logging(cfg.log_level, cfg.log_dir,
                  cfg.log_max_bytes, cfg.log_backup_count)

    from . import diagnostics
    from .print_history import history_path_for
    from .remito_cli import dispatch_remito, has_remito_args
    hpath = history_path_for(cfg.log_dir, cfg.history_file)
    if args.panel:
        from .desktop import run_panel
        return run_panel(hpath, cfg.default_test_printer)
    if has_remito_args(args):
        rc = dispatch_remito(args, hpath)
        return rc if rc is not None else 0
    if args.health_check:
        return diagnostics.health_check(cfg)
    if args.list_printers:
        return diagnostics.list_printers()
    if args.test_printer is not None:
        return diagnostics.test_printer(cfg, args.test_printer)
    if args.run_once:
        return diagnostics.run_once(cfg)

    from .worker import run_forever
    try:
        run_forever(cfg)
    except KeyboardInterrupt:
        print("\nDetenido.", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
