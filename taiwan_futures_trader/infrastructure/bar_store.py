"""OHLCV bar persistence: upsert and query bars from SQLite."""
from __future__ import annotations

from datetime import date, datetime

from taiwan_futures_trader.domain.models import OHLCVBar
from taiwan_futures_trader.infrastructure.database import Database


class BarStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert_bars(self, symbol: str, timeframe: str, bars: list[OHLCVBar]) -> None:
        if not bars:
            return
        conn = self._db.get_connection()
        conn.executemany(
            """
            INSERT INTO bars (symbol, timeframe, ts, open, high, low, close, volume, open_interest)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe, ts) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low,
                close=excluded.close, volume=excluded.volume,
                open_interest=excluded.open_interest
            """,
            [
                (
                    symbol, timeframe,
                    b.timestamp.isoformat(),
                    b.open, b.high, b.low, b.close,
                    b.volume, b.open_interest,
                )
                for b in bars
            ],
        )
        conn.commit()

    def query_bars(
        self, symbol: str, timeframe: str, start: date, end: date
    ) -> list[OHLCVBar]:
        conn = self._db.get_connection()
        rows = conn.execute(
            """
            SELECT ts, open, high, low, close, volume, open_interest
            FROM bars
            WHERE symbol = ? AND timeframe = ? AND ts >= ? AND ts <= ?
            ORDER BY ts
            """,
            (symbol, timeframe, start.isoformat(), end.isoformat() + "T23:59:59"),
        ).fetchall()
        return [
            OHLCVBar(
                timestamp=datetime.fromisoformat(r["ts"]),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=int(r["volume"]),
                open_interest=int(r["open_interest"] or 0),
            )
            for r in rows
        ]

    def get_latest_date(self, symbol: str, timeframe: str) -> date | None:
        """Return the date of the most recent bar, or None if no data."""
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT MAX(ts) AS max_ts FROM bars WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe),
        ).fetchone()
        if row and row["max_ts"]:
            return datetime.fromisoformat(row["max_ts"]).date()
        return None
