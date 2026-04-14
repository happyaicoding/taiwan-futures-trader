"""Application service: load CSV, compute indicators, build ChartDataset."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from taiwan_futures_trader.domain.indicators import (
    calculate_kd,
    calculate_ma,
    calculate_macd,
)
from taiwan_futures_trader.domain.models import ChartDataset, OHLCVBar
from taiwan_futures_trader.infrastructure.column_mapper import ColumnMapper

_RESAMPLE_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
    "open_interest": "last",
}

# Only non-trivial mappings (identity "Nmin" entries handled by the regex fallback)
_FREQ_MAP: dict[str, str] = {
    "1h":  "1h",
    "1d":  "1D",
    "日K": "1D",
}


class ChartDataService:
    def __init__(self) -> None:
        self._mapper = ColumnMapper()

    def load_csv(self, filepath: str | Path) -> pd.DataFrame:
        """Read a CSV, normalize columns, sort by timestamp."""
        raw = pd.read_csv(filepath)
        df = self._mapper.map(raw)
        df = df.set_index("timestamp").sort_index()
        return df

    def resample(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """Resample a timestamp-indexed DataFrame to a coarser timeframe.

        Accepts:
          - fixed labels: "1min", "5min", "15min", "30min", "1h", "1d"
          - arbitrary minute counts: "4min", "50min", "7min" …
        """
        freq = _FREQ_MAP.get(timeframe)
        if freq is None:
            m = re.fullmatch(r"(\d+)min", timeframe)
            if m:
                freq = f"{m.group(1)}min"
            else:
                raise ValueError(
                    f"Unknown timeframe: {timeframe!r}. "
                    f"Use fixed labels {list(_FREQ_MAP)} or 'Nmin' (e.g. '4min', '50min')."
                )
        resampled = df.resample(freq).agg(_RESAMPLE_AGG).dropna()
        return resampled

    def bars_to_dataframe(self, bars: list[OHLCVBar]) -> pd.DataFrame:
        """Convert a list of OHLCVBar into a timestamp-indexed DataFrame."""
        import pandas as pd

        data = {
            "timestamp": [b.timestamp for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
            "open_interest": [b.open_interest for b in bars],
        }
        df = pd.DataFrame(data).set_index("timestamp").sort_index()
        return df

    def prepare_chart_dataset_from_bars(
        self,
        bars: list[OHLCVBar],
        symbol: str,
        timeframe: str,
        ma_periods: list[int] | None = None,
        include_macd: bool = True,
        include_kd: bool = True,
    ) -> ChartDataset:
        """Build ChartDataset directly from a list of OHLCVBar (skips CSV/resample)."""
        if ma_periods is None:
            ma_periods = [5, 10, 20, 60]
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        ma_results = [calculate_ma(closes, p) for p in ma_periods]
        macd = calculate_macd(closes) if include_macd else None
        kd = calculate_kd(highs, lows, closes) if include_kd else None
        return ChartDataset(
            symbol=symbol,
            timeframe=timeframe,
            bars=list(bars),
            ma_results=ma_results,
            macd=macd,
            kd=kd,
        )

    def prepare_chart_dataset(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        ma_periods: list[int] | None = None,
        include_macd: bool = True,
        include_kd: bool = True,
    ) -> ChartDataset:
        if ma_periods is None:
            ma_periods = [5, 10, 20, 60]

        df = df.reset_index()  # bring timestamp back as column

        bars: list[OHLCVBar] = [
            OHLCVBar(
                timestamp=row.timestamp.to_pydatetime(),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=int(row.volume),
                open_interest=int(row.open_interest),
            )
            for row in df.itertuples(index=False)
        ]

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        ma_results = [calculate_ma(closes, p) for p in ma_periods]
        macd = calculate_macd(closes) if include_macd else None
        kd = calculate_kd(highs, lows, closes) if include_kd else None

        return ChartDataset(
            symbol=symbol,
            timeframe=timeframe,
            bars=bars,
            ma_results=ma_results,
            macd=macd,
            kd=kd,
        )
