# -*- coding: utf-8 -*-
"""
カラーマネジメントを打ち消す色 (マニピュレータの MUIDrawManager に渡す色)。

    drawMgr.setColor(om.MColor(display_color((1.0, 0.35, 0.85))))

カラーマネジメントが有効だと (2022 / 2027 の既定。ACES 1.0 SDR-video)、MUIDrawManager の色は 3D も
2D (line2d・text2d) もシーンリニアの値として表示の変換を通る (旧版の実機で確認: 青が水色に、0.12 の
灰色が明るい灰色に見えた)。cmds.colorManagementConvert(toDisplaySpace=) が「渡す値 -> 表示の色」
なので、その逆を求める。ACES はチャンネルどうしが影響し合うので、1 チャンネルずつ二分法で合わせる
ことを、全体が合うまで繰り返す (1 色 200〜300 回の変換。結果は覚えておく)。
Qt のパネルは変換を通らないので使わない。
"""
import maya.cmds as cmds

__all__ = ["color_management_key", "display_color"]

_CACHE = {}
_QUERY = object()


def color_management_key():
    """今のカラーマネジメントの設定 (変わったら変換をやり直すためのキー)。無効なら None。"""
    try:
        if not cmds.colorManagementPrefs(query=True, cmEnabled=True):
            return None
        return cmds.colorManagementPrefs(query=True, viewTransformName=True)
    except RuntimeError:
        return None


def display_color(rgb, key=_QUERY):
    """画面に rgb (表示の色) で見せるために、setColor に渡す値 (r, g, b)。"""
    if key is _QUERY:
        key = color_management_key()
    rgb = tuple(float(c) for c in rgb)
    if key is None:
        return rgb
    cache_key = (key, rgb)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    value = [max(c, 1e-3) ** 2.2 for c in rgb]   # sRGB のガンマの逆で近い所から始める
    for _sweep in range(8):
        for i in range(3):
            low, high = 0.0, 16.0
            for _ in range(30):
                trial = list(value)
                trial[i] = (low + high) / 2.0
                if cmds.colorManagementConvert(toDisplaySpace=trial)[i] < rgb[i]:
                    low = trial[i]
                else:
                    high = trial[i]
            value[i] = (low + high) / 2.0
        shown = cmds.colorManagementConvert(toDisplaySpace=value)
        if max(abs(s - t) for s, t in zip(shown, rgb)) < 1e-3:
            break
    result = tuple(value)
    _CACHE[cache_key] = result
    return result
