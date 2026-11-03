# -*- coding: utf-8 -*-
"""
スクリプトエディタに出すメッセージ (頭に「スキンウェイトスライダー:」を付ける)。

    from SkinWeightSlider import log
    log.info("頂点 {} 個".format(count))   # print
    log.warning("ロックされています")        # Maya の警告 (黄色)。Maya が無ければ print

Maya は warning を呼んだときにだけ読み込む (Maya の無い pytest からも import できるように)。
"""
from .constants import LOG_PREFIX

__all__ = ["info", "warning"]


def _text(message):
    return "{}: {}".format(LOG_PREFIX, message)


def info(message):
    print(_text(message))


def warning(message):
    try:
        import maya.api.OpenMaya as om
    except ImportError:
        print("警告 " + _text(message))
        return
    om.MGlobal.displayWarning(_text(message))
