# -*- coding: utf-8 -*-
"""
パネル全体 (Qt だけ)。PanelState (core/panel_state.py) を表示し、操作をシグナルで知らせる。

    panel = PanelWidget()
    panel.setState(state)
    panel.rowPressed.connect(...)    # 中身は tool/session.py が行う

    ┌──────────────────────────────────────────────┐
    │ ::  [割合] [加算] [絶対] [移動]            ↺ │  つまみ・モード・置き場所に戻す
    │ body: 頂点 12 個                             │
    │ 🔒 ■ joint1   ████████░░░░░░░░   0.488       │  鍵・色・名前・バー・数値 (スクロール)
    │ ＋ インフルエンスを足す                      │
    │ － 小さいウェイトを刈り取る (0.001 未満)     │
    │ [コピー] [ペースト (3)] [平均化]             │
    │ 注記                                         │
    └──────────────────────────────────────────────┘

塗り方 (ホストが決める):
- 不透明 (ビューの中): 描画面 (Maya が OpenGL で描く) の上の半透明は、下を Qt が描き直さないので
  前の絵が残って重なった (試作で確認)。毎回全体を不透明に塗る
- 半透明 (枠なしのウィンドウ): WA_TranslucentBackground のウィンドウで、前の絵を消してから
  角の丸い背景を不透明度 opacity で塗る。スクロールの中 (viewport) が背景を塗ると透けない
  (Maya のスタイルシート。試作で確認) ので、viewport と中身は塗らない

大きさ: パネルは中身で大きさを変えない (選択の前後で大きさが変わって見づらかった)。大きさはホストが
設定 (panelWidth / panelHeight) で決め、行は残りの高さいっぱいに並べてスクロールする。
端・角 (EDGE_PIXELS の幅) を押してドラッグすると resizeDragged(端, 押した位置からの移動量) を出し、
ホストが反対側の辺を動かさずに大きさを変える。行が入りきらない幅にはしない (minimumPanelSize)。
"""
from ..core.modes import MODE_LABELS, MODES
from ..core.placement import EDGE_BOTTOM, EDGE_LEFT, EDGE_RIGHT, EDGE_TOP, PANEL_MIN_SIZE
from .qt import QtCore, QtGui, QtWidgets, alive, event_pos, exec_menu, global_pos
from .widgets import (BAR_MIN_WIDTH, LOCK_WIDTH, NAME_WIDTH, SWATCH_WIDTH, Colors,
                      GripWidget, IconButton, RowWidget, value_width)

__all__ = ["PanelWidget", "ACTIONS", "ACTION_LABELS", "ROW_ACTIONS", "row_menu_items", "edges_at",
           "EDGE_PIXELS"]

ACTIONS = ("copy", "paste", "average", "smooth")
ACTION_LABELS = {"copy": "コピー", "paste": "ペースト", "average": "平均化", "smooth": "スムーズ"}
# スムーズのボタンの右クリックで選べる強さと回数
SMOOTH_STRENGTHS = (0.1, 0.25, 0.5, 0.75, 1.0)
SMOOTH_ITERATIONS = (1, 2, 3, 5, 10)
SMOOTH_METHOD_LABELS = (("uniform", "均等"), ("distance", "距離に応じて"), ("cotangent", "コタンジェント"))
# 行の右クリックのメニュー (名前は tool/session.WeightSession.row_action が受け取る)。None は区切り
ROW_ACTIONS = ("selectJoint", "selectAffected", None, "soloLock", "lockAll", "unlockAll", None,
               "zero", "full", "giveToPartner", "setPartner")


def row_menu_items(state, row):
    """行の右クリックのメニューの項目 [(名前, 表示, 押せるか)] (区切りは None)。Qt を使わない。"""
    items = []
    editable = not row.locked and not state.dragging
    partner = state.partner
    for action in ROW_ACTIONS:
        if action is None:
            items.append(None)
        elif action == "selectJoint":
            items.append((action, "ジョイント {} を選ぶ".format(row.name), True))
        elif action == "selectAffected":
            items.append((action, "このインフルエンスの影響を受ける頂点を選ぶ", True))
        elif action == "soloLock":
            items.append((action, "これ以外をすべてロック", True))
        elif action == "lockAll":
            items.append((action, "すべてロック", True))
        elif action == "unlockAll":
            items.append((action, "すべてロック解除", True))
        elif action == "zero":
            items.append((action, "0 にする (ほかへ配る)", editable))
        elif action == "full":
            items.append((action, "1 にする (ほかを 0 に)", editable))
        elif action == "giveToPartner":
            if partner is not None and partner != row.index:
                items.append((action, "移動の相手 {} へ全部移す".format(state.partner_name), editable))
        elif action == "setPartner":
            items.append((action, "移動の相手を外す" if partner == row.index else "移動の相手にする",
                          not state.dragging))
    return items
MARGIN = 8
EDGE_PIXELS = 6   # 端からこの距離までを押すと大きさを変える (余白の中なので部品とは重ならない)


def edges_at(rect, point, size=EDGE_PIXELS):
    """矩形 rect の中の point が、どの端・角の上か (EDGE_* の和。端でなければ 0)。"""
    edges = 0
    if point.x() < rect.left() + size:
        edges |= EDGE_LEFT
    elif point.x() > rect.right() - size:
        edges |= EDGE_RIGHT
    if point.y() < rect.top() + size:
        edges |= EDGE_TOP
    elif point.y() > rect.bottom() - size:
        edges |= EDGE_BOTTOM
    return edges


def edge_cursor(edges):
    shape = QtCore.Qt
    if edges in (EDGE_LEFT | EDGE_TOP, EDGE_RIGHT | EDGE_BOTTOM):
        return shape.SizeFDiagCursor
    if edges in (EDGE_RIGHT | EDGE_TOP, EDGE_LEFT | EDGE_BOTTOM):
        return shape.SizeBDiagCursor
    if edges in (EDGE_LEFT, EDGE_RIGHT):
        return shape.SizeHorCursor
    if edges in (EDGE_TOP, EDGE_BOTTOM):
        return shape.SizeVerCursor
    return None

_STYLE = """
QWidget#{name} QLabel {{ color: #e6e6e6; background: transparent; }}
QWidget#{name} QLabel#info, QWidget#{name} QLabel#note, QWidget#{name} QLabel#message {{ color: #a0a0a0; }}
QWidget#{name} QPushButton {{ color: #d8d8d8; background: #3a3a3a; border: none; border-radius: 3px;
    padding: 2px 6px; }}
QWidget#{name} QPushButton:hover {{ background: #4a4a4a; }}
QWidget#{name} QPushButton:checked {{ color: #ffffff; background: #4599f2; }}
QWidget#{name} QPushButton:disabled {{ color: #707070; background: #303030; }}
QWidget#{name} QPushButton#flat {{ background: transparent; color: #a0a0a0; text-align: left; padding-left: 4px; }}
QWidget#{name} QPushButton#flat:hover {{ background: #3e3e3e; color: #ebebeb; }}
QWidget#{name} QScrollArea, QWidget#{name} QScrollArea > QWidget,
QWidget#{name} QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
"""


class PanelWidget(QtWidgets.QWidget):
    """パネル。データは setState で受け取り、Maya は呼ばない。"""

    rowPressed = QtCore.Signal(int, float, bool, bool)   # 番号, 値, Ctrl, Shift
    rowMoved = QtCore.Signal(float, bool, bool, int)     # 値, Ctrl, Shift, 押した位置からの距離
    rowReleased = QtCore.Signal()
    rowHovered = QtCore.Signal(int)                      # 乗せた行の番号 (離れたら -1)
    lockClicked = QtCore.Signal(int)
    rowAction = QtCore.Signal(int, str)                  # 行の右クリックのメニュー (番号, ROW_ACTIONS の名前)
    valueEntered = QtCore.Signal(int, str)
    modeClicked = QtCore.Signal(str)
    addToggled = QtCore.Signal(str)                      # 足す / 外すインフルエンスのフルパス
    pruneClicked = QtCore.Signal()
    actionClicked = QtCore.Signal(str)                   # ACTIONS のどれか
    settingChosen = QtCore.Signal(str, object)           # 設定のキー, 値 (スムーズのボタンの右クリック)
    gripDragged = QtCore.Signal(QtCore.QPoint)
    gripFinished = QtCore.Signal()
    resetPositionClicked = QtCore.Signal()
    resizeDragged = QtCore.Signal(int, QtCore.QPoint)    # 端 (EDGE_*), 押した位置からの移動量
    resizeFinished = QtCore.Signal()
    interacted = QtCore.Signal()                         # 操作を終えた (フォーカスをビューへ返す)
    sizeChanged = QtCore.Signal()

    def __init__(self, object_name="skinWeightSliderPanel", parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setMouseTracking(True)
        self.setStyleSheet(_STYLE.format(name=object_name))
        self._opaque = True
        self._opacity = 255
        self._state = None
        self._order = None
        self._generation = None
        self._hover = -1
        self._resize = None   # 端のドラッグ中: (端, 押したときのマウスの位置)
        self._decimals = 3
        self._show_swatch = False
        self.rows = {}   # 番号 -> RowWidget
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(MARGIN, 6, MARGIN, 8)
        layout.setSpacing(4)
        # 上の段: つまみ・モード・戻す
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(4)
        self.grip = GripWidget(self)
        self.grip.dragged.connect(self.gripDragged.emit)
        self.grip.dragFinished.connect(self.gripFinished.emit)
        self.grip.dragFinished.connect(self.interacted.emit)
        header.addWidget(self.grip)
        self.mode_buttons = {}
        for number, mode in enumerate(MODES, 1):
            button = self._button("{}: {}".format(number, MODE_LABELS[mode]), checkable=True)
            button.clicked.connect(lambda checked=False, m=mode: self._clicked(self.modeClicked, m))
            header.addWidget(button, 1)
            self.mode_buttons[mode] = button
        self.reset_button = IconButton("reset", 18, self)
        self.reset_button.setToolTip("つまみで動かしたパネルを置き場所に戻す")
        self.reset_button.clicked.connect(lambda: self._clicked(self.resetPositionClicked))
        header.addWidget(self.reset_button)
        layout.addLayout(header)
        self.info = QtWidgets.QLabel(self)
        self.info.setObjectName("info")
        layout.addWidget(self.info)
        self.message = QtWidgets.QLabel(self)
        self.message.setObjectName("message")
        self.message.setWordWrap(True)
        self.message.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        layout.addWidget(self.message, 1)   # 選んでいないときは、行の代わりに残りの高さを使う
        # 行 (スクロール)
        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFocusPolicy(QtCore.Qt.NoFocus)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.container = QtWidgets.QWidget()
        self.rows_layout = QtWidgets.QVBoxLayout(self.container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(self.container)
        for widget in (self.scroll, self.scroll.viewport(), self.container):
            widget.setAutoFillBackground(False)
            widget.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        layout.addWidget(self.scroll, 1)    # 行は残りの高さいっぱい (入りきらなければスクロール)
        # 「＋」「－」
        self.add_button = self._button("＋ インフルエンスを足す", flat=True)
        self.add_button.clicked.connect(self._show_add_menu)
        layout.addWidget(self.add_button)
        self.prune_button = self._button("", flat=True)
        self.prune_button.clicked.connect(lambda: self._clicked(self.pruneClicked))
        layout.addWidget(self.prune_button)
        # コピー・ペースト・平均化
        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(4)
        self.action_buttons = {}
        for action in ACTIONS:
            button = self._button(ACTION_LABELS[action])
            button.clicked.connect(lambda checked=False, a=action: self._clicked(self.actionClicked, a))
            actions.addWidget(button, 1)
            self.action_buttons[action] = button
        smooth = self.action_buttons["smooth"]
        smooth.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        smooth.customContextMenuRequested.connect(
            lambda point: self._show_smooth_menu(smooth.mapToGlobal(point)))
        layout.addLayout(actions)
        self.note = QtWidgets.QLabel(self)
        self.note.setObjectName("note")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

    def _button(self, text, checkable=False, flat=False):
        button = QtWidgets.QPushButton(text, self)
        button.setFocusPolicy(QtCore.Qt.NoFocus)
        button.setCheckable(checkable)
        if flat:
            button.setObjectName("flat")
        return button

    def _clicked(self, signal, *args):
        signal.emit(*args)
        self.interacted.emit()

    # -- 表示 -----------------------------------------------------------------

    def state(self):
        return self._state

    def setTranslucent(self, translucent, opacity=255):
        """半透明 (枠なしのウィンドウ) か不透明 (ビューの中) かと、背景の不透明度。"""
        self._opaque = not translucent
        self._opacity = int(opacity)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, self._opaque)
        self.update()

    def setState(self, state):
        """PanelState を出す。行の並びが同じなら行を作り直さない (ドラッグ中のバー・入力中の欄を
        壊さないため)。"""
        self._state = state
        has_model = not state.message
        self.message.setText(state.message)
        self.message.setVisible(not has_model)
        self.info.setText(state.info)
        self.info.setVisible(has_model and bool(state.info))
        for mode, button in self.mode_buttons.items():
            button.setChecked(mode == state.mode)
            button.setEnabled(not state.dragging)
        self.reset_button.setActive(state.offset_moved)
        order = [row.index for row in state.rows]
        if order != self._order:
            self._rebuild(order)
        show_swatch = any(row.color is not None for row in state.rows)
        for row in state.rows:
            self.rows[row.index].setRow(row, state.decimals, state.elide_front, show_swatch)
        self.scroll.setVisible(has_model)
        if state.generation != self._generation:
            self._generation = state.generation
            self.scroll.verticalScrollBar().setValue(0)   # 選択を変えたら先頭から
        self.add_button.setVisible(has_model and bool(state.zero))
        self.prune_button.setText(state.prune_label)
        self.prune_button.setVisible(has_model)
        paste = self.action_buttons["paste"]
        paste.setText("ペースト ({})".format(state.clipboard_count) if state.clipboard_count else "ペースト")
        paste.setEnabled(has_model and state.clipboard_count > 0 and not state.dragging)
        self.action_buttons["copy"].setEnabled(has_model and not state.dragging)
        self.action_buttons["average"].setEnabled(has_model and state.can_average and not state.dragging)
        self.action_buttons["smooth"].setEnabled(has_model and not state.dragging)
        self.action_buttons["smooth"].setToolTip(
            "隣の頂点の平均へ寄せる ({}、強さ {:g} × {} 回)\n右クリックで方式・強さ・回数を変える".format(
                dict(SMOOTH_METHOD_LABELS).get(state.smooth_method, ""), state.smooth_strength,
                state.smooth_iterations))
        for button in self.action_buttons.values():
            button.setVisible(has_model)
        self.note.setText("\n".join(state.notes))
        self.note.setVisible(has_model and bool(state.notes))
        if (state.decimals, show_swatch) != (self._decimals, self._show_swatch):
            self._decimals, self._show_swatch = state.decimals, show_swatch
            self.sizeChanged.emit()   # 行が入る最小の幅が変わった (ホストが大きさを直す)

    def minimumPanelSize(self):
        """行が入る最小の大きさ (幅は桁数・色の列・スクロールバーから。設定の下限より小さくしない)。"""
        metrics = self.fontMetrics()
        row = (2 + 4 + LOCK_WIDTH + NAME_WIDTH + BAR_MIN_WIDTH + value_width(metrics, self._decimals)
               + 3 * 4 + (SWATCH_WIDTH if self._show_swatch else 0)
               + self.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent))
        return max(row + MARGIN * 2, PANEL_MIN_SIZE[0]), PANEL_MIN_SIZE[1]

    def _rebuild(self, order):
        for widget in self.rows.values():
            self.rows_layout.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
        self.rows = {}
        for position, index in enumerate(order):
            row = RowWidget(index, self.container)
            row.bar.pressed.connect(lambda value, ctrl, shift, i=index: self.rowPressed.emit(i, value, ctrl, shift))
            row.bar.moved.connect(self.rowMoved.emit)
            row.bar.released.connect(self.rowReleased.emit)
            row.bar.released.connect(self.interacted.emit)
            row.lock.clicked.connect(lambda checked=False, i=index: self._clicked(self.lockClicked, i))
            row.value.entered.connect(lambda text, i=index: self.valueEntered.emit(i, text))
            row.value.finished.connect(self.interacted.emit)
            row.hovered.connect(self._row_hovered)
            row.menuRequested.connect(self._show_row_menu)
            self.rows_layout.insertWidget(position, row)
            self.rows[index] = row
        self._order = list(order)
        if self._hover not in self.rows:
            self._set_hover(-1)

    def _row_hovered(self, index, inside):
        if inside:
            self._set_hover(index)
        elif self._hover == index:
            self._set_hover(-1)

    def _set_hover(self, index):
        if index != self._hover:
            self._hover = index
            self.rowHovered.emit(index)

    def _show_row_menu(self, index, position):
        """行の右クリックのメニュー (ロック・選択・0 / 1・移動の相手)。"""
        state = self._state
        rows = [row for row in (state.rows if state is not None else []) if row.index == index]
        if not rows:
            return
        menu = QtWidgets.QMenu(self)
        menu.setAttribute(QtCore.Qt.WA_NoMouseReplay)   # 外のクリックをビューへ送り直さない
        menu.addSection(rows[0].name)
        for item in row_menu_items(state, rows[0]):
            if item is None:
                menu.addSeparator()
                continue
            action_name, text, enabled = item
            action = menu.addAction(text)
            action.setEnabled(enabled)
            action.triggered.connect(lambda checked=False, name=action_name:
                                     self.rowAction.emit(index, name))
        exec_menu(menu, position)
        if alive(menu):
            menu.deleteLater()
        self.interacted.emit()

    def _show_smooth_menu(self, position):
        """スムーズのボタンの右クリック: 強さと回数を選ぶ (設定を変える)。"""
        state = self._state
        if state is None:
            return
        menu = QtWidgets.QMenu(self)
        menu.setAttribute(QtCore.Qt.WA_NoMouseReplay)
        menu.addSection("方式")
        for method, label in SMOOTH_METHOD_LABELS:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(method == state.smooth_method)
            action.triggered.connect(lambda checked=False, m=method: self.settingChosen.emit("smoothMethod", m))
        for title, key, values, current in (
                ("強さ", "smoothStrength", SMOOTH_STRENGTHS, state.smooth_strength),
                ("回数", "smoothIterations", SMOOTH_ITERATIONS, state.smooth_iterations)):
            menu.addSection(title)
            for value in values:
                action = menu.addAction("{:g}".format(value))
                action.setCheckable(True)
                action.setChecked(abs(value - current) < 1e-9)
                action.triggered.connect(lambda checked=False, k=key, v=value: self.settingChosen.emit(k, v))
        exec_menu(menu, position)
        if alive(menu):
            menu.deleteLater()
        self.interacted.emit()

    def isDragging(self):
        return any(row.bar.isDragging() for row in self.rows.values())

    def _show_add_menu(self):
        """選んだ頂点で 0 のインフルエンスの一覧。選ぶと行に足す・外す (チェックは足しているもの)。"""
        state = self._state
        if state is None or not state.zero:
            return
        menu = QtWidgets.QMenu(self)
        # 外をクリックして閉じたとき、そのクリックをビューへ送り直さない (選択が変わらないように)
        menu.setAttribute(QtCore.Qt.WA_NoMouseReplay)
        menu.addSection("0 のインフルエンスを行に足す")
        for item in state.zero:
            action = menu.addAction(item.name)
            action.setCheckable(True)
            action.setChecked(item.pinned)
            action.setToolTip(item.key)
            action.triggered.connect(lambda checked=False, key=item.key: self.addToggled.emit(key))
        position = self.add_button.mapToGlobal(QtCore.QPoint(0, self.add_button.height()))
        exec_menu(menu, position)
        if alive(menu):
            menu.deleteLater()
        self.interacted.emit()

    # -- 描画とイベント -------------------------------------------------------

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        if self._opaque:
            painter.fillRect(self.rect(), Colors.BACKGROUND)
            painter.setPen(Colors.BORDER)
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            painter.end()
            return
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), QtCore.Qt.transparent)   # 前の絵を消す
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        border = QtGui.QColor(Colors.BORDER)
        border.setAlpha(self._opacity)
        background = QtGui.QColor(Colors.BACKGROUND)
        background.setAlpha(self._opacity)
        painter.setPen(QtGui.QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sizeChanged.emit()

    def leaveEvent(self, event):
        self._set_hover(-1)
        if self._resize is None:
            self.unsetCursor()

    # パネルの上のマウスは受け取って、ビュー (選択・カメラ) へ抜けないようにする。
    # 端・角を押したときは大きさを変える
    def mousePressEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.LeftButton:
            edges = edges_at(self.rect(), event_pos(event))
            if edges:
                self._resize = (edges, global_pos(event))

    def mouseReleaseEvent(self, event):
        event.accept()
        if self._resize is not None and event.button() == QtCore.Qt.LeftButton:
            self._resize = None
            self.resizeFinished.emit()
            self.interacted.emit()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        event.accept()
        if self._resize is not None:
            edges, start = self._resize
            self.resizeDragged.emit(edges, global_pos(event) - start)
            return
        cursor = edge_cursor(edges_at(self.rect(), event_pos(event)))
        if cursor is None:
            self.unsetCursor()
        else:
            self.setCursor(cursor)

    def wheelEvent(self, event):
        event.accept()
