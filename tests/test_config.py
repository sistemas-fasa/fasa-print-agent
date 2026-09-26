import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fasa_print_agent.config import load_config  # noqa: E402


def test_load_config_defaults(tmp_path, monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith(("AGENT_", "DB_", "LOG_", "PRINT_", "SUMATRA",
                         "ALLOWED_", "MAX_", "DEFAULT_")):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.agent_name == "SERVERFASA"
    assert cfg.poll_seconds == 2
    assert cfg.allowed_tipos_impresion == ["REMITO_CTACTE"]


def test_load_config_env_file(tmp_path):
    env = tmp_path / "agent.env"
    env.write_text("AGENT_NAME=TEST1\nPOLL_SECONDS=5\nALLOWED_TIPOS_IMPRESION=A,B\n",
                   encoding="utf-8")
    cfg = load_config(env)
    assert cfg.agent_name == "TEST1"
    assert cfg.poll_seconds == 5
    assert cfg.allowed_tipos_impresion == ["A", "B"]
