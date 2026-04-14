from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class OHLCVBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    open_interest: int

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open


@dataclass
class ViewportState:
    first_bar: int
    last_bar: int


@dataclass
class MAResult:
    period: int
    values: list[float | None]
    visible: bool = True


@dataclass
class MACDResult:
    macd_line: list[float | None]
    signal_line: list[float | None]
    histogram: list[float | None]


@dataclass
class KDResult:
    k_line: list[float | None]
    d_line: list[float | None]
    period: int = 9


@dataclass
class ChartDataset:
    symbol: str
    timeframe: str
    bars: list[OHLCVBar]
    ma_results: list[MAResult] = field(default_factory=list)
    macd: MACDResult | None = None
    kd: KDResult | None = None

    def __len__(self) -> int:
        return len(self.bars)
