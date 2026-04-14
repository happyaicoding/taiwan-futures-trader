"""Top-level QMainWindow assembling all components."""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMainWindow, QMessageBox, QStatusBar, QWidget

from taiwan_futures_trader.application.chart_controller import ChartController
from taiwan_futures_trader.application.realtime_controller import RealtimeController
from taiwan_futures_trader.infrastructure.bar_store import BarStore
from taiwan_futures_trader.infrastructure.database import Database
from taiwan_futures_trader.infrastructure.shioaji_adapter import ShioajiAdapter
from taiwan_futures_trader.infrastructure.tick_store import TickStore
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


def _get_credentials() -> tuple[str, str] | None:
    """Return (api_key, secret_key) from env, or prompt the user."""
    api_key = os.environ.get("SINOPAC_API_KEY", "")
    secret_key = os.environ.get("SINOPAC_SECRET_KEY", "")
    if api_key and secret_key:
        return api_key, secret_key

    # Prompt via dialog
    api_key, ok = QInputDialog.getText(None, "永豐 API 金鑰", "API Key:", QLineEdit.EchoMode.Normal)
    if not ok or not api_key:
        return None
    secret_key, ok = QInputDialog.getText(None, "永豐 API 金鑰", "Secret Key:", QLineEdit.EchoMode.Password)
    if not ok or not secret_key:
        return None
    return api_key, secret_key


class MainWindow(QMainWindow):
    def __init__(
        self,
        default_data_file: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        _load_env()

        # CSV controller (existing)
        self._controller = ChartController(self)

        # Realtime infrastructure
        db_path = Path(__file__).parent.parent.parent / "data" / "futures.db"
        self._db = Database(db_path)
        self._db.initialize()
        self._adapter = ShioajiAdapter(simulation=True)
        self._tick_store = TickStore(self._db)
        self._bar_store = BarStore(self._db)
        self._rt_ctrl = RealtimeController(
            self._adapter, self._tick_store, self._bar_store, self
        )

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
        self._toolbar.session_filter_changed.connect(self._on_session_filter_changed)
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

        # Realtime controller wiring
        self._toolbar.api_connect_requested.connect(self._on_api_connect)
        self._rt_ctrl.dataset_ready.connect(self._panel._on_dataset_ready)
        self._rt_ctrl.dataset_ready.connect(self._on_rt_dataset_ready)
        self._rt_ctrl.status_changed.connect(self._toolbar.set_api_status)
        self._rt_ctrl.status_changed.connect(self._on_rt_status)

        self._is_live = False
        self._has_db_data = False

        # Load historical bars from DB on startup (no API login needed)
        self._rt_ctrl.load_from_db(self._current_timeframe())

    # ---------------------------------------------------------------- slots
    def _current_timeframe(self) -> str:
        for btn in self._toolbar._tf_group.buttons():
            if btn.isChecked():
                return btn.text()
        return "5min"

    def _on_rt_dataset_ready(self, ds) -> None:
        if not self._is_live:
            self._has_db_data = len(ds) > 0
        suffix = "  [即時]" if self._is_live else ""
        self._status.showMessage(
            f"{ds.symbol}  {ds.timeframe}  共 {len(ds)} 根 K 線{suffix}"
        )

    def _on_ma_toggled(self, period: int, visible: bool) -> None:
        if self._is_live or self._has_db_data:
            self._rt_ctrl.toggle_ma(period, visible)
        else:
            self._controller.toggle_ma(period, visible)

    def _on_session_filter_changed(self, session: str) -> None:
        if self._is_live or self._has_db_data:
            self._rt_ctrl.change_session_filter(session)

    def _on_timeframe_changed(self, timeframe: str) -> None:
        if self._is_live or self._has_db_data:
            self._rt_ctrl.change_timeframe(timeframe)
        else:
            self._controller.change_timeframe(timeframe)

    def _on_macd_toggled(self, visible: bool) -> None:
        self._panel.show_macd(visible)
        if self._is_live or self._has_db_data:
            self._rt_ctrl.toggle_macd(visible)
        else:
            self._controller.toggle_macd(visible)

    def _on_kd_toggled(self, visible: bool) -> None:
        self._panel.show_kd(visible)
        if self._is_live or self._has_db_data:
            self._rt_ctrl.toggle_kd(visible)
        else:
            self._controller.toggle_kd(visible)

    def _on_api_connect(self, checked: bool) -> None:
        if checked:
            creds = _get_credentials()
            if creds is None:
                # User cancelled — reset button
                self._toolbar.set_api_status("disconnected")
                return
            api_key, secret_key = creds
            self._rt_ctrl.connect(
                api_key, secret_key,
                timeframe=self._current_timeframe(),
            )
        else:
            self._rt_ctrl.disconnect()

    def _on_rt_status(self, status: str) -> None:
        self._is_live = (status == "live")
        if status.startswith("error"):
            QMessageBox.warning(self, "API 連線失敗", status)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._adapter.is_logged_in:
            self._rt_ctrl.disconnect()
        self._db.close_all()
        super().closeEvent(event)
        # Shioaji C-extension cleanup triggers a segfault during normal interpreter
        # shutdown; force-exit after Qt teardown to bypass it cleanly.
        import os as _os
        _os._exit(0)
