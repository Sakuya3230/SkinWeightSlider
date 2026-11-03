# -*- coding: utf-8 -*-
"""
ツール設定のウィンドウ。MEL は core/tool_ui_text.py が設定の定義表から組み立てる。

    define()        MEL のプロシージャを定義する (import したときに 1 回。リロードでも定義し直す)
    refresh()       開いているウィンドウの値を、今の設定に合わせる (パネル・キーで変えたとき)
    color_value(k)  色の設定の値 [r, g, b] (ウィンドウの MEL が python() で呼ぶ)

Maya はツールのアイコンをダブルクリックしたとき (とツールを有効にしたとき) に
<stringClassName>Properties / Values を呼ぶ。その前に定義しておく必要があるので、このモジュールを
import したとき (コンテキストのモジュールが import する = プラグインを読み込んだとき) に定義する。
"""
import maya.mel as mel

from ..core.settings import Settings
from ..core.tool_ui_text import CLASS_NAME, tool_ui_mel
from ..scene.prefs import OptionVarStorage
from .icon import icon_path

__all__ = ["define", "refresh", "color_value"]


def define():
    mel.eval(tool_ui_mel(icon_path()))


def color_value(key):
    """色の設定の値 [r, g, b]。設定は変えるたびに保存されるので、保存先から読めば今の値。"""
    return [float(c) for c in Settings(OptionVarStorage()).value(key)]


def refresh():
    """開いているウィンドウの値を合わせる (ウィンドウが無い・別のツールなら何もしない)。"""
    try:
        mel.eval("{}RefreshUI".format(CLASS_NAME))
    except RuntimeError:
        pass


define()
