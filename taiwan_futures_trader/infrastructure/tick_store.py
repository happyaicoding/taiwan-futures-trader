"""Tick persistence: write and query raw ticks from SQLite."""
from __future__ import annotations

from datetime import datetime

from taiwan_futures_trader.infrastructure.database import Database


class TickStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, symbol: str, ts: datetime, price: float, volume: int) -> None:
        conn = self._db.get_connection()
        conn.execute(
            "INSERT INTO ticks (symbol, ts, price, volume) VALUES (?, ?, ?, ?)",
            (symbol, ts.isoformat(), price, volume),
        )
        conn.commit()

    def query(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[tuple[datetime, float, int]]:
        """Return [(ts, price, volume), ...] sorted ascending."""
        conn = self._db.get_connection()
        rows = conn.execute(
            "SELECT ts, price, volume FROM ticks "
            "WHERE symbol = ? AND ts >= ? AND ts <= ? ORDER BY ts",
            (symbol, start.isoformat(), end.isoformat()),
        ).fetchall()
        return [(datetime.fromisoformat(r["ts"]), float(r["price"]), int(r["volume"])) for r in rows]

    def clear_old(self, symbol: str, before: datetime) -> None:
        conn = self._db.get_connection()
        conn.execute(
            "DELETE FROM ticks WHERE symbol = ? AND ts < ?",
            (symbol, before.isoformat()),
        )
        conn.commit()
