"""Worker de polling (SPEC §19): reclamar → resolver → imprimir → actualizar.

Origen del documento (prioridad):
1. `archivo_path`: PDF listo (legado / contingencia).
2. `payload_json` + `documento_tipo=REMITO`: el agente genera el PDF A5
   (ver docs/CONTRATO_ERP.md y fixtures/remito_ctacte_ejemplo.json).
"""
from __future__ import annotations

import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from . import windows_print
from .config import AgentConfig
from .logging_config import job_extra
from .print_history import history_path_for, record
from .printer_resolver import (
    PrinterMappingNotFound,
    PrinterNotAvailable,
    resolve_printer,
)
from .queue import (
    claim_next_job,
    mark_error,
    mark_printed,
    mark_spooled,
)

log = logging.getLogger(__name__)


def _validate_job(job: dict[str, Any], cfg: AgentConfig) -> str | None:
    """Retorna código de error si el job es inválido, None si OK."""
    if job.get("tipo_impresion") not in cfg.allowed_tipos_impresion:
        return "TIPO_NO_PERMITIDO"
    if job.get("documento_tipo") not in cfg.allowed_documento_tipos:
        return "DOCUMENTO_NO_PERMITIDO"
    try:
        copias = int(job.get("copias", 1))
    except (TypeError, ValueError):
        return "COPIAS_INVALIDAS"
    if copias < 1 or copias > cfg.max_copias:
        return "COPIAS_INVALIDAS"
    if not job.get("archivo_path") and not job.get("payload_json"):
        return "DOCUMENTO_FALTANTE"
    return None


def _resolve_pdf_path(job: dict[str, Any]) -> tuple[str, Any | None]:
    """Retorna (ruta_pdf, tmpdir). `tmpdir` no-None debe limpiarse tras
    imprimir. Lanza `_PdfError` (con `.code`) si no hay documento útil."""
    if job.get("archivo_path"):
        return str(job["archivo_path"]), None
    if str(job.get("documento_tipo", "")) != "REMITO":
        raise _PdfError("GENERADOR_NO_SOPORTADO",
                        f"Sin archivo y sin generador para "
                        f"documento_tipo={job.get('documento_tipo')!r}")
    raw = job.get("payload_json")
    try:
        data_dict = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise _PdfError("PAYLOAD_INVALIDO",
                        f"payload_json no es JSON válido: {e}") from e
    try:
        from .remito_data import RemitoCtaCte
        from .remito_pdf import build_remito_pdf

        data = RemitoCtaCte.from_dict(data_dict)
    except Exception as e:
        raise _PdfError("PAYLOAD_INVALIDO",
                        f"payload no mapea a REMITO_CTACTE: {e}") from e
    tmp = tempfile.TemporaryDirectory(prefix="fasa-job-")
    try:
        out = build_remito_pdf(
            data, Path(tmp.name) / f"remito-{job.get('id')}-"
            f"{job.get('documento_id')}.pdf")
    except Exception as e:
        tmp.cleanup()
        raise _PdfError("PDF_GENERACION_ERROR", str(e)[:500]) from e
    return str(out), tmp


class _PdfError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def process_one(conn, cfg: AgentConfig) -> bool:
    """Procesa un trabajo. Retorna True si tomó uno (aunque falle)."""
    job = claim_next_job(conn, cfg.agent_name)
    if job is None:
        return False

    jid = job["id"]
    estacion = str(job.get("estacion", ""))
    tipo = str(job.get("tipo_impresion", ""))
    doc = f"{job.get('documento_tipo')}/{job.get('documento_id')}"
    ex = job_extra(cfg.agent_name, jid, estacion, tipo, doc, "?")
    t0 = time.monotonic()
    hpath = history_path_for(cfg.log_dir, cfg.history_file)
    base = {"source": "worker", "doc": doc, "estacion": estacion,
            "tipo": tipo}

    invalid = _validate_job(job, cfg)
    if invalid:
        mark_error(conn, jid, invalid, f"Validación: {invalid}", retry=False)
        log.error("Job rechazado validación %s", invalid, extra=ex["extra"])
        record(hpath, {**base, "result": "ERROR", "code": invalid})
        return True

    try:
        resolved = resolve_printer(conn, estacion, tipo)
    except PrinterMappingNotFound as e:
        mark_error(conn, jid, "PRINTER_MAPPING_NOT_FOUND", str(e), retry=False)
        log.error("Sin mapping: %s", e, extra=ex["extra"])
        record(hpath, {**base, "result": "ERROR",
                       "code": "PRINTER_MAPPING_NOT_FOUND"})
        return True
    except Exception as e:  # DB u otro
        mark_error(conn, jid, "RESOLVER_ERROR",
                   f"{type(e).__name__}: {e}", retry=True)
        log.exception("Error resolviendo impresora", extra=ex["extra"])
        return True

    ex = job_extra(cfg.agent_name, jid, estacion, tipo, doc,
                   resolved.windows_name)

    if not windows_print.printer_exists(resolved.windows_name):
        # En dev sin win32 las listas están vacías: solo fallar si hay
        # impresoras visibles (evita falsos positivos en tests/CI).
        visible = windows_print.list_printers()
        if visible:
            mark_error(conn, jid, "PRINTER_NOT_AVAILABLE",
                       f"Impresora no visible: {resolved.windows_name}. "
                       f"Visibles: {', '.join(visible[:10])}", retry=True)
            log.error("Impresora no disponible", extra=ex["extra"])
            return True
        # Sin backend (Linux/CI): marcar como spool simulado solo si el
        # archivo existe, para permitir pruebas de integración sin Windows.
        log.warning("Sin backend Windows; spool simulado", extra=ex["extra"])

    try:
        pdf_path, tmpdir = _resolve_pdf_path(job)
    except _PdfError as e:
        mark_error(conn, jid, e.code, str(e)[:2000], retry=False)
        log.error("Documento no generable: %s", e, extra=ex["extra"])
        record(hpath, {**base, "result": "ERROR", "code": e.code})
        return True

    try:
        mark_spooled(conn, jid, resolved.windows_name)
        windows_print.print_pdf(
            pdf_path, resolved.windows_name,
            copies=int(job.get("copias", 1)),
            sumatra_path=cfg.sumatra_pdf_path,
            timeout=cfg.print_timeout_seconds,
        )
    except PrinterNotAvailable as e:
        mark_error(conn, jid, "PRINTER_NOT_AVAILABLE", str(e), retry=True)
        log.error("Printer no disponible: %s", e, extra=ex["extra"])
        return True
    except Exception as e:  # windows_print.PrintError u otro
        code = getattr(e, "code", type(e).__name__)
        # Reintentable salvo errores definitivos de archivo/validación.
        retry = code not in ("FILE_NOT_FOUND", "NO_PRINT_BACKEND")
        mark_error(conn, jid, code, str(e)[:2000], retry=retry)
        log.error("Error imprimiendo: %s", e, extra=ex["extra"])
        record(hpath, {**base, "printer": resolved.windows_name,
                       "result": "ERROR", "code": code})
        return True
    finally:
        try:
            if tmpdir is not None:
                tmpdir.cleanup()
        except Exception:
            pass

    mark_printed(conn, jid)
    dt = time.monotonic() - t0
    log.info("RESULT=OK duracion=%.1fs", dt, extra=ex["extra"])
    record(hpath, {**base, "printer": resolved.windows_name,
                   "copies": int(job.get("copias", 1)), "result": "OK"})
    return True


def run_forever(cfg: AgentConfig, connect_fn=None) -> None:
    """Loop de polling hasta KeyboardInterrupt."""
    from .database import connect as _connect
    connect_fn = connect_fn or _connect
    log.info("Agente %s polling cada %ss", cfg.agent_name, cfg.poll_seconds,
             extra=job_extra(cfg.agent_name)["extra"])
    while True:
        try:
            conn = connect_fn(cfg)
            try:
                worked = process_one(conn, cfg)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            if not worked:
                time.sleep(cfg.poll_seconds)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log.exception("Error ciclo polling: %s", e,
                          extra=job_extra(cfg.agent_name)["extra"])
            time.sleep(cfg.poll_seconds)
