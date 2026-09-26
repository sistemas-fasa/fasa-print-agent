"""Fakes mínimos de conexión MySQL para tests (sin servidor real)."""
from __future__ import annotations


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self._one = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        handler = self.conn.handlers.pop(0) if self.conn.handlers else None
        if handler is None:
            self.rowcount = 0
            self._one = None
            return
        kind, value = handler(sql, params)
        if kind == "one":
            self._one = value
            self.rowcount = 1 if value else 0
        elif kind == "update":
            self.rowcount = value
            self._one = None

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._one or []


class FakeConn:
    def __init__(self, handlers):
        self.handlers = list(handlers)
        self.executed = []
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed += 1


def one(row):
    return lambda sql, params: ("one", row)


def upd(n):
    return lambda sql, params: ("update", n)
