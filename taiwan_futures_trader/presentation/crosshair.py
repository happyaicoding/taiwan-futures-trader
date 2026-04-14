"""Shared crosshair state and mixin for synchronized cross-chart crosshair."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen


class CrosshairState(QObject):
    """Singleton-like shared state broadcast to all chart widgets."""

    position_changed = pyqtSignal(float, float)  # (bar_index_float, value)
    hidden = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.bar_index: float = -1.0
        self.value: float = 0.0
        self.visible: bool = False

    def update_from_mouse(self, bar_index: float, value: float) -> None:
        self.bar_index = bar_index
        self.value = value
        self.visible = True
        self.position_changed.emit(bar_index, value)

    def hide(self) -> None:
        self.visible = False
        self.hidden.emit()


class CoordTransform:
    """Converts between data coordinates and pixel coordinates."""

    def __init__(
        self,
        rect: QRect,
        first_bar: int,
        last_bar: int,
        y_min: float,
        y_max: float,
        margin_left: int = 0,
        margin_right: int = 60,
        margin_top: int = 10,
        margin_bottom: int = 20,
    ) -> None:
        self.rect = rect
        self.first_bar = first_bar
        self.last_bar = last_bar
        self.y_min = y_min
        self.y_max = y_max
        self.margin_left = margin_left
        self.margin_right = margin_right
        self.margin_top = margin_top
        self.margin_bottom = margin_bottom

        self.chart_left = rect.left() + margin_left
        self.chart_right = rect.right() - margin_right
        self.chart_top = rect.top() + margin_top
        self.chart_bottom = rect.bottom() - margin_bottom
        self.chart_width = max(1, self.chart_right - self.chart_left)
        self.chart_height = max(1, self.chart_bottom - self.chart_top)

    def bar_to_pixel_x(self, bar_index: float) -> float:
        span = max(1, self.last_bar - self.first_bar)
        return self.chart_left + (bar_index - self.first_bar) / span * self.chart_width

    def pixel_to_bar(self, px: float) -> float:
        span = max(1, self.last_bar - self.first_bar)
        return self.first_bar + (px - self.chart_left) / self.chart_width * span

    def value_to_pixel_y(self, value: float) -> float:
        span = max(1e-10, self.y_max - self.y_min)
        return self.chart_bottom - (value - self.y_min) / span * self.chart_height

    def pixel_to_value(self, py: float) -> float:
        span = max(1e-10, self.y_max - self.y_min)
        return self.y_min + (self.chart_bottom - py) / self.chart_height * span

    @property
    def bar_width(self) -> float:
        span = max(1, self.last_bar - self.first_bar)
        return max(1.0, self.chart_width / span)


def draw_label_box(
    painter: QPainter,
    text: str,
    x: int,
    y: int,
    align_right: bool = False,
) -> None:
    """Draw a small label box at (x, y) for axis value labels."""
    fm = painter.fontMetrics()
    tw = fm.horizontalAdvance(text) + 8
    th = fm.height() + 4
    if align_right:
        bx = x - tw
    else:
        bx = x
    by = y - th // 2
    painter.fillRect(bx, by, tw, th, QColor(30, 34, 45, 210))
    painter.setPen(QColor(200, 200, 200))
    painter.drawText(bx + 4, by + th - 5, text)


class CrosshairMixin:
    """Mixin for chart QWidgets. Requires self._crosshair_state and self._transform."""

    _crosshair_state: CrosshairState
    _transform: CoordTransform | None

    def _connect_crosshair(self) -> None:
        self._crosshair_state.position_changed.connect(self._on_crosshair_changed)
        self._crosshair_state.hidden.connect(self._on_crosshair_hidden)
        self.setMouseTracking(True)  # type: ignore[attr-defined]

    def _on_crosshair_changed(self, bar_index: float, value: float) -> None:
        self.update()  # type: ignore[attr-defined]

    def _on_crosshair_hidden(self) -> None:
        self.update()  # type: ignore[attr-defined]

    def _draw_crosshair(self, painter: QPainter, label_text: str = "") -> None:
        if not self._crosshair_state.visible:
            return
        self._draw_crosshair_with_value(
            painter, self._crosshair_state.value, label_text
        )

    def _draw_crosshair_with_value(
        self, painter: QPainter, y_value: float, label_text: str = ""
    ) -> None:
        """Draw crosshair using an explicit y_value instead of shared state.value.
        Use this when the widget has its own y-scale (e.g. volume) so we don't
        need to mutate the shared CrosshairState.
        """
        state = self._crosshair_state
        t = self._transform
        if not state.visible or t is None:
            return

        px = int(t.bar_to_pixel_x(state.bar_index))
        if px < t.chart_left or px > t.chart_right:
            return

        pen = QPen(QColor(180, 180, 180, 120))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(1)
        painter.setPen(pen)

        painter.drawLine(px, t.chart_top, px, t.chart_bottom)

        py = int(t.value_to_pixel_y(y_value))
        if t.chart_top <= py <= t.chart_bottom:
            painter.drawLine(t.chart_left, py, t.chart_right, py)
            if label_text:
                draw_label_box(painter, label_text, t.chart_right + 2, py)

    def _draw_value_line(
        self, painter: QPainter, values: list, color: QColor
    ) -> None:
        """Draw a polyline over bars from values list. Skips None entries."""
        t = self._transform
        if t is None:
            return
        from PyQt6.QtGui import QPen
        painter.setPen(QPen(color, 1))
        prev = None
        for i in range(t.first_bar, min(t.last_bar, len(values))):
            v = values[i]
            if v is None:
                prev = None
                continue
            px = int(t.bar_to_pixel_x(i))
            py = int(t.value_to_pixel_y(v))
            if prev is not None:
                painter.drawLine(prev[0], prev[1], px, py)
            prev = (px, py)
