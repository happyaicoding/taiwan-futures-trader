"""QAbstractTableModel wrapping a list of OHLCVBar for QTableView display."""
from __future__ import annotations

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor

from taiwan_futures_trader.domain.models import OHLCVBar

_HEADERS = ["時間", "開", "高", "低", "收", "量", "未平倉", "漲跌", "漲跌%"]
_GREEN = QColor("#26A69A")
_RED   = QColor("#EF5350")


class OHLCVTableModel(QAbstractTableModel):
    def __init__(self, bars: list[OHLCVBar] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._bars: list[OHLCVBar] = bars or []

    def set_bars(self, bars: list[OHLCVBar]) -> None:
        self.beginResetModel()
        self._bars = bars
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._bars)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(_HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return _HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row < 0 or row >= len(self._bars):
            return None
        bar = self._bars[row]
        prev_close = self._bars[row - 1].close if row > 0 else bar.open
        change = bar.close - prev_close
        change_pct = change / prev_close * 100 if prev_close else 0.0

        if role == Qt.ItemDataRole.DisplayRole:
            mapping = [
                bar.timestamp.strftime("%Y-%m-%d %H:%M"),
                f"{bar.open:,.0f}",
                f"{bar.high:,.0f}",
                f"{bar.low:,.0f}",
                f"{bar.close:,.0f}",
                f"{bar.volume:,d}",
                f"{bar.open_interest:,d}",
                f"{change:+,.0f}",
                f"{change_pct:+.2f}%",
            ]
            return mapping[col]

        if role == Qt.ItemDataRole.ForegroundRole and col in (7, 8):
            return _GREEN if change >= 0 else _RED

        return None
