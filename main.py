"""Entry point for Taiwan Futures Trader."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from taiwan_futures_trader.presentation.main_window import MainWindow

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

DARK_STYLESHEET = """
QWidget            { background-color: #131722; color: #d1d4dc;
                     font-family: "Microsoft JhengHei", "Segoe UI", sans-serif; font-size: 12px; }
QMainWindow        { background-color: #131722; }
QToolBar           { background-color: #1e222d; border-bottom: 1px solid #2a2e39; spacing: 6px;
                     padding: 3px; }
QStatusBar         { background-color: #1e222d; border-top: 1px solid #2a2e39; }
QSplitter::handle  { background-color: #2a2e39; }
QPushButton        { background-color: #2a2e39; border: 1px solid #363a45;
                     border-radius: 3px; padding: 3px 8px; color: #d1d4dc; }
QPushButton:hover  { background-color: #363a45; }
QPushButton:checked{ background-color: #2962ff; border-color: #2962ff; }
QCheckBox          { spacing: 4px; }
QCheckBox::indicator { width: 13px; height: 13px; }
QLabel             { color: #9598a1; }
QStatusBar         { color: #9598a1; }
"""

DEFAULT_DATA_FILE = Path(__file__).parent / "data" / "TXFR1_1min.csv"


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow(default_data_file=DEFAULT_DATA_FILE)
    window.setWindowTitle("台指期看盤 MVP — TXFR1")
    window.resize(1400, 900)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
