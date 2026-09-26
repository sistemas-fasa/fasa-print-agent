"""Diagnóstico CLI (SPEC §21): health-check, list-printers, test-printer, run-once."""
from __future__ import annotations

import sys

from . import windows_print
from .config import AgentConfig


def health_check(cfg: AgentConfig) -> int:
    from . import database
    ok = True
    print(f"[1/5] Config: agent={cfg.agent_name} poll={cfg.poll_seconds}s "
          f"db={cfg.db_user}@{cfg.db_host}:{cfg.db_port}/{cfg.db_name}")
    if not cfg.db_user or not cfg.db_password:
        print("      WARN: DB_USER/DB_PASSWORD vacíos")
    try:
        database.check_connection(cfg)
        print("[2/5] MySQL: OK")
    except Exception as e:
        print(f"[2/5] MySQL: FAIL {e}")
        return 2
    try:
        missing = database.check_tables(cfg)
        if missing:
            print(f"[3/5] Tablas: FALTAN {missing}")
            ok = False
        else:
            print("[3/5] Tablas print_jobs/impresora_maquina/impresoras: OK")
    except Exception as e:
        print(f"[3/5] Tablas: FAIL {e}")
        return 2
    printers = windows_print.list_printers()
    print(f"[4/5] Spooler Windows: {len(printers)} impresora(s) visible(s)")
    for p in printers[:20]:
        print(f"      - {p}")
    if not printers:
        print("      WARN: ninguna impresora visible desde esta cuenta "
              "(¿cuenta del servicio? ver docs)")
    print(f"[5/5] Identidad agente: {cfg.agent_name}")
    print("HEALTH " + ("OK" if ok else "DEGRADED"))
    return 0 if ok else 3


def list_printers() -> int:
    printers = windows_print.list_printers()
    if not printers:
        print("(sin impresoras visibles — ¿pywin32 instalado? ¿cuenta del servicio?)")
        return 1
    for p in printers:
        print(p)
    return 0


def test_printer(cfg: AgentConfig, printer: str) -> int:
    name = printer or cfg.default_test_printer
    if not name:
        print("Indicar impresora: --test-printer \"Nombre\"", file=sys.stderr)
        return 2
    printers = windows_print.list_printers()
    if printers and name not in printers:
        print(f"PRINTER_NOT_AVAILABLE: {name!r} no visible. Visibles:")
        for p in printers:
            print(f"  - {p}")
        return 1
    # Página de prueba: imprime un PDF mínimo si no hay backend real.
    print(f"OK: impresora {name!r} visible. "
          f"Para prueba física configurar un PDF y usar --run-once.")
    return 0


def run_once(cfg: AgentConfig) -> int:
    from .database import connect
    from .worker import process_one
    conn = connect(cfg)
    try:
        worked = process_one(conn, cfg)
    finally:
        conn.close()
    print("JOB procesado" if worked else "Sin trabajos PENDIENTE")
    return 0
