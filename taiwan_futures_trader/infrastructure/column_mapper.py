"""Single source of truth for column name normalization.

All DataFrames entering the Application layer MUST be passed through
ColumnMapper.map() first. Never do column aliasing anywhere else.
"""
from __future__ import annotations

import pandas as pd

CANONICAL_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "open_interest",
]

ALIASES: dict[str, list[str]] = {
    "timestamp": [
        "Timestamp", "time", "Time", "date", "Date", "datetime", "Datetime",
        "ts", "TS", "日期", "時間",
    ],
    "open": ["Open", "OPEN", "o", "first", "開盤價", "開"],
    "high": ["High", "HIGH", "h", "max", "最高價", "高"],
    "low":  ["Low",  "LOW",  "l", "min", "最低價", "低"],
    "close": [
        "Close", "CLOSE", "c", "price", "last", "收盤價", "收",
    ],
    "volume": [
        "Volume", "VOLUME", "vol", "Vol", "VOL", "qty",
        "總Volume", "成交量", "v",
    ],
    "open_interest": [
        "OpenInterest", "open_int", "OI", "oi", "oi_qty",
        "未平倉量", "未平倉",
    ],
}


class ColumnMappingError(ValueError):
    pass


class ColumnMapper:
    def __init__(self) -> None:
        self._reverse: dict[str, str] = {}
        for canonical, aliases in ALIASES.items():
            for alias in aliases:
                self._reverse[alias] = canonical

    def map(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rename columns to canonical names and cast types.

        Raises ColumnMappingError if a required canonical column cannot
        be resolved.
        """
        rename_map: dict[str, str] = {}
        for col in df.columns:
            if col in CANONICAL_COLUMNS:
                continue  # already canonical
            if col in self._reverse:
                rename_map[col] = self._reverse[col]

        result = df.rename(columns=rename_map)

        missing = self.validate(result)
        if missing:
            raise ColumnMappingError(
                f"Cannot map required columns: {missing}. "
                f"Available columns: {list(result.columns)}"
            )

        result = result[CANONICAL_COLUMNS].copy()
        result["timestamp"] = pd.to_datetime(result["timestamp"])
        for col in ("open", "high", "low", "close"):
            result[col] = result[col].astype("float64")
        for col in ("volume", "open_interest"):
            result[col] = result[col].astype("int64")

        return result

    def validate(self, df: pd.DataFrame) -> list[str]:
        """Return list of canonical columns missing from df (no raise)."""
        return [c for c in CANONICAL_COLUMNS if c not in df.columns]
