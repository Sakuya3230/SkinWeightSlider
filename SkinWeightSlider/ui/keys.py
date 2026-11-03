# -*- coding: utf-8 -*-
"""
パネルの上のキーと、ドラッグ中の Esc (Qt のアプリケーションのイベントフィルター)。

    keys = PanelKeys(over_panel, is_dragging, on_key)
    keys.install()      # ツールを有効にしたとき
    keys.uninstall()    # ツールを無効にしたとき (外さないと、リロードのあとも古いコードが呼ばれる)

on_key に渡す名前:
    "scale" / "add" / "absolute" / "move"   マウスがパネルの上にあるときの 1 / 2 / 3 / 4
    "copy" / "paste"                         マウスがパネルの上にあるときの Ctrl+C / Ctrl+V
    "escape"                                 ドラッグ中の Esc (取り消し)
パネルの外のキーは Maya にそのまま渡す (1 / 2 / 3 はスムーズメッシュのプレビュー、Ctrl+C はコピー)。
文字の入力欄 (数値の欄など) にフォーカスがあれば受け取らない。

Maya のホットキーより先に受け取るため、ShortcutOverride のイベントを accept する (Qt はキーを押すと
まず ShortcutOverride を送り、accept されなければショートカットとして扱う)。押しっぱなしの繰り返し
(isAutoRepeat) では実行しない。
"""
from ..core.modes import MODE_KEYS
from .qt import QtCore, QtWidgets

__all__ = ["PanelKeys"]


class PanelKeys(QtCore.QObject):
    def __init__(self, over_panel, is_dragging, on_key):
        super().__init__()
        self._over_panel = over_panel
        self._is_dragging = is_dragging
        self._on_key = on_key
        self._installed = False
        qt = QtCore.Qt
        self._plain = dict((getattr(qt, "Key_" + key), mode) for key, mode in MODE_KEYS.items())
        self._ctrl = {qt.Key_C: "copy", qt.Key_V: "paste"}

    def install(self):
        app = QtWidgets.QApplication.instance()
        if app is not None and not self._installed:
            app.installEventFilter(self)
            self._installed = True

    def uninstall(self):
        app = QtWidgets.QApplication.instance()
        if app is not None and self._installed:
            app.removeEventFilter(self)
        self._installed = False

    def name_for(self, key, modifiers):
        """キーと修飾キーから on_key に渡す名前 (受け取らないなら None)。テストでも使う。"""
        if key == QtCore.Qt.Key_Escape and self._is_dragging():
            return "escape"
        if not self._over_panel() or _typing():
            return None
        if modifiers == QtCore.Qt.NoModifier:
            return self._plain.get(key)
        if modifiers == QtCore.Qt.ControlModifier:
            return self._ctrl.get(key)
        return None

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind not in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress):
            return False
        name = self.name_for(event.key(), event.modifiers())
        if name is None:
            return False
        if kind == QtCore.QEvent.ShortcutOverride:
            event.accept()   # ホットキーより先にキーを受け取る
            return True
        if not event.isAutoRepeat():
            self._on_key(name)
        return True


def _typing():
    typing = (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit,
              QtWidgets.QAbstractSpinBox)
    return isinstance(QtWidgets.QApplication.focusWidget(), typing)
