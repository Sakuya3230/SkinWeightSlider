# -*- coding: utf-8 -*-
"""
パネルをアクティブなビューの上に置き続ける (Qt だけ。ビューの取り方は外から渡す)。

    host = PanelHost(make_panel, view_provider, main_window_provider, redraw_view)
    host.configure(host="window", placement="topRight", offset=(0, 0), opacity=210)
    host.close()

出し方 (設定 host):
    window  枠なしの Tool ウィンドウ (Maya のメインウィンドウが持ち主) を、描画面の上に置く。
            WA_TranslucentBackground で背景を半透明にできる (試作で確認)。表示しただけでは
            フォーカスを奪わない (WA_ShowWithoutActivating)。数値の欄に打てるよう、フォーカスは
            受け取れるようにし、操作のあとは returnFocus でメインウィンドウへ返す
    view    描画面 (M3dView.widget()) の子。不透明に塗り、パネルが縮んだ・動いたら空いた所を
            ビューに描き直させる (前の絵が残るため。試作で確認)。パネルをネイティブの子ウィンドウに
            すると、ビューの操作 (選択など) が一切効かなくなった (試作で確認) ので、しない

アクティブなビュー (4 画面・スペースでの最大化) が替わったら付け替え、パネルが壊されたら作り直す
(QTimer で 0.25 秒ごとに確かめる)。ビュー・メインウィンドウの大きさ・位置が変わったら置き直す。
置き場所は core/placement.py (ビューの 9 か所 + つまみで動かしたずれ。ビューの中に収める)。
大きさは設定 (panelWidth / panelHeight) をホストが決める (パネルは中身で大きさを変えない)。行が入らない
幅・ビューより大きくはしない。パネルの端・角のドラッグでは、反対側の辺を動かさずに大きさとずれを変え、
離したら on_resize(大きさ, ずれ) で 1 回だけ知らせる (設定に保存する)。
"""
from ..core.placement import offset_for, placement_position, resize_rect
from ..core.settings import HOST_VIEW, HOST_WINDOW
from .qt import QtCore, QtGui, QtWidgets, alive, shiboken

__all__ = ["PanelHost", "HOST_WINDOW", "HOST_VIEW", "SYNC_INTERVAL", "remove_panels"]

SYNC_INTERVAL = 250   # アクティブなビューを確かめる間隔 (ミリ秒)


def _pointer(widget):
    return shiboken.getCppPointer(widget)[0] if widget is not None else 0


class PanelHost(QtCore.QObject):
    """パネルをビューの上に置く。

    make_panel()            新しいパネル (PanelWidget) を返す (壊されたら作り直すため)
    view_provider()         アクティブなビューの描画面の QWidget (無ければ None)
    main_window_provider()  Maya のメインウィンドウ (window の持ち主)
    redraw_view()           ビューを描き直させる (view で、パネルが空けた所の前の絵を消す)
    on_offset(offset)       つまみで動かし終えたときの、実際のずれ (ビューの中に収めたあと)
    on_resize(size, offset) 端・角で大きさを変え終えたときの、実際の大きさとずれ (まとめて保存する。
                            別々に保存すると、途中で古いずれのまま置き直されて動いて見えた)
    """

    def __init__(self, make_panel, view_provider, main_window_provider=None, redraw_view=None,
                 on_offset=None, on_resize=None, interval=SYNC_INTERVAL):
        super().__init__()
        self._make_panel = make_panel
        self._view_provider = view_provider
        self._main_window_provider = main_window_provider or (lambda: None)
        self._redraw_view = redraw_view or (lambda: None)
        self._on_offset = on_offset
        self._on_resize = on_resize
        self.size = (380, 300)     # 保存している大きさ
        self._drag_size = None     # 端のドラッグ中の大きさ
        self._resize_start = None  # 端を押したときの矩形 (x, y, 幅, 高さ)
        self._rect = None          # 置いた矩形 (ビューの中の x, y, 幅, 高さ)
        self.host = HOST_WINDOW
        self.placement = "topRight"
        self.offset = (0, 0)       # 保存しているずれ
        self.opacity = 255
        self.panel = None
        self.view = None
        self._key = None
        self._watched = []
        self._drag_offset = None   # つまみのドラッグ中のずれ
        self._drag_start = (0, 0)  # 押したときのずれ
        self._applied = (0, 0)     # 置いたときの実際のずれ
        self._geometry = None
        self.log = []              # 付け替えの記録 (診断・テスト用)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(interval)
        self._timer.timeout.connect(self.sync)
        self._timer.start()

    # -- 設定 -----------------------------------------------------------------

    def configure(self, host=None, placement=None, offset=None, opacity=None, size=None):
        """出し方・置き場所・ずれ・不透明度・大きさを変える (変わったものだけ)。"""
        rebuild = host is not None and host != self.host
        if host is not None:
            self.host = host
        if placement is not None:
            self.placement = placement
        if offset is not None:
            self.offset = (int(offset[0]), int(offset[1]))
        if opacity is not None:
            self.opacity = int(opacity)
        if size is not None:
            self.size = (int(size[0]), int(size[1]))
        if rebuild:
            self._discard_panel()   # 親の種類が変わるので作り直す (ウィンドウのフラグも変わる)
        elif alive(self.panel):
            self.panel.setTranslucent(self.host == HOST_WINDOW, self.opacity)
        self.sync()

    # -- 付け替えと置き直し -----------------------------------------------------

    def sync(self):
        """アクティブなビューを確かめ、変わっていれば付け替え、置き直す。"""
        view = self._view_provider()
        if not alive(view):
            if alive(self.panel):
                self.panel.hide()
            return
        if not alive(self.panel):
            self.panel = None
        parent = self._main_window_provider() if self.host == HOST_WINDOW else view
        key = (_pointer(view), _pointer(parent), self.host)
        if self.panel is None or key != self._key:
            self._attach(view, parent)
            self._key = key
        self.place()

    def _attach(self, view, parent):
        self._unwatch()
        if self.panel is None:
            self.panel = self._make_panel()
            self.panel.sizeChanged.connect(self.place)
            self.panel.gripDragged.connect(self._grip_dragged)
            self.panel.gripFinished.connect(self._grip_finished)
            self.panel.resizeDragged.connect(self._resize_dragged)
            self.panel.resizeFinished.connect(self._resize_finished)
        if self.host == HOST_WINDOW:
            flags = QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint
            self.panel.setParent(parent, flags)
            self.panel.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
            self.panel.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
            self._watch(parent)   # メインウィンドウが動いたら置き直す
        else:
            self.panel.setParent(parent)
        self.panel.setTranslucent(self.host == HOST_WINDOW, self.opacity)
        self.view = view
        self._watch(view)
        self._geometry = None
        self.panel.show()
        self.panel.raise_()
        self.log.append("{} -> {}".format(self.host, view.metaObject().className()))

    def place(self):
        if not (alive(self.panel) and alive(self.view)):
            return
        view = self.view
        width, height = self.panelSize()
        if (self.panel.width(), self.panel.height()) != (width, height):
            self.panel.setFixedSize(width, height)
        offset = self._drag_offset if self._drag_offset is not None else self.offset
        x, y, self._applied = placement_position(self.placement, (view.width(), view.height()),
                                                 (width, height), offset)
        self._rect = (x, y, width, height)
        if self.host == HOST_WINDOW:
            origin = view.mapToGlobal(QtCore.QPoint(0, 0))
            main = self._main_window_provider()
            visible = view.isVisible() and not (alive(main) and main.isMinimized())
            self.panel.setVisible(visible)
        else:
            origin = QtCore.QPoint(0, 0)
            if not self.panel.isVisible():
                self.panel.show()   # ビューが無いあいだ隠していたもの
        self.panel.move(origin + QtCore.QPoint(x, y))
        if self.host != HOST_WINDOW:
            self.panel.raise_()
            self._redraw_vacated()

    def _redraw_vacated(self):
        """前の矩形のうち、今のパネルの外になった所があれば、ビューを描き直させる。"""
        geometry = self.panel.geometry()
        before, self._geometry = self._geometry, QtCore.QRect(geometry)
        if before is None or before == geometry or geometry.contains(before):
            return
        if alive(self.view):
            self.view.update()
        self._redraw_view()

    def panelSize(self):
        """パネルの実際の大きさ: 設定 (ドラッグ中はその大きさ) を、行が入る大きさ以上・ビュー以下に。"""
        width, height = self._drag_size if self._drag_size is not None else self.size
        if alive(self.panel):
            least = self.panel.minimumPanelSize()
            width, height = max(width, least[0]), max(height, least[1])
        if alive(self.view):
            width = min(width, max(self.view.width(), 1))
            height = min(height, max(self.view.height(), 1))
        return int(width), int(height)

    # -- 端・角で大きさを変える ----------------------------------------------------

    def _resize_dragged(self, edges, delta):
        if not (alive(self.panel) and alive(self.view) and self._rect is not None):
            return
        if self._resize_start is None:
            self._resize_start = self._rect
        view_size = (self.view.width(), self.view.height())
        rect = resize_rect(self._resize_start, edges, (delta.x(), delta.y()),
                           self.panel.minimumPanelSize(), view_size)
        self._drag_size = (rect[2], rect[3])
        self._drag_offset = offset_for(self.placement, view_size, rect)
        self.place()

    def _resize_finished(self):
        if self._resize_start is None:
            return
        self._resize_start = None
        self.size = self.panelSize()   # 収めたあとの大きさ
        self._drag_size = None
        self._drag_offset = None
        self.offset = tuple(self._applied)
        self.place()
        if self._on_resize is not None:
            self._on_resize(self.size, self.offset)

    # -- つまみ -----------------------------------------------------------------

    def _grip_dragged(self, delta):
        if self._drag_offset is None:
            self._drag_start = self.offset   # 押したときのずれ
        self._drag_offset = (self._drag_start[0] + delta.x(), self._drag_start[1] + delta.y())
        self.place()

    def _grip_finished(self):
        if self._drag_offset is None:
            return
        self._drag_offset = None
        self.offset = tuple(self._applied)   # はみ出した分を溜めない
        self.place()
        if self._on_offset is not None:
            self._on_offset(self.offset)

    # -- そのほか ---------------------------------------------------------------

    def containsCursor(self):
        """マウスがパネルの上にあるか (パネルの上のキーを受け取るか決める)。"""
        panel = self.panel
        if not (alive(panel) and panel.isVisible()):
            return False
        return panel.rect().contains(panel.mapFromGlobal(QtGui.QCursor.pos()))

    def returnFocus(self):
        """キーボードのフォーカスをビューへ返す (Maya のホットキーが効くように)。"""
        if self.host == HOST_WINDOW:
            main = self._main_window_provider()
            if alive(main):
                main.activateWindow()
        if alive(self.view):
            self.view.setFocus()

    def _watch(self, widget):
        if alive(widget):
            widget.installEventFilter(self)
            self._watched.append(widget)

    def _unwatch(self):
        for widget in self._watched:
            if alive(widget):
                widget.removeEventFilter(self)
        self._watched = []

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Move, QtCore.QEvent.Show,
                            QtCore.QEvent.Hide, QtCore.QEvent.WindowStateChange):
            QtCore.QTimer.singleShot(0, self.place)
        return False

    def _discard_panel(self):
        self._unwatch()
        self._geometry = None
        if alive(self.panel):
            self.panel.hide()
            self.panel.setParent(None)
            self.panel.deleteLater()
        self.panel = None
        self.view = None
        self._key = None

    def close(self):
        self._timer.stop()
        self._discard_panel()


def remove_panels(object_name):
    """objectName が object_name のウィジェットを消す (リロードの前のパネルが残っていたとき)。"""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return 0
    count = 0
    for widget in app.allWidgets():
        if widget.objectName() == object_name:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
            count += 1
    return count
