"""BarBuilder: aggregate tick stream into OHLCV bars (international convention)."""
from __future__ import annotations

from datetime import datetime

from taiwan_futures_trader.domain.models import OHLCVBar


def _bar_start(ts: datetime, n: int) -> datetime:
    """Floor timestamp to the nearest N-minute boundary (international convention)."""
    bar_minute = (ts.minute // n) * n
    return ts.replace(minute=bar_minute, second=0, microsecond=0)


class BarBuilder:
    """
    Aggregates a tick stream into OHLCV bars for an N-minute timeframe.

    International Minute K convention:
      tick at 08:45:30 → bar_start = 08:45:00
      tick at 08:59:59 → bar_start = 08:45:00  (for N=15: (45//15)*15=45)
    """

    def __init__(self, timeframe_minutes: int) -> None:
        self._n = timeframe_minutes
        self._current: OHLCVBar | None = None
        self._current_bar_start: datetime | None = None

    def push_tick(
        self, ts: datetime, price: float, volume: int
    ) -> tuple[OHLCVBar | None, OHLCVBar]:
        """
        Feed one tick.

        Returns:
            (completed_bar, current_bar)
            completed_bar is non-None only when a new bar boundary is crossed.
        """
        bar_start = _bar_start(ts, self._n)
        completed: OHLCVBar | None = None

        if self._current is None:
            # First tick ever
            self._current = OHLCVBar(
                timestamp=bar_start,
                open=price, high=price, low=price, close=price,
                volume=volume, open_interest=0,
            )
            self._current_bar_start = bar_start
        elif bar_start != self._current_bar_start:
            # New bar period — seal the old bar
            completed = self._current
            self._current = OHLCVBar(
                timestamp=bar_start,
                open=price, high=price, low=price, close=price,
                volume=volume, open_interest=0,
            )
            self._current_bar_start = bar_start
        else:
            # Same bar — update H/L/C/Volume
            self._current = OHLCVBar(
                timestamp=self._current.timestamp,
                open=self._current.open,
                high=max(self._current.high, price),
                low=min(self._current.low, price),
                close=price,
                volume=self._current.volume + volume,
                open_interest=0,
            )

        return completed, self._current

    def reset(self, timeframe_minutes: int | None = None) -> None:
        if timeframe_minutes is not None:
            self._n = timeframe_minutes
        self._current = None
        self._current_bar_start = None

    def seed(self, bar: OHLCVBar) -> None:
        """
        Pre-load a known in-progress bar so the next live tick continues from
        this state rather than starting a brand-new bar from scratch.
        Useful after reconnecting with a partially-built bar reconstructed from
        api.ticks() historical data.
        """
        self._current = bar
        self._current_bar_start = bar.timestamp  # already floored to N-min boundary

    @property
    def current_bar(self) -> OHLCVBar | None:
        return self._current
