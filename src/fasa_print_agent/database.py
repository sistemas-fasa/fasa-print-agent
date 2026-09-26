"""Acceso MySQL (pymysql, stdlib-friendly, sin ORM)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pymysql
import pymysql.cursors

from .config import AgentConfig


def connect(cfg: AgentConfig):
    return pymysql.connect(
        host=cfg.db_host,
        port=cfg.db_port,
        database=cfg.db_name,
        user=cfg.db_user,
        password=cfg.db_password,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )


@contextmanager
def session(cfg: AgentConfig) -> Iterator[pymysql.Connection]:
    conn = connect(cfg)
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def check_connection(cfg: AgentConfig) -> None:
    """Lanza excepción si MySQL no es accesible."""
    conn = connect(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
            if not row or row.get("ok") != 1:
                raise RuntimeError("MySQL no respondió SELECT 1")
    finally:
        conn.close()


def check_tables(cfg: AgentConfig) -> list[str]:
    """Devuelve lista de tablas requeridas faltantes."""
    required = ["print_jobs", "impresora_maquina", "impresoras"]
    conn = connect(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE()"
            )
            present = {r["TABLE_NAME"].lower() for r in cur.fetchall()}
        return [t for t in required if t.lower() not in present]
    finally:
        conn.close()
