"""MACD and KD subplot widgets."""
from __future__ import annotations

import itertools

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from taiwan_futures_trader.domain.models import ChartDataset, ViewportState
from taiwan_futures_trader.presentation.crosshair import (
    CoordTransform,
    CrosshairMixin,
    CrosshairState,
)

MARGIN_LEFT   = 0
MARGIN_RIGHT  = 65
MARGIN_TOP    = 5
MARGIN_BOTTOM = 5


class MACDWidget(QWidget, CrosshairMixin):
    def __init__(self, crosshair_state: CrosshairState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._crosshair_state = crosshair_state
        self._dataset: ChartDataset | None = None
        self._viewport = ViewportState(0, 0)
        self._transform: CoordTransform | None = None
        self.setMinimumHeight(60)
        self._connect_crosshair()

    def set_dataset(self, dataset: ChartDataset) -> None:
        self._dataset = dataset
        self._rebuild_transform()
        self.update()

    def set_viewport(self, vp: ViewportState) -> None:
        self._viewport = vp
        self._rebuild_transform()
        self.update()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        self._rebuild_transform()
        super().resizeEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        t = self._transform
        if t is None:
            return
        bar_index = t.pixel_to_bar(event.position().x())
        value = t.pixel_to_value(event.position().y())
        self._crosshair_state.update_from_mouse(bar_index, value)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._crosshair_state.hide()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#131722"))
        if self._dataset is None or self._transform is None or self._dataset.macd is None:
            painter.drawText(10, 20, "MACD")
            painter.end()
            return
        self._draw_macd(painter)
        self._draw_crosshair(painter)
        painter.end()

    def _draw_macd(self, painter: QPainter) -> None:
        t = self._transform
        macd = self._dataset.macd  # type: ignore[union-attr]
        if t is None or macd is None:
            return

        bw = t.bar_width
        body_w = max(1.0, bw * 0.65)
        zero_y = int(t.value_to_pixel_y(0.0))

        for i in range(t.first_bar, min(t.last_bar, len(macd.histogram))):
            h_val = macd.histogram[i]
            if h_val is None:
                continue
            cx = int(t.bar_to_pixel_x(i))
            bar_y = int(t.value_to_pixel_y(h_val))
            color = QColor("#26A69A") if h_val >= 0 else QColor("#EF5350")
            top_y = min(zero_y, bar_y)
            bot_y = max(zero_y, bar_y)
            painter.fillRect(int(cx - body_w / 2), top_y, int(body_w), max(1, bot_y - top_y), color)

        painter.setPen(QPen(QColor(80, 80, 90), 1))
        painter.drawLine(t.chart_left, zero_y, t.chart_right, zero_y)

        self._draw_value_line(painter, macd.macd_line, QColor("#FFFFFF"))
        self._draw_value_line(painter, macd.signal_line, QColor("#FF8C00"))

        painter.setPen(QColor(130, 130, 140))
        painter.drawText(t.chart_left + 4, t.chart_top + 14, "MACD(12,26,9)")

    def _rebuild_transform(self) -> None:
        if self._dataset is None or self._dataset.macd is None:
            self._transform = None
            return
        vp = self._viewport
        macd = self._dataset.macd
        first = max(0, vp.first_bar)
        last = min(len(self._dataset.bars), vp.last_bar)
        if first >= last:
            self._transform = None
            return

        # Single-pass min/max over all three series using itertools.chain
        extreme = 0.0
        for v in itertools.chain(
            macd.histogram[first:last],
            macd.macd_line[first:last],
            macd.signal_line[first:last],
        ):
            if v is not None:
                extreme = max(extreme, abs(v))
        if extreme == 0.0:
            self._transform = None
            return
        extreme *= 1.1

        self._transform = CoordTransform(
            rect=self.rect(),
            first_bar=first,
            last_bar=last,
            y_min=-extreme,
            y_max=extreme,
            margin_left=MARGIN_LEFT,
            margin_right=MARGIN_RIGHT,
            margin_top=MARGIN_TOP,
            margin_bottom=MARGIN_BOTTOM,
        )


class KDWidget(QWidget, CrosshairMixin):
    def __init__(self, crosshair_state: CrosshairState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._crosshair_state = crosshair_state
        self._dataset: ChartDataset | None = None
        self._viewport = ViewportState(0, 0)
        self._transform: CoordTransform | None = None
        self.setMinimumHeight(60)
        self._connect_crosshair()

    def set_dataset(self, dataset: ChartDataset) -> None:
        self._dataset = dataset
        self._rebuild_transform()
        self.update()

    def set_viewport(self, vp: ViewportState) -> None:
        self._viewport = vp
        self._rebuild_transform()
        self.update()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        self._rebuild_transform()
        super().resizeEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        t = self._transform
        if t is None:
            return
        bar_index = t.pixel_to_bar(event.position().x())
        value = t.pixel_to_value(event.position().y())
        self._crosshair_state.update_from_mouse(bar_index, value)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._crosshair_state.hide()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#131722"))
        if self._dataset is None or self._transform is None or self._dataset.kd is None:
            painter.drawText(10, 20, "KD")
            painter.end()
            return
        self._draw_kd(painter)
        self._draw_crosshair(painter)
        painter.end()

    def _draw_kd(self, painter: QPainter) -> None:
        t = self._transform
        kd = self._dataset.kd  # type: ignore[union-attr]
        if t is None or kd is None:
            return

        ref_pen = QPen(QColor(80, 80, 90), 1)
        ref_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(ref_pen)
        for ref in (80.0, 20.0):
            py = int(t.value_to_pixel_y(ref))
            if t.chart_top <= py <= t.chart_bottom:
                painter.drawLine(t.chart_left, py, t.chart_right, py)

        self._draw_value_line(painter, kd.k_line, QColor("#FFD700"))
        self._draw_value_line(painter, kd.d_line, QColor("#9370DB"))

        painter.setPen(QColor(130, 130, 140))
        painter.drawText(t.chart_left + 4, t.chart_top + 14, f"KD({kd.period})")

    def _rebuild_transform(self) -> None:
        if self._dataset is None or self._dataset.kd is None:
            self._transform = None
            return
        vp = self._viewport
        first = max(0, vp.first_bar)
        last = min(len(self._dataset.bars), vp.last_bar)
        if first >= last:
            self._transform = None
            return
        self._transform = CoordTransform(
            rect=self.rect(),
            first_bar=first,
            last_bar=last,
            y_min=0.0,
            y_max=100.0,
            margin_left=MARGIN_LEFT,
            margin_right=MARGIN_RIGHT,
            margin_top=MARGIN_TOP,
            margin_bottom=MARGIN_BOTTOM,
        )
