"""Historial de trabajos enviados (para el panel de escritorio).

Persistencia mínima: archivo JSONL append-only (una línea por trabajo).
Best-effort: nunca lanza (no debe romper una impresión por no poder
escribir el historial). Sin dependencias y sin Windows.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def history_path_for(log_dir: str = "", history_file: str = "") -> Path | None:
    """Ruta del historial. `history_file="off"` lo desactiva."""
    if (history_file or "").strip().lower() == "off":
        return None
    if (history_file or "").strip():
        return Path(history_file)
    base = Path(log_dir) if (log_dir or "").strip() else Path.cwd()
    return base / "print-history.jsonl"


def record(path: Path | None, entry: dict) -> None:
    """Agrega una entrada al historial. Nunca lanza."""
    if path is None:
        return
    try:
        data = {"ts": datetime.now().isoformat(timespec="seconds")}
        data.update(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_recent(path: Path | None, limit: int = 100) -> list[dict]:
    """Últimas `limit` entradas (más recientes primero). Nunca lanza."""
    if path is None:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-max(1, limit):]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    out.reverse()
    return out
