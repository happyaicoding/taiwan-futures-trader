"""QPainter-based candlestick chart with MA overlays, zoom, and pan."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen, QWheelEvent
from PyQt6.QtWidgets import QWidget

from taiwan_futures_trader.domain.models import ChartDataset, ViewportState
from taiwan_futures_trader.presentation.crosshair import (
    CoordTransform,
    CrosshairMixin,
    CrosshairState,
    draw_label_box,
)

# MA line colors keyed by period
MA_COLORS: dict[int, QColor] = {
    5:  QColor("#FFD700"),   # yellow
    10: QColor("#00BFFF"),   # cyan
    20: QColor("#FF8C00"),   # orange
    60: QColor("#9370DB"),   # purple
}

BULL_COLOR  = QColor("#EF5350")  # close >= open → 紅（漲，台灣慣例）
BEAR_COLOR  = QColor("#26A69A")  # close <  open → 綠（跌，台灣慣例）
WICK_COLOR  = QColor("#9E9E9E")

MARGIN_LEFT   = 0
MARGIN_RIGHT  = 65
MARGIN_TOP    = 15
MARGIN_BOTTOM = 25

DEFAULT_VISIBLE_BARS = 120
MIN_VISIBLE_BARS = 10


class CandlestickWidget(QWidget, CrosshairMixin):
    viewport_changed = pyqtSignal(object)  # ViewportState

    def __init__(self, crosshair_state: CrosshairState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._crosshair_state = crosshair_state
        self._dataset: ChartDataset | None = None
        self._viewport = ViewportState(0, 0)
        self._transform: CoordTransform | None = None
        self._drag_start: QPoint | None = None
        self._drag_first_bar: int = 0
        self.setMinimumHeight(200)
        self._connect_crosshair()

    # ------------------------------------------------------------------ slots
    def set_dataset(self, dataset: ChartDataset) -> None:
        self._dataset = dataset
        n = len(dataset)
        first = max(0, n - DEFAULT_VISIBLE_BARS)
        self._viewport = ViewportState(first, n)
        self._rebuild_transform()
        self.viewport_changed.emit(ViewportState(self._viewport.first_bar, self._viewport.last_bar))
        self.update()

    def set_viewport(self, vp: ViewportState) -> None:
        self._viewport = vp
        self._rebuild_transform()
        self.update()

    # --------------------------------------------------------- event handlers
    def resizeEvent(self, event) -> None:  # type: ignore[override]
        self._rebuild_transform()
        super().resizeEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._dataset is None:
            return
        n = len(self._dataset)
        vp = self._viewport
        visible = vp.last_bar - vp.first_bar
        delta = event.angleDelta().y()
        zoom_in = delta > 0

        change = max(1, visible // 8)
        if zoom_in:
            new_visible = max(MIN_VISIBLE_BARS, visible - change)
        else:
            new_visible = min(n, visible + change)

        # Keep the bar under the cursor stationary
        t = self._transform
        if t is not None:
            mx = event.position().x()
            ratio = (mx - t.chart_left) / max(1, t.chart_width)
        else:
            ratio = 0.5

        new_first = int(vp.last_bar - new_visible - ratio * (new_visible - visible))
        new_first = max(0, min(n - new_visible, new_first))
        new_last = new_first + new_visible

        self._viewport = ViewportState(new_first, new_last)
        self._rebuild_transform()
        self.viewport_changed.emit(ViewportState(new_first, new_last))
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
            self._drag_first_bar = self._viewport.first_bar

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        t = self._transform
        if t is None or self._dataset is None:
            return

        px = event.position().x()
        py = event.position().y()

        if self._drag_start is not None:
            dx = px - self._drag_start.x()
            span = max(1, self._viewport.last_bar - self._viewport.first_bar)
            bar_delta = int(-dx / t.chart_width * span)
            n = len(self._dataset)
            new_first = max(0, min(n - span, self._drag_first_bar + bar_delta))
            new_last = new_first + span
            self._viewport = ViewportState(new_first, new_last)
            self._rebuild_transform()
            self.viewport_changed.emit(ViewportState(new_first, new_last))
            self.update()

        bar_index = t.pixel_to_bar(px)
        value = t.pixel_to_value(py)
        self._crosshair_state.update_from_mouse(bar_index, value)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start = None

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._crosshair_state.hide()

    # --------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._draw_background(painter)
        if self._dataset is None or self._transform is None:
            painter.end()
            return
        self._draw_grid(painter)
        self._draw_candles(painter)
        self._draw_ma_lines(painter)
        self._draw_y_axis(painter)
        self._draw_x_axis(painter)
        self._draw_ohlc_info_bar(painter)
        t = self._transform
        state = self._crosshair_state
        label = f"{state.value:,.0f}" if state.visible else ""
        self._draw_crosshair(painter, label)
        painter.end()

    def _draw_background(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), QColor("#131722"))

    def _draw_grid(self, painter: QPainter) -> None:
        t = self._transform
        if t is None:
            return
        pen = QPen(QColor(42, 46, 57))
        pen.setWidth(1)
        painter.setPen(pen)
        # Horizontal grid lines (5 lines)
        for i in range(1, 6):
            y = int(t.chart_top + i * t.chart_height / 6)
            painter.drawLine(t.chart_left, y, t.chart_right, y)

    def _draw_candles(self, painter: QPainter) -> None:
        t = self._transform
        ds = self._dataset
        if t is None or ds is None:
            return

        bw = t.bar_width
        body_w = max(1.0, bw * 0.65)
        half_body = body_w / 2
        span = max(1, t.last_bar - t.first_bar)
        x_scale = t.chart_width / span

        for i in range(t.first_bar, min(t.last_bar, len(ds.bars))):
            bar = ds.bars[i]
            cx = t.bar_to_pixel_x(i)

            # Wick
            wick_x = int(cx)
            wick_top = int(t.value_to_pixel_y(bar.high))
            wick_bot = int(t.value_to_pixel_y(bar.low))
            painter.setPen(QPen(WICK_COLOR, 1))
            painter.drawLine(wick_x, wick_top, wick_x, wick_bot)

            # Body
            color = BULL_COLOR if bar.is_bullish else BEAR_COLOR
            painter.setPen(QPen(color, 1))
            painter.setBrush(color)
            body_top = int(t.value_to_pixel_y(max(bar.open, bar.close)))
            body_bot = int(t.value_to_pixel_y(min(bar.open, bar.close)))
            body_h = max(1, body_bot - body_top)
            painter.drawRect(
                int(cx - half_body), body_top,
                int(body_w), body_h,
            )
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_ma_lines(self, painter: QPainter) -> None:
        t = self._transform
        ds = self._dataset
        if t is None or ds is None:
            return

        for ma in ds.ma_results:
            if not ma.visible:
                continue
            color = MA_COLORS.get(ma.period, QColor("#FFFFFF"))
            pen = QPen(color, 1)
            painter.setPen(pen)
            prev_pt = None
            for i in range(t.first_bar, min(t.last_bar, len(ma.values))):
                v = ma.values[i]
                if v is None:
                    prev_pt = None
                    continue
                px = int(t.bar_to_pixel_x(i))
                py = int(t.value_to_pixel_y(v))
                if prev_pt is not None:
                    painter.drawLine(prev_pt[0], prev_pt[1], px, py)
                prev_pt = (px, py)

    def _draw_y_axis(self, painter: QPainter) -> None:
        t = self._transform
        if t is None:
            return
        painter.setPen(QColor(130, 130, 140))
        steps = 6
        for i in range(steps + 1):
            v = t.y_min + (t.y_max - t.y_min) * i / steps
            py = int(t.value_to_pixel_y(v))
            if t.chart_top <= py <= t.chart_bottom:
                painter.drawText(t.chart_right + 4, py + 4, f"{v:,.0f}")

    def _draw_x_axis(self, painter: QPainter) -> None:
        t = self._transform
        ds = self._dataset
        if t is None or ds is None:
            return
        painter.setPen(QColor(130, 130, 140))
        n_labels = 6
        span = t.last_bar - t.first_bar
        step = max(1, span // n_labels)
        for i in range(t.first_bar, min(t.last_bar, len(ds.bars)), step):
            ts = ds.bars[i].timestamp
            label = ts.strftime("%m/%d %H:%M")
            px = int(t.bar_to_pixel_x(i))
            painter.drawText(px - 30, t.chart_bottom + 18, label)

    def _draw_ohlc_info_bar(self, painter: QPainter) -> None:
        """Show O/H/L/C, volume and timestamp of the bar under the crosshair."""
        ds = self._dataset
        t = self._transform
        state = self._crosshair_state
        if not state.visible or ds is None or t is None:
            return
        bar_idx = int(round(state.bar_index))
        if not (0 <= bar_idx < len(ds.bars)):
            return
        bar = ds.bars[bar_idx]

        ts_str = bar.timestamp.strftime("%Y-%m-%d %H:%M")
        change = bar.close - bar.open
        pct = change / bar.open * 100 if bar.open else 0.0
        sign = "+" if change >= 0 else ""
        info = (
            f"{ts_str}    "
            f"開 {bar.open:,.0f}    高 {bar.high:,.0f}    "
            f"低 {bar.low:,.0f}    收 {bar.close:,.0f}    "
            f"漲跌 {sign}{change:,.0f} ({sign}{pct:.2f}%)    "
            f"量 {bar.volume:,d}"
        )

        color = BULL_COLOR if bar.is_bullish else BEAR_COLOR
        painter.setPen(color)
        painter.drawText(t.chart_left + 4, t.chart_top - 2, info)

    # --------------------------------------------------------------- helpers
    def _rebuild_transform(self) -> None:
        if self._dataset is None:
            self._transform = None
            return
        ds = self._dataset
        vp = self._viewport
        first = max(0, vp.first_bar)
        last = min(len(ds.bars), vp.last_bar)

        if first >= last:
            self._transform = None
            return

        visible_bars = ds.bars[first:last]
        y_min = min(b.low for b in visible_bars) * 0.999
        y_max = max(b.high for b in visible_bars) * 1.001

        self._transform = CoordTransform(
            rect=self.rect(),
            first_bar=first,
            last_bar=last,
            y_min=y_min,
            y_max=y_max,
            margin_left=MARGIN_LEFT,
            margin_right=MARGIN_RIGHT,
            margin_top=MARGIN_TOP,
            margin_bottom=MARGIN_BOTTOM,
        )
