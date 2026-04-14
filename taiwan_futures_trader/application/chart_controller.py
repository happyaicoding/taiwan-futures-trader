"""ChartController + background loader thread."""
from __future__ import annotations

import logging

import pandas as pd
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from taiwan_futures_trader.application.chart_data_service import ChartDataService
from taiwan_futures_trader.domain.models import ChartDataset

logger = logging.getLogger(__name__)


class _LoaderThread(QThread):
    # Emits (dataset, base_df | None) — base_df is non-None only on a fresh CSV load
    data_ready = pyqtSignal(object, object)
    error = pyqtSignal(str)

    def __init__(
        self,
        filepath: str,
        symbol: str,
        timeframe: str,
        ma_periods: list[int],
        include_macd: bool,
        include_kd: bool,
        base_df: pd.DataFrame | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._filepath = filepath
        self._symbol = symbol
        self._timeframe = timeframe
        self._ma_periods = ma_periods
        self._include_macd = include_macd
        self._include_kd = include_kd
        self._base_df = base_df          # pre-loaded df; if None, load from disk
        self._service = ChartDataService()

    def run(self) -> None:
        try:
            if self._base_df is not None:
                df = self._base_df
                new_base_df = None       # no new base to propagate
            else:
                df = self._service.load_csv(self._filepath)
                new_base_df = df         # expose freshly loaded df to controller

            df_ready = self._service.resample(df, self._timeframe)
            dataset = self._service.prepare_chart_dataset(
                df_ready,
                symbol=self._symbol,
                timeframe=self._timeframe,
                ma_periods=self._ma_periods,
                include_macd=self._include_macd,
                include_kd=self._include_kd,
            )
            self.data_ready.emit(dataset, new_base_df)
        except Exception as exc:
            logger.exception("Failed to load chart data")
            self.error.emit(str(exc))


class ChartController(QObject):
    dataset_ready = pyqtSignal(object)   # ChartDataset
    loading_started = pyqtSignal()
    loading_failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = ChartDataService()
        self._thread: _LoaderThread | None = None
        self._base_df: pd.DataFrame | None = None       # cached after first CSV load
        self._last_dataset: ChartDataset | None = None
        self._current_filepath: str = ""
        self._current_symbol: str = ""
        self._current_timeframe: str = "5min"
        self._ma_periods: list[int] = [5, 10, 20, 60]
        self._include_macd: bool = True
        self._include_kd: bool = True
        self._ma_visibility: dict[int, bool] = {p: True for p in self._ma_periods}

    # ----------------------------------------------------------------- public
    def load_symbol(self, filepath: str, symbol: str, timeframe: str = "5min") -> None:
        self._current_filepath = filepath
        self._current_symbol = symbol
        self._current_timeframe = timeframe
        self._base_df = None             # force re-read from disk for new file
        self._start_loader(filepath, symbol, timeframe)

    def change_timeframe(self, timeframe: str) -> None:
        if not self._current_filepath:
            return
        self._current_timeframe = timeframe
        # Pass cached base_df so the thread skips disk I/O
        self._start_loader(
            self._current_filepath,
            self._current_symbol,
            timeframe,
            base_df=self._base_df,
        )

    def toggle_ma(self, period: int, visible: bool) -> None:
        self._ma_visibility[period] = visible
        if self._last_dataset is not None:
            for ma in self._last_dataset.ma_results:
                if ma.period == period:
                    ma.visible = visible
            self.dataset_ready.emit(self._last_dataset)

    def toggle_macd(self, visible: bool) -> None:
        self._include_macd = visible
        if visible and self._last_dataset is not None and self._last_dataset.macd is None:
            # MACD was never computed — reload to compute it
            self._start_loader(
                self._current_filepath,
                self._current_symbol,
                self._current_timeframe,
                base_df=self._base_df,
            )

    def toggle_kd(self, visible: bool) -> None:
        self._include_kd = visible
        if visible and self._last_dataset is not None and self._last_dataset.kd is None:
            self._start_loader(
                self._current_filepath,
                self._current_symbol,
                self._current_timeframe,
                base_df=self._base_df,
            )

    # ----------------------------------------------------------------- private
    def _start_loader(
        self,
        filepath: str,
        symbol: str,
        timeframe: str,
        base_df: pd.DataFrame | None = None,
    ) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.data_ready.disconnect()
            self._thread.error.disconnect()
            self._thread.quit()
            self._thread.wait(500)

        self.loading_started.emit()
        self._thread = _LoaderThread(
            filepath=filepath,
            symbol=symbol,
            timeframe=timeframe,
            ma_periods=self._ma_periods,
            include_macd=self._include_macd,
            include_kd=self._include_kd,
            base_df=base_df,
            parent=self,
        )
        self._thread.data_ready.connect(self._on_data_ready)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_data_ready(self, dataset: ChartDataset, new_base_df: object) -> None:
        if isinstance(new_base_df, pd.DataFrame):
            self._base_df = new_base_df
        for ma in dataset.ma_results:
            ma.visible = self._ma_visibility.get(ma.period, True)
        self._last_dataset = dataset
        self.dataset_ready.emit(dataset)

    def _on_error(self, message: str) -> None:
        self.loading_failed.emit(message)
