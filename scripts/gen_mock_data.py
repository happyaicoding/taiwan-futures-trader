"""Generate mock TXFR1 1-minute OHLCV data for development/testing.

Usage:
    python scripts/gen_mock_data.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"


def _trading_timestamps(n_days: int, freq: str = "1min") -> pd.DatetimeIndex:
    """Return timestamps for Taiwan futures day session (08:45-13:45)."""
    all_ts: list[pd.Timestamp] = []
    start_date = pd.Timestamp("2024-01-02")
    day = start_date
    count = 0
    while count < n_days:
        if day.weekday() < 5:  # Mon-Fri
            session = pd.date_range(
                start=day.replace(hour=8, minute=45),
                end=day.replace(hour=13, minute=45),
                freq=freq,
            )
            all_ts.extend(session)
            count += 1
        day += pd.Timedelta(days=1)
    return pd.DatetimeIndex(all_ts)


def generate_txfr1(
    n_days: int = 20,
    freq: str = "1min",
    seed: int = 42,
    start_price: float = 19500.0,
    output_path: Path | None = None,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    timestamps = _trading_timestamps(n_days, freq)
    n = len(timestamps)

    # Price walk (geometric Brownian motion, σ scaled for 1-min bars)
    log_returns = rng.normal(0, 0.001, size=n)
    prices = start_price * np.exp(np.cumsum(log_returns))

    bars_per_day = len(pd.date_range("08:45", "13:45", freq=freq))

    opens, highs, lows, closes, volumes = [], [], [], [], []
    prev_close = start_price
    for i, p in enumerate(prices):
        o = prev_close
        c = float(round(p, 0))
        wick_up = abs(rng.normal(0, 0.0005)) * max(o, c)
        wick_dn = abs(rng.normal(0, 0.0005)) * min(o, c)
        h = float(round(max(o, c) + wick_up, 0))
        l = float(round(min(o, c) - wick_dn, 0))
        opens.append(float(round(o, 0)))
        highs.append(h)
        lows.append(max(l, 1.0))
        closes.append(c)
        prev_close = c

        # Volume: session-open and session-close spikes
        bar_in_session = i % bars_per_day
        vol_base = rng.lognormal(4.5, 0.8)
        if bar_in_session < 3 or bar_in_session > bars_per_day - 4:
            vol_base *= 1.8
        volumes.append(max(1, int(vol_base)))

    # Open interest: bounded random walk
    oi = [int(rng.integers(79_000, 81_000))]
    for _ in range(n - 1):
        step = int(rng.normal(0, 50))
        oi.append(max(60_000, min(120_000, oi[-1] + step)))

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "open_interest": oi,
    })

    if output_path is None:
        output_path = DATA_DIR / "TXFR1_1min.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Written {len(df)} rows -> {output_path}")

    # Alt-column version to exercise ColumnMapper
    alt_path = DATA_DIR / "TXFR1_1min_altcols.csv"
    df_alt = df.rename(columns={
        "timestamp": "Date", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Vol", "open_interest": "oi",
    })
    df_alt.to_csv(alt_path, index=False)
    print(f"Written alt-cols version -> {alt_path}")

    return df


if __name__ == "__main__":
    generate_txfr1()
