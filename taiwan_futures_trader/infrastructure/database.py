"""SQLite connection manager with thread-local connections."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


_DDL = """
CREATE TABLE IF NOT EXISTS ticks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol   TEXT    NOT NULL,
    ts       TEXT    NOT NULL,
    price    REAL    NOT NULL,
    volume   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ticks_symbol_ts ON ticks(symbol, ts);

CREATE TABLE IF NOT EXISTS bars (
    symbol        TEXT NOT NULL,
    timeframe     TEXT NOT NULL,
    ts            TEXT NOT NULL,
    open          REAL,
    high          REAL,
    low           REAL,
    close         REAL,
    volume        INTEGER,
    open_interest INTEGER,
    PRIMARY KEY (symbol, timeframe, ts)
);
"""


class Database:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._local = threading.local()

    def get_connection(self) -> sqlite3.Connection:
        """Return a thread-local SQLite connection, creating it if needed."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def initialize(self) -> None:
        """Create tables if they don't exist."""
        conn = self.get_connection()
        conn.executescript(_DDL)
        conn.commit()

    def close_all(self) -> None:
        """Close this thread's connection if open."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
