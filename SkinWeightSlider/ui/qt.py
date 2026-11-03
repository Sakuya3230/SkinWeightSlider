# -*- coding: utf-8 -*-
"""
PySide6 (Maya 2025〜) と PySide2 (〜2024) の違いを吸収する。

    from .qt import QtCore, QtGui, QtWidgets, shiboken, event_pos, exec_menu
"""
try:
    from PySide6 import QtCore, QtGui, QtWidgets
    import shiboken6 as shiboken
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    import shiboken2 as shiboken

__all__ = ["QtCore", "QtGui", "QtWidgets", "shiboken", "event_pos", "global_pos", "exec_menu",
           "alive", "text_width"]


def event_pos(event):
    """マウスのイベントの位置 (QPoint。PySide6 は position()、PySide2 は pos())。"""
    if hasattr(event, "position"):
        return event.position().toPoint()
    return event.pos()


def global_pos(event):
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


def exec_menu(menu, position):
    """QMenu を開いて選ばれるまで待つ (PySide2 は exec_)。"""
    return (getattr(menu, "exec", None) or menu.exec_)(position)


def alive(widget):
    """ウィジェットがまだ壊されていないか (C++ の側が消えていれば False)。"""
    return widget is not None and shiboken.isValid(widget)


def text_width(metrics, text):
    """文字の幅 (Qt 5.11 より前は width)。"""
    if hasattr(metrics, "horizontalAdvance"):
        return metrics.horizontalAdvance(text)
    return metrics.width(text)
