"""Logging con rotación. Formato apto para soporte (ver SPEC §20)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False


def setup_logging(level: str = "INFO", log_dir: str = "",
                  max_bytes: int = 5_242_880, backup_count: int = 7) -> None:
    global _configured
    if _configured:
        return
    _configured = True

    numeric = getattr(logging, level.upper(), logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s level=%(levelname)s agent=%(agent)s "
        "job=%(job_id)s estacion=%(estacion)s tipo=%(tipo)s "
        "doc=%(doc)s printer=%(printer)s %(message)s"
    )

    # Defaults para que ningún log falle por falta de campos extra.
    old_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.__dict__.setdefault("agent", "-")
        record.__dict__.setdefault("job_id", "-")
        record.__dict__.setdefault("estacion", "-")
        record.__dict__.setdefault("tipo", "-")
        record.__dict__.setdefault("doc", "-")
        record.__dict__.setdefault("printer", "-")
        return record

    logging.setLogRecordFactory(factory)

    root = logging.getLogger()
    root.setLevel(numeric)
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    root.addHandler(handler)

    if log_dir:
        try:
            path = Path(log_dir)
            path.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                path / "fasa-print-agent.log",
                maxBytes=max_bytes, backupCount=backup_count,
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:
            root.warning("No se pudo crear log dir %s; solo consola", log_dir)


def job_extra(agent: str = "-", job_id: object = "-",
              estacion: str = "-", tipo: str = "-",
              doc: str = "-", printer: str = "-") -> dict:
    return {"extra": {
        "agent": agent, "job_id": str(job_id), "estacion": estacion,
        "tipo": tipo, "doc": doc, "printer": printer,
    }}
