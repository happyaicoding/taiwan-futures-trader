"""ChartToolbar: symbol picker, timeframe buttons, MA/MACD/KD toggles, API connect."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QLabel,
    QPushButton,
    QSpinBox,
    QToolBar,
    QWidget,
)

_DOT_OFFLINE = "color: #9E9E9E; font-size: 16px;"
_DOT_LIVE    = "color: #26A69A; font-size: 16px;"
_DOT_ERROR   = "color: #EF5350; font-size: 16px;"


class ChartToolbar(QToolBar):
    symbol_load_requested = pyqtSignal(str, str)  # (filepath, symbol)
    timeframe_changed = pyqtSignal(str)
    session_filter_changed = pyqtSignal(str)      # "all" | "day" | "night"
    ma_toggled = pyqtSignal(int, bool)            # (period, visible)
    macd_toggled = pyqtSignal(bool)
    kd_toggled = pyqtSignal(bool)
    api_connect_requested = pyqtSignal(bool)      # True=connect, False=disconnect

    TIMEFRAMES = ["1min", "5min", "15min", "30min", "1h", "日K"]
    MA_PERIODS  = [5, 10, 20, 60]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Controls", parent)
        self.setMovable(False)
        self._build_ui()

    def _build_ui(self) -> None:
        # --- API connect button + status dot
        self._connect_btn = QPushButton("連線 API")
        self._connect_btn.setCheckable(True)
        self._connect_btn.setFixedWidth(72)
        self._connect_btn.toggled.connect(self.api_connect_requested)
        self.addWidget(self._connect_btn)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(_DOT_OFFLINE)
        self._status_dot.setToolTip("未連線")
        self.addWidget(self._status_dot)
        self.addSeparator()

        # --- File open button
        open_btn = QPushButton("開啟 CSV")
        open_btn.clicked.connect(self._on_open_csv)
        self.addWidget(open_btn)
        self.addSeparator()

        # --- Timeframe radio buttons
        self.addWidget(QLabel("週期:"))
        self._tf_group = QButtonGroup(self)
        self._tf_group.setExclusive(True)
        for tf in self.TIMEFRAMES:
            btn = QPushButton(tf)
            btn.setCheckable(True)
            btn.setFixedWidth(52)
            if tf == "5min":
                btn.setChecked(True)
            self._tf_group.addButton(btn)
            self.addWidget(btn)
            btn.clicked.connect(lambda checked, t=tf: self._on_preset_tf(t))

        # --- Custom minute input
        self.addWidget(QLabel(" 自訂:"))
        self._custom_spin = QSpinBox()
        self._custom_spin.setRange(1, 999)
        self._custom_spin.setValue(1)
        self._custom_spin.setSuffix(" 分")
        self._custom_spin.setFixedWidth(76)
        self._custom_spin.setToolTip("輸入任意分鐘數，按 Enter 或點「繪製」")
        self._custom_spin.editingFinished.connect(self._on_custom_tf)
        self.addWidget(self._custom_spin)

        draw_btn = QPushButton("繪製")
        draw_btn.setFixedWidth(46)
        draw_btn.setToolTip("繪製自訂分 K 線圖")
        draw_btn.clicked.connect(self._on_custom_tf)
        self.addWidget(draw_btn)

        self.addSeparator()

        # --- Session filter buttons (日+夜 / 日盤 / 夜盤)
        self.addWidget(QLabel("時段:"))
        self._session_group = QButtonGroup(self)
        self._session_group.setExclusive(True)
        _sessions = [("日+夜", "all"), ("日盤", "day"), ("夜盤", "night")]
        for label, key in _sessions:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedWidth(52)
            if key == "all":
                btn.setChecked(True)
            self._session_group.addButton(btn)
            self.addWidget(btn)
            btn.clicked.connect(lambda checked, k=key: self.session_filter_changed.emit(k))

        self.addSeparator()

        # --- MA toggles
        self.addWidget(QLabel("MA:"))
        MA_COLORS = {5: "#FFD700", 10: "#00BFFF", 20: "#FF8C00", 60: "#9370DB"}
        for period in self.MA_PERIODS:
            cb = QCheckBox(str(period))
            cb.setChecked(True)
            color = MA_COLORS.get(period, "#FFFFFF")
            cb.setStyleSheet(f"color: {color};")
            cb.toggled.connect(lambda checked, p=period: self.ma_toggled.emit(p, checked))
            self.addWidget(cb)
        self.addSeparator()

        # --- Indicator toggles
        macd_cb = QCheckBox("MACD")
        macd_cb.setChecked(True)
        macd_cb.toggled.connect(self.macd_toggled)
        self.addWidget(macd_cb)

        kd_cb = QCheckBox("KD")
        kd_cb.setChecked(True)
        kd_cb.toggled.connect(self.kd_toggled)
        self.addWidget(kd_cb)

    def _on_preset_tf(self, tf: str) -> None:
        """Called when a preset timeframe button is clicked."""
        self.timeframe_changed.emit(tf)

    def _on_custom_tf(self) -> None:
        """Called when the custom spinbox fires or Draw button is clicked."""
        minutes = self._custom_spin.value()
        tf = f"{minutes}min"
        # Uncheck all preset buttons so none appears selected
        for btn in self._tf_group.buttons():
            btn.setChecked(False)
        self.timeframe_changed.emit(tf)

    def _on_open_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "開啟 K 線 CSV",
            str(Path.home()),
            "CSV 檔案 (*.csv);;所有檔案 (*)",
        )
        if path:
            symbol = Path(path).stem.split("_")[0].upper()
            self.symbol_load_requested.emit(path, symbol)

    def load_default(self, filepath: str, symbol: str = "TXFR1") -> None:
        """Programmatically trigger a load without UI interaction."""
        self.symbol_load_requested.emit(filepath, symbol)

    def set_api_status(self, status: str) -> None:
        """Update the live status dot. status: 'connecting', 'live', 'disconnected', 'error: ...'"""
        if status == "live":
            self._status_dot.setStyleSheet(_DOT_LIVE)
            self._status_dot.setToolTip("即時連線中")
            self._connect_btn.setText("斷線")
        elif status == "disconnected":
            self._status_dot.setStyleSheet(_DOT_OFFLINE)
            self._status_dot.setToolTip("未連線")
            self._connect_btn.setText("連線 API")
            # Reset button state without re-emitting signal
            self._connect_btn.blockSignals(True)
            self._connect_btn.setChecked(False)
            self._connect_btn.blockSignals(False)
        elif status == "connecting":
            self._status_dot.setStyleSheet(_DOT_OFFLINE)
            self._status_dot.setToolTip("連線中...")
        elif status.startswith("error"):
            self._status_dot.setStyleSheet(_DOT_ERROR)
            self._status_dot.setToolTip(status)
            self._connect_btn.setText("連線 API")
            self._connect_btn.blockSignals(True)
            self._connect_btn.setChecked(False)
            self._connect_btn.blockSignals(False)
