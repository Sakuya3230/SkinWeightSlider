# -*- coding: utf-8 -*-
"""
パネルの部品 (Qt だけ。Maya を使わない)。

    RowWidget   1 つのインフルエンスの行: 鍵 | 色 | 名前 | バー | 数値
    BarWidget   平均のバー (押す・動かすと 0〜1 の値を出す。下の細い線は頂点ごとの最小〜最大)
    ValueEdit   数値の欄 (押すと入力。Enter で決定、Esc で取り消し)
    GripWidget  パネルを動かすつまみ
    IconButton  鍵・戻すボタン (記号は QPainter で描く。フォントに無い記号に頼らない)

どの部品もキーボードのフォーカスを取らない (数値の欄だけクリックで取る)。Maya のホットキーが
そのまま効くようにするため。マウスのイベントは受け取って消費し、ビュー (選択・カメラ) へ抜けさせない。
"""
from .qt import QtCore, QtGui, QtWidgets, event_pos, global_pos, text_width

__all__ = ["Colors", "ROW_HEIGHT", "NAME_WIDTH", "BAR_WIDTH", "BAR_MIN_WIDTH", "RowWidget", "BarWidget", "ValueEdit",
           "GripWidget", "IconButton", "value_width"]

ROW_HEIGHT = 22
NAME_WIDTH = 104
BAR_WIDTH = 140      # バーの幅の目安 (既定の大きさのパネルで)
BAR_MIN_WIDTH = 60   # パネルを狭めたときのバーの最小の幅
LOCK_WIDTH = 18
SWATCH_WIDTH = 12


class Colors(object):
    """パネルの色 (Qt の色はそのまま画面に出る。カラーマネジメントの変換は無い)。"""
    BACKGROUND = QtGui.QColor(38, 38, 38)
    BORDER = QtGui.QColor(90, 90, 90)
    ROW_HOVER = QtGui.QColor(62, 62, 62)
    ROW_ACTIVE = QtGui.QColor(84, 78, 52)
    ROW_PARTNER = QtGui.QColor(48, 76, 92)
    TRACK = QtGui.QColor(72, 72, 72)
    TRACK_HOVER = QtGui.QColor(86, 86, 86)
    FILL = QtGui.QColor(69, 153, 242)
    FILL_LOCKED = QtGui.QColor(140, 140, 140)
    RANGE = QtGui.QColor(160, 160, 160)
    PREVIEW = QtGui.QColor(255, 217, 77)
    TEXT = QtGui.QColor(235, 235, 235)
    TEXT_DIM = QtGui.QColor(150, 150, 150)
    LOCK_ON = QtGui.QColor(245, 190, 60)
    LOCK_OFF = QtGui.QColor(120, 120, 120)


def value_width(metrics, decimals):
    """数値の欄の幅 (「0.000」を桁数どおりに測る。桁を増やしてもバーと重ならない)。"""
    return text_width(metrics, "=0." + "0" * int(decimals)) + 10


def _modifiers():
    modifiers = QtWidgets.QApplication.keyboardModifiers()
    return bool(modifiers & QtCore.Qt.ControlModifier), bool(modifiers & QtCore.Qt.ShiftModifier)


class BarWidget(QtWidgets.QWidget):
    """平均のバー。press / move / release をシグナルで知らせる (値の計算・刻みはセッション)。

    pressed(値, Ctrl, Shift) / moved(値, Ctrl, Shift, 押した位置からの横の距離) / released()
    """

    pressed = QtCore.Signal(float, bool, bool)
    moved = QtCore.Signal(float, bool, bool, int)
    released = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setMouseTracking(True)
        self.setMinimumWidth(BAR_MIN_WIDTH)   # パネルの幅に合わせて伸びる
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self._values = (0.0, 0.0, 0.0)
        self._locked = False
        self._preview = None
        self._hover = False
        self._press_x = None

    def setValues(self, average, minimum, maximum, locked, preview=None):
        self._values = (average, minimum, maximum)
        self._locked = locked
        self._preview = preview
        self.update()

    def isDragging(self):
        return self._press_x is not None

    def track(self):
        return QtCore.QRectF(self.rect()).adjusted(2, 4, -2, -7)

    def valueAt(self, x):
        track = self.track()
        return (x - track.left()) / max(track.width(), 1.0)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        track = self.track()
        average, minimum, maximum = self._values
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(Colors.TRACK_HOVER if self._hover else Colors.TRACK)
        painter.drawRoundedRect(track, 2, 2)
        if average > 0.0:
            fill = QtCore.QRectF(track)
            fill.setWidth(track.width() * min(max(average, 0.0), 1.0))
            painter.setBrush(Colors.FILL_LOCKED if self._locked else Colors.FILL)
            painter.drawRoundedRect(fill, 2, 2)
        if maximum > minimum:   # 頂点ごとの最小〜最大 (バーのすぐ下の細い線)
            y = track.bottom() + 3
            painter.setPen(QtGui.QPen(Colors.RANGE, 2))
            painter.drawLine(QtCore.QPointF(track.left() + track.width() * minimum, y),
                             QtCore.QPointF(track.left() + track.width() * maximum, y))
        if self._preview is not None:   # ドラッグ中のマウスの位置の値
            x = track.left() + track.width() * min(max(self._preview, 0.0), 1.0)
            painter.setPen(QtGui.QPen(Colors.PREVIEW, 2))
            painter.drawLine(QtCore.QPointF(x, track.top() - 3), QtCore.QPointF(x, track.bottom() + 3))
        painter.end()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.LeftButton and self._press_x is None:
            x = event_pos(event).x()
            self._press_x = x
            ctrl, shift = _modifiers()
            self.pressed.emit(self.valueAt(x), ctrl, shift)

    def mouseMoveEvent(self, event):
        event.accept()
        if self._press_x is not None:
            x = event_pos(event).x()
            ctrl, shift = _modifiers()
            self.moved.emit(self.valueAt(x), ctrl, shift, abs(x - self._press_x))

    def mouseReleaseEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.LeftButton and self._press_x is not None:
            self._press_x = None
            self.released.emit()

    def mouseDoubleClickEvent(self, event):
        event.accept()


class ValueEdit(QtWidgets.QLineEdit):
    """数値の欄。ふだんは平均を出し、押すと入力の文字 (「×1.0」など) にして全部を選ぶ。

    Enter で entered(文字) を出す。Esc・フォーカスが外れたら元に戻す。どちらも finished を出す
    (パネルがキーボードのフォーカスをビューへ返す)。
    """

    entered = QtCore.Signal(str)
    finished = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.setFrame(False)
        self._shown = ""
        self._edit_text = ""
        self.returnPressed.connect(self._accept)

    def setShown(self, text, edit_text):
        """ふだん出す文字と、押したときの文字。入力中は書き換えない。"""
        self._shown = text
        self._edit_text = edit_text
        if not self.hasFocus():
            self.setText(text)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.setText(self._edit_text)
        QtCore.QTimer.singleShot(0, self.selectAll)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setText(self._shown)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.setText(self._shown)
            self.clearFocus()
            self.finished.emit()
            return
        super().keyPressEvent(event)

    def _accept(self):
        text = self.text()
        self.clearFocus()
        self.finished.emit()
        self.entered.emit(text)


class IconButton(QtWidgets.QAbstractButton):
    """記号を QPainter で描く小さなボタン (kind は "lock" / "reset")。"""

    def __init__(self, kind, size=18, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setFixedSize(size, size)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._hover = False
        self.active = False   # 鍵: ロック中 / 戻す: 動かしている

    def setActive(self, active):
        if self.active != active:
            self.active = active
            self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        if self._hover:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(Colors.ROW_HOVER.lighter(130))
            painter.drawRoundedRect(QtCore.QRectF(self.rect()), 3, 3)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        if self.kind == "lock":
            color = Colors.LOCK_ON if self.active else Colors.LOCK_OFF
            painter.setPen(QtGui.QPen(color, 1.6))
            painter.setBrush(QtCore.Qt.NoBrush)
            path = QtGui.QPainterPath()   # つる (閉じていれば両足が本体に入る。開いていれば右足が浮く)
            path.moveTo(cx - 3, cy)
            path.lineTo(cx - 3, cy - 2.5)
            path.arcTo(cx - 3, cy - 5.5, 6, 6, 180, -180)
            path.lineTo(cx + 3, cy if self.active else cy - 2)
            painter.drawPath(path)
            painter.fillRect(QtCore.QRectF(cx - 4.5, cy, 9, 6), color)
        else:   # reset: 反時計回りの丸い矢印
            color = Colors.TEXT if self.active else Colors.TEXT_DIM
            painter.setPen(QtGui.QPen(color, 1.5))
            rect = QtCore.QRectF(cx - 5, cy - 5, 10, 10)
            painter.drawArc(rect, 60 * 16, 270 * 16)
            tip = QtCore.QPointF(cx + 2.5, cy - 4.3)
            painter.drawLine(tip, tip + QtCore.QPointF(-3.5, -1.0))
            painter.drawLine(tip, tip + QtCore.QPointF(-0.5, 3.5))
        painter.end()


class GripWidget(QtWidgets.QWidget):
    """パネルを動かすつまみ。dragged(押した位置からの移動量 QPoint) / dragFinished()。"""

    dragged = QtCore.Signal(QtCore.QPoint)
    dragFinished = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 20)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setCursor(QtCore.Qt.SizeAllCursor)
        self.setToolTip("ドラッグでパネルを動かす")
        self._press = None

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(Colors.TEXT if self._press is not None else Colors.TEXT_DIM)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        for dx in (-2.5, 2.5):
            for dy in (-5, 0, 5):
                painter.drawEllipse(QtCore.QPointF(cx + dx, cy + dy), 1.2, 1.2)
        painter.end()

    def mousePressEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.LeftButton:
            self._press = global_pos(event)
            self.update()

    def mouseMoveEvent(self, event):
        event.accept()
        if self._press is not None:
            self.dragged.emit(global_pos(event) - self._press)

    def mouseReleaseEvent(self, event):
        event.accept()
        if self._press is not None and event.button() == QtCore.Qt.LeftButton:
            self._press = None
            self.update()
            self.dragFinished.emit()


class _Swatch(QtWidgets.QWidget):
    """インフルエンスの色の四角 (色が無ければ何も描かない)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(SWATCH_WIDTH, ROW_HEIGHT)
        self.color = None

    def paintEvent(self, event):
        if self.color is None:
            return
        painter = QtGui.QPainter(self)
        painter.fillRect(QtCore.QRectF(1, self.height() / 2.0 - 5, 10, 10), self.color)
        painter.end()


class RowWidget(QtWidgets.QWidget):
    """1 つのインフルエンスの行。hovered(番号, 乗ったか) で乗せた行を、menuRequested(番号, 画面の位置) で
    右クリックを知らせる。"""

    hovered = QtCore.Signal(int, bool)
    menuRequested = QtCore.Signal(int, QtCore.QPoint)

    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.setFixedHeight(ROW_HEIGHT)
        self.setMouseTracking(True)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 4, 0)
        layout.setSpacing(3)
        self.lock = IconButton("lock", 18, self)
        self.swatch = _Swatch(self)
        self.name = QtWidgets.QLabel(self)
        self.name.setFixedWidth(NAME_WIDTH)
        self.bar = BarWidget(self)
        self.value = ValueEdit(self)
        for widget in (self.lock, self.swatch, self.name):
            layout.addWidget(widget)
        layout.addWidget(self.bar, 1)
        layout.addWidget(self.value)
        self._background = None
        self._text_color = None
        self.state = None

    def setRow(self, row, decimals, elide_front, show_swatch):
        """RowState を出す。"""
        self.state = row
        metrics = self.name.fontMetrics()
        mode = QtCore.Qt.ElideLeft if elide_front else QtCore.Qt.ElideRight
        self.name.setText(metrics.elidedText(row.name, mode, NAME_WIDTH))
        fmt = "{:.%df}" % decimals
        self.setToolTip("{}\n{}\n平均 {}  最小 {}  最大 {}".format(
            row.name, row.key, fmt.format(row.average), fmt.format(row.minimum),
            fmt.format(row.maximum)))
        self.lock.setActive(row.locked)
        self.lock.setToolTip("ロックを解除する" if row.locked else "ロックする")
        self.swatch.color = QtGui.QColor.fromRgbF(*row.color) if row.color else None
        self.swatch.setVisible(show_swatch)
        self.swatch.update()
        self.bar.setValues(row.average, row.minimum, row.maximum, row.locked, row.preview)
        self.value.setFixedWidth(value_width(metrics, decimals))
        self.value.setShown(fmt.format(row.average), row.edit_text)
        # 文字の色はスタイルシートで (Maya のスタイルシートがパレットより強いことがあるため)
        color = Colors.PREVIEW if row.active else (Colors.TEXT_DIM if row.locked else Colors.TEXT)
        if color.name() != self._text_color:
            self._text_color = color.name()
            self.name.setStyleSheet("QLabel {{ color: {}; background: transparent; }}".format(color.name()))
            self.value.setStyleSheet(
                "QLineEdit {{ color: {}; background: transparent; border: none; }}"
                "QLineEdit:focus {{ color: #ebebeb; background: #1c1c1c; }}".format(color.name()))
        if row.active:
            self._background = Colors.ROW_ACTIVE
        elif row.partner:
            self._background = Colors.ROW_PARTNER
        else:
            self._background = None
        self.update()

    def paintEvent(self, event):
        color = self._background
        if color is None and self.underMouse():
            color = Colors.ROW_HOVER
        if color is not None:
            painter = QtGui.QPainter(self)
            painter.fillRect(self.rect(), color)
            painter.end()

    def enterEvent(self, event):
        self.update()
        self.hovered.emit(self.index, True)

    def leaveEvent(self, event):
        self.update()
        self.hovered.emit(self.index, False)

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def contextMenuEvent(self, event):
        event.accept()
        self.menuRequested.emit(self.index, event.globalPos())
