"""Volume bar chart, x-axis synchronized with CandlestickWidget."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from taiwan_futures_trader.domain.models import ChartDataset, ViewportState
from taiwan_futures_trader.presentation.crosshair import (
    CoordTransform,
    CrosshairMixin,
    CrosshairState,
    draw_label_box,
)

MARGIN_LEFT   = 0
MARGIN_RIGHT  = 65
MARGIN_TOP    = 5
MARGIN_BOTTOM = 20

BULL_COLOR = QColor(38, 166, 154, 160)
BEAR_COLOR = QColor(239, 83, 80, 160)


class VolumeWidget(QWidget, CrosshairMixin):
    def __init__(self, crosshair_state: CrosshairState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._crosshair_state = crosshair_state
        self._dataset: ChartDataset | None = None
        self._viewport = ViewportState(0, 0)
        self._transform: CoordTransform | None = None
        self.setMinimumHeight(60)
        self.setMaximumHeight(150)
        self._connect_crosshair()

    # ------------------------------------------------------------------ slots
    def set_dataset(self, dataset: ChartDataset) -> None:
        self._dataset = dataset
        self._rebuild_transform()
        self.update()

    def set_viewport(self, vp: ViewportState) -> None:
        self._viewport = vp
        self._rebuild_transform()
        self.update()

    # --------------------------------------------------------- event handlers
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

    # --------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#131722"))
        if self._dataset is None or self._transform is None:
            painter.end()
            return
        self._draw_volume_bars(painter)
        self._draw_volume_axis(painter)
        # Crosshair with volume label
        t = self._transform
        state = self._crosshair_state
        bar_idx = int(round(state.bar_index))
        if (
            state.visible
            and self._dataset
            and 0 <= bar_idx < len(self._dataset.bars)
        ):
            vol = self._dataset.bars[bar_idx].volume
            label = f"{vol:,d}"
            # Draw crosshair manually so we can use bar's volume for the y-line
            # without mutating the shared CrosshairState
            self._draw_crosshair_with_value(painter, vol, label)
        else:
            self._draw_crosshair(painter)
        painter.end()

    def _draw_volume_bars(self, painter: QPainter) -> None:
        t = self._transform
        ds = self._dataset
        if t is None or ds is None:
            return

        bw = t.bar_width
        body_w = max(1.0, bw * 0.65)

        for i in range(t.first_bar, min(t.last_bar, len(ds.bars))):
            bar = ds.bars[i]
            cx = t.bar_to_pixel_x(i)
            top_y = int(t.value_to_pixel_y(bar.volume))
            bot_y = t.chart_bottom
            h = max(1, bot_y - top_y)
            color = BULL_COLOR if bar.is_bullish else BEAR_COLOR
            painter.fillRect(int(cx - body_w / 2), top_y, int(body_w), h, color)

    def _draw_volume_axis(self, painter: QPainter) -> None:
        t = self._transform
        if t is None:
            return
        painter.setPen(QColor(130, 130, 140))
        # 2 labels: top and middle
        for i in (1, 2):
            v = t.y_max * i / 2
            py = int(t.value_to_pixel_y(v))
            if t.chart_top <= py <= t.chart_bottom:
                if v >= 10_000:
                    label = f"{v / 10_000:.1f}萬"
                else:
                    label = f"{int(v):,d}"
                painter.drawText(t.chart_right + 4, py + 4, label)

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
        y_max = max(b.volume for b in visible_bars) * 1.1 or 1.0

        self._transform = CoordTransform(
            rect=self.rect(),
            first_bar=first,
            last_bar=last,
            y_min=0.0,
            y_max=y_max,
            margin_left=MARGIN_LEFT,
            margin_right=MARGIN_RIGHT,
            margin_top=MARGIN_TOP,
            margin_bottom=MARGIN_BOTTOM,
        )
