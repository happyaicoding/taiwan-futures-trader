"""ChartPanel: vertical QSplitter wiring all chart widgets."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from taiwan_futures_trader.application.chart_controller import ChartController
from taiwan_futures_trader.domain.models import ChartDataset
from taiwan_futures_trader.presentation.candlestick_widget import CandlestickWidget
from taiwan_futures_trader.presentation.crosshair import CrosshairState
from taiwan_futures_trader.presentation.indicator_widget import KDWidget, MACDWidget
from taiwan_futures_trader.presentation.volume_widget import VolumeWidget


class ChartPanel(QWidget):
    def __init__(self, controller: ChartController, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._crosshair = CrosshairState(self)

        self._candle = CandlestickWidget(self._crosshair, self)
        self._volume = VolumeWidget(self._crosshair, self)
        self._macd   = MACDWidget(self._crosshair, self)
        self._kd     = KDWidget(self._crosshair, self)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self._candle)
        splitter.addWidget(self._volume)
        splitter.addWidget(self._macd)
        splitter.addWidget(self._kd)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)
        splitter.setStretchFactor(3, 2)
        splitter.setSizes([500, 80, 120, 120])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._candle.viewport_changed.connect(self._volume.set_viewport)
        self._candle.viewport_changed.connect(self._macd.set_viewport)
        self._candle.viewport_changed.connect(self._kd.set_viewport)

        controller.dataset_ready.connect(self._on_dataset_ready)

    def _on_dataset_ready(self, dataset: ChartDataset) -> None:
        self._candle.set_dataset(dataset)
        vp = self._candle._viewport
        self._volume.set_dataset(dataset)
        self._volume.set_viewport(vp)
        self._macd.set_dataset(dataset)
        self._macd.set_viewport(vp)
        self._kd.set_dataset(dataset)
        self._kd.set_viewport(vp)

    def show_macd(self, visible: bool) -> None:
        self._macd.setVisible(visible)

    def show_kd(self, visible: bool) -> None:
        self._kd.setVisible(visible)
