# -*- coding: utf-8 -*-
"""
Maya の Qt のウィジェットを引く (パネルを置く先)。

    active_view_widget()   アクティブな 3D ビューの描画面 (M3dView.widget())
    maya_main_window()     Maya のメインウィンドウ (枠なしのウィンドウの持ち主)
    refresh_view()         アクティブな 3D ビューを描き直す

MQtUtil は API 1.0 (maya.OpenMayaUI) にしか無い (2.0 で呼んで AttributeError になった。試作で確認)。
"""
import maya.api.OpenMayaUI as omui
import maya.OpenMayaUI as omui1

from ..ui.qt import QtWidgets, shiboken

__all__ = ["active_view_widget", "maya_main_window", "refresh_view"]


def active_view_widget():
    try:
        pointer = omui.M3dView.active3dView().widget()
    except RuntimeError:
        return None
    if not pointer:
        return None
    return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget)


def maya_main_window():
    pointer = omui1.MQtUtil.mainWindow()
    return shiboken.wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None


def refresh_view():
    try:
        omui.M3dView.active3dView().refresh(False, True)
    except RuntimeError:
        pass
