import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fasa_print_agent.print_history import (  # noqa: E402
    history_path_for,
    read_recent,
    record,
)


def test_history_path_defaults_and_off(tmp_path):
    p = history_path_for(str(tmp_path), "")
    assert p == tmp_path / "print-history.jsonl"
    assert history_path_for(str(tmp_path), "off") is None
    assert history_path_for(str(tmp_path), "OFF") is None
    assert history_path_for("", "rel.jsonl") == Path("rel.jsonl")
    assert history_path_for("", "") == Path.cwd() / "print-history.jsonl"


def test_record_and_read_recent_roundtrip(tmp_path):
    p = tmp_path / "h.jsonl"
    assert read_recent(p) == []
    record(p, {"doc": "a.pdf", "result": "OK", "windows_job_id": 3})
    record(p, {"doc": "b.pdf", "result": "ERROR", "code": "X"})
    rows = read_recent(p)
    assert [r["doc"] for r in rows] == ["b.pdf", "a.pdf"]
    assert rows[0]["ts"] and rows[1]["windows_job_id"] == 3
    assert len(read_recent(p, limit=1)) == 1


def test_record_never_raises_and_skips_bad_lines(tmp_path):
    record(None, {"doc": "x"})  # desactivado: no-op
    p = tmp_path / "h.jsonl"
    p.write_text('{"doc": "ok"}\nno-json\n', encoding="utf-8")
    assert [r["doc"] for r in read_recent(p)] == ["ok"]
    record(tmp_path / "noexiste" / "h.jsonl", {"a": 1})  # crea dirs
    assert (tmp_path / "noexiste" / "h.jsonl").is_file()
