"""Pure-Python indicator calculations. No PyQt, no pandas, no broker deps."""
from __future__ import annotations

from taiwan_futures_trader.domain.models import KDResult, MACDResult, MAResult


def calculate_ma(closes: list[float], period: int) -> MAResult:
    """O(n) running-sum moving average."""
    n = len(closes)
    values: list[float | None] = [None] * min(period - 1, n)
    if n < period:
        return MAResult(period=period, values=values)
    running = sum(closes[:period])
    values.append(running / period)
    for i in range(period, n):
        running += closes[i] - closes[i - period]
        values.append(running / period)
    return MAResult(period=period, values=values)


def _ema(values: list[float], span: int) -> list[float | None]:
    """EMA with SMA seed for the first value."""
    if len(values) < span:
        return [None] * len(values)
    alpha = 2.0 / (span + 1)
    result: list[float | None] = [None] * (span - 1)
    seed = sum(values[:span]) / span
    result.append(seed)
    prev = seed
    for v in values[span:]:
        prev = alpha * v + (1.0 - alpha) * prev
        result.append(prev)
    return result


def calculate_macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MACDResult:
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)

    macd_line: list[float | None] = []
    for f, s in zip(ema_fast, ema_slow):
        if f is None or s is None:
            macd_line.append(None)
        else:
            macd_line.append(f - s)

    valid_macd = [v for v in macd_line if v is not None]
    signal_raw = _ema(valid_macd, signal)

    none_count = sum(1 for v in macd_line if v is None)
    signal_line: list[float | None] = [None] * none_count + signal_raw  # type: ignore[operator]

    histogram: list[float | None] = []
    for m, s in zip(macd_line, signal_line):
        if m is None or s is None:
            histogram.append(None)
        else:
            histogram.append(m - s)

    return MACDResult(macd_line=macd_line, signal_line=signal_line, histogram=histogram)


def calculate_kd(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 9,
) -> KDResult:
    n = len(closes)
    k_line: list[float | None] = []
    d_line: list[float | None] = []
    k_prev = 50.0
    d_prev = 50.0

    for i in range(n):
        if i < period - 1:
            k_line.append(None)
            d_line.append(None)
            continue
        window_h = max(highs[i - period + 1: i + 1])
        window_l = min(lows[i - period + 1: i + 1])
        denom = window_h - window_l if window_h != window_l else 1e-10
        rsv = 100.0 * (closes[i] - window_l) / denom
        k_val = (2.0 / 3.0) * k_prev + (1.0 / 3.0) * rsv
        d_val = (2.0 / 3.0) * d_prev + (1.0 / 3.0) * k_val
        k_line.append(k_val)
        d_line.append(d_val)
        k_prev, d_prev = k_val, d_val

    return KDResult(k_line=k_line, d_line=d_line, period=period)
