"""Configuración del agente (sin credenciales hardcodeadas).

Lee variables de entorno y/o archivo .env. En producción el archivo es:
    C:\\ProgramData\\FASA Print Agent\\agent.env
En desarrollo se usa `.env` en la raíz del repo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROD_ENV_PATH = Path(r"C:\ProgramData\FASA Print Agent\agent.env")


def _load_dotenv(path: Path) -> None:
    """Carga mínima de archivo .env (KEY=VALUE, sin dependencias externas)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


def _get_list(name: str) -> list[str]:
    raw = _get(name, "")
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


@dataclass
class AgentConfig:
    agent_name: str = "SERVERFASA"
    poll_seconds: int = 2

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "fasa_erp"
    db_user: str = ""
    db_password: str = ""

    sumatra_pdf_path: str = ""
    print_timeout_seconds: int = 60
    default_test_printer: str = ""

    allowed_tipos_impresion: list[str] = field(default_factory=list)
    allowed_documento_tipos: list[str] = field(default_factory=list)
    max_copias: int = 5

    log_level: str = "INFO"
    log_dir: str = r"C:\ProgramData\FASA Print Agent\logs"
    log_max_bytes: int = 5_242_880
    log_backup_count: int = 7


def load_config(env_file: str | Path | None = None) -> AgentConfig:
    """Carga configuración. `env_file` explícito tiene prioridad para tests."""
    if env_file is not None:
        _load_dotenv(Path(env_file))
    else:
        # .env local (desarrollo) primero, luego ruta de producción.
        _load_dotenv(Path.cwd() / ".env")
        _load_dotenv(PROD_ENV_PATH)

    return AgentConfig(
        agent_name=_get("AGENT_NAME", "SERVERFASA") or "SERVERFASA",
        poll_seconds=max(1, _get_int("POLL_SECONDS", 2)),
        db_host=_get("DB_HOST", "127.0.0.1"),
        db_port=_get_int("DB_PORT", 3306),
        db_name=_get("DB_NAME", "fasa_erp"),
        db_user=_get("DB_USER", ""),
        db_password=_get("DB_PASSWORD", ""),
        sumatra_pdf_path=_get("SUMATRA_PDF_PATH", ""),
        print_timeout_seconds=max(5, _get_int("PRINT_TIMEOUT_SECONDS", 60)),
        default_test_printer=_get("DEFAULT_TEST_PRINTER", ""),
        allowed_tipos_impresion=_get_list("ALLOWED_TIPOS_IMPRESION")
        or ["REMITO_CTACTE"],
        allowed_documento_tipos=_get_list("ALLOWED_DOCUMENTO_TIPOS") or ["REMITO"],
        max_copias=max(1, _get_int("MAX_COPIAS", 5)),
        log_level=_get("LOG_LEVEL", "INFO").upper() or "INFO",
        log_dir=_get("LOG_DIR", r"C:\ProgramData\FASA Print Agent\logs"),
        log_max_bytes=_get_int("LOG_MAX_BYTES", 5_242_880),
        log_backup_count=_get_int("LOG_BACKUP_COUNT", 7),
    )
