# -*- coding: utf-8 -*-
"""
ツールのアイコンとシェルフのボタン (UVPathCut と同じ形)。

    icon_path()          ツール・シェルフ・ツール設定の見出しに渡すアイコン (名前か絶対パス)
    add_shelf_button()   今のシェルフにボタンを作る (同じものがあれば作らない)。
                         押すとツールにし、ダブルクリックでツール設定のウィンドウを開く

アイコンは D:\\MayaPy\\icons\\skinWeightSlider.png (リポジトリの直下の icons)。起動用のバッチ
(maya20XX.bat) が XBMLANGPATH にこのフォルダを足すので名前で渡せる。バッチを通さずに起動した Maya
でも出るよう、XBMLANGPATH に無ければ絶対パスを返す。
"""
import os

import maya.cmds as cmds
import maya.mel as mel

from ..constants import ICON_NAME, TITLE

__all__ = ["icon_path", "add_shelf_button", "ICON_DIRECTORY", "SHELF_COMMAND"]

ICON_DIRECTORY = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "..", "..", "..", "icons"))
SHELF_COMMAND = "import SkinWeightSlider; SkinWeightSlider.tool()"
SHELF_DOUBLE_CLICK = "import SkinWeightSlider; SkinWeightSlider.tool()\nimport maya.cmds as cmds\ncmds.toolPropertyWindow()"


def icon_path():
    """アイコン: XBMLANGPATH のフォルダにあれば名前、無ければ絶対パス (/ 区切り)。"""
    for folder in os.environ.get("XBMLANGPATH", "").split(os.pathsep):
        folder = folder.strip().strip('"').replace("%B", "")
        if folder and os.path.isfile(os.path.join(folder, ICON_NAME)):
            return ICON_NAME
    return os.path.join(ICON_DIRECTORY, ICON_NAME).replace("\\", "/")


def add_shelf_button(shelf=None):
    """シェルフ (省くと今開いているシェルフ) にボタンを作る。作ったボタンの名前 (あれば既存のもの)。"""
    if shelf is None:
        top = mel.eval("$sws_tmp = $gShelfTopLevel")
        if not top or not cmds.tabLayout(top, exists=True):
            raise RuntimeError("シェルフが見つかりません (GUI で実行してください)")
        shelf = cmds.tabLayout(top, query=True, selectTab=True)
    for button in cmds.shelfLayout(shelf, query=True, childArray=True) or []:
        if cmds.objectTypeUI(button) == "shelfButton" and \
                cmds.shelfButton(button, query=True, command=True) == SHELF_COMMAND:
            cmds.shelfButton(button, edit=True, image=icon_path())   # アイコンだけ合わせる
            return button
    return cmds.shelfButton(parent=shelf, image=icon_path(), command=SHELF_COMMAND,
                            sourceType="python", label=TITLE,
                            annotation="{} (ダブルクリックで設定)".format(TITLE),
                            doubleClickCommand=SHELF_DOUBLE_CLICK, imageOverlayLabel="")
