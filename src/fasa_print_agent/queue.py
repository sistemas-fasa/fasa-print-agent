"""Cola persistente `print_jobs` con reclamo atómico (SPEC §9–11).

Nunca SELECT→imprimir→UPDATE sin exclusión. El reclamo se hace con un
único UPDATE atómico + SELECT posterior, válido en cualquier versión de
MySQL (no depende de SKIP LOCKED).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

ESTADO_PENDIENTE = "PENDIENTE"
ESTADO_TOMADO = "TOMADO"
ESTADO_SPOOLER = "ENVIADO_SPOOLER"
ESTADO_IMPRESO = "IMPRESO"
ESTADO_ERROR = "ERROR"
ESTADO_CANCELADO = "CANCELADO"


def claim_next_job(conn, agent_name: str) -> dict[str, Any] | None:
    """Reclama el próximo PENDIENTE de forma atómica. Retorna el job o None."""
    with conn.cursor() as cur:
        # 1) candidato más antiguo (solo lectura).
        cur.execute(
            """
            SELECT id FROM print_jobs
             WHERE estado = %s AND intentos < max_intentos
             ORDER BY created_at ASC LIMIT 1
            """,
            (ESTADO_PENDIENTE,),
        )
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            return None
        job_id = row["id"]
        # 2) UPDATE condicional atómico: solo gana quien transicione
        #    PENDIENTE→TOMADO (affected_rows=1). Los demás ven 0 filas.
        cur.execute(
            """
            UPDATE print_jobs
               SET estado = %s,
                   claimed_at = NOW(),
                   agent_name = %s,
                   intentos = intentos + 1
             WHERE id = %s AND estado = %s
            """,
            (ESTADO_TOMADO, agent_name, job_id, ESTADO_PENDIENTE),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return None
        cur.execute("SELECT * FROM print_jobs WHERE id = %s", (job_id,))
        job = cur.fetchone()
        if job is None:
            conn.rollback()
            return None
        conn.commit()
        return job


def mark_spooled(conn, job_id: int, impresora: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE print_jobs SET estado=%s, spooled_at=NOW(), "
            "impresora_resuelta=%s WHERE id=%s",
            (ESTADO_SPOOLER, impresora, job_id),
        )
    conn.commit()


def mark_printed(conn, job_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE print_jobs SET estado=%s, printed_at=NOW() WHERE id=%s",
            (ESTADO_IMPRESO, job_id),
        )
    conn.commit()


def mark_error(conn, job_id: int, code: str, message: str,
               retry: bool = False) -> None:
    """ERROR terminal, o reencola a PENDIENTE si retry=True y quedan intentos."""
    with conn.cursor() as cur:
        if retry:
            cur.execute(
                """
                UPDATE print_jobs
                   SET estado = CASE WHEN intentos < max_intentos
                                     THEN %s ELSE %s END,
                       failed_at = CASE WHEN intentos < max_intentos
                                        THEN NULL ELSE NOW() END,
                       error_code = %s, error_message = %s
                 WHERE id = %s
                """,
                (ESTADO_PENDIENTE, ESTADO_ERROR, code, message[:2000], job_id),
            )
        else:
            cur.execute(
                "UPDATE print_jobs SET estado=%s, failed_at=NOW(), "
                "error_code=%s, error_message=%s WHERE id=%s",
                (ESTADO_ERROR, code, message[:2000], job_id),
            )
    conn.commit()


def get_job(conn, job_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM print_jobs WHERE id=%s", (job_id,))
        return cur.fetchone()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
