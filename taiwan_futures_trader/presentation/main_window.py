"""Top-level QMainWindow assembling all components (CSV-dev: CSV only, no API)."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow, QStatusBar, QWidget

from taiwan_futures_trader.application.chart_controller import ChartController
from taiwan_futures_trader.presentation.chart_panel import ChartPanel
from taiwan_futures_trader.presentation.toolbar import ChartToolbar

# Credentials search order
_ENV_PATHS = [
    Path(__file__).parent.parent.parent / ".env",                        # project root
    Path(__file__).parent.parent.parent.parent / "claude_demo" / ".env", # sibling project
]


def _load_env() -> None:
    """Load .env from known locations; ignore if python-dotenv not installed."""
    try:
        from dotenv import load_dotenv
        for p in _ENV_PATHS:
            if p.exists():
                load_dotenv(p)
                return
    except ImportError:
        pass


class MainWindow(QMainWindow):
    def __init__(
        self,
        default_data_file: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        _load_env()

        # CSV controller
        self._controller = ChartController(self)

        # UI
        self._panel = ChartPanel(self._controller, self)
        self._toolbar = ChartToolbar(self)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)
        self.setCentralWidget(self._panel)

        status = QStatusBar()
        self.setStatusBar(status)
        self._status = status

        # CSV controller wiring
        self._toolbar.symbol_load_requested.connect(
            lambda fp, sym: self._controller.load_symbol(fp, sym, self._current_timeframe())
        )
        self._toolbar.timeframe_changed.connect(self._on_timeframe_changed)
        self._toolbar.ma_toggled.connect(self._on_ma_toggled)
        self._toolbar.macd_toggled.connect(self._on_macd_toggled)
        self._toolbar.kd_toggled.connect(self._on_kd_toggled)

        self._controller.loading_started.connect(lambda: status.showMessage("載入中..."))
        self._controller.dataset_ready.connect(
            lambda ds: status.showMessage(
                f"{ds.symbol}  {ds.timeframe}  共 {len(ds)} 根 K 線"
            )
        )
        self._controller.loading_failed.connect(
            lambda msg: status.showMessage(f"錯誤：{msg}")
        )

    # ---------------------------------------------------------------- slots
    def _current_timeframe(self) -> str:
        for btn in self._toolbar._tf_group.buttons():
            if btn.isChecked():
                return btn.text()
        return "5min"

    def _on_ma_toggled(self, period: int, visible: bool) -> None:
        self._controller.toggle_ma(period, visible)

    def _on_timeframe_changed(self, timeframe: str) -> None:
        self._controller.change_timeframe(timeframe)

    def _on_macd_toggled(self, visible: bool) -> None:
        self._panel.show_macd(visible)
        self._controller.toggle_macd(visible)

    def _on_kd_toggled(self, visible: bool) -> None:
        self._panel.show_kd(visible)
        self._controller.toggle_kd(visible)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        super().closeEvent(event)
