"""Small native Qt visuals shared by the launcher and agent screens."""
import math

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class AgentAvatar(QWidget):
    """Minimal black orb avatar with a quiet animated activity ring."""

    def __init__(self, size=56, parent=None):
        super().__init__(parent)
        self._working = False
        self._phase = 0.0
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_working(self, working):
        self._working = bool(working)
        self.update()

    def _tick(self):
        if self._working:
            self._phase = (self._phase + 5.0) % 360.0
            self.update()

    def paintEvent(self, event):
        side = min(self.width(), self.height())
        center = side / 2
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        ring_color = QColor("#a24f49") if self._working else QColor("#a9b0aa")
        painter.setPen(QPen(ring_color, max(1.5, side * 0.025)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inset = side * 0.07
        painter.drawEllipse(int(inset), int(inset), int(side - 2 * inset), int(side - 2 * inset))

        if self._working:
            angle = math.radians(self._phase)
            orbit = side * 0.43
            dot = side * 0.055
            x = center + math.cos(angle) * orbit - dot / 2
            y = center + math.sin(angle) * orbit - dot / 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#c86a60"))
            painter.drawEllipse(int(x), int(y), int(dot), int(dot))

        orb = side * 0.68
        gradient = QRadialGradient(center - orb * 0.20, center - orb * 0.25, orb)
        gradient.setColorAt(0, QColor("#252726"))
        gradient.setColorAt(0.72, QColor("#101111"))
        gradient.setColorAt(1, QColor("#050606"))
        painter.setPen(QPen(QColor("#343735"), max(1, side * 0.018)))
        painter.setBrush(gradient)
        painter.drawEllipse(int((side - orb) / 2), int((side - orb) / 2), int(orb), int(orb))

        eye_y = center - side * 0.025
        eye_gap = side * 0.12
        eye = max(2.2, side * 0.035)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#d8dad5"))
        painter.drawEllipse(int(center - eye_gap - eye / 2), int(eye_y), int(eye), int(eye))
        painter.drawEllipse(int(center + eye_gap - eye / 2), int(eye_y), int(eye), int(eye))
        painter.setPen(QPen(QColor("#858984"), max(1, side * 0.018), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(int(center - side * 0.07), int(center + side * 0.11),
                         int(center + side * 0.07), int(center + side * 0.11))
