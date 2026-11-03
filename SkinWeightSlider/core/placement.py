# -*- coding: utf-8 -*-
"""
パネルの置き場所と大きさ (Maya に依存しない)。座標は Qt の向き (左上が原点、y は下向き)、単位はピクセル。

    x, y, applied = placement_position("topRight", (800, 600), (320, 240), offset=(-20, 30))
    rect = resize_rect((x, y, w, h), EDGE_LEFT | EDGE_TOP, (dx, dy), minimum)

置き場所はビューの 9 か所 (設定 placement)。つまみで動かしたずれ (設定 panelOffset) を足し、
パネルがビューからはみ出さないよう収める。applied は収めたあとの実際のずれ (はみ出した分を溜めない)。
大きさは設定 panelWidth / panelHeight。端・角のドラッグ (resize_rect) で、反対側の辺を動かさずに変える。
"""

__all__ = ["PLACEMENTS", "PLACEMENT_LABELS", "VIEW_MARGIN", "PANEL_MIN_SIZE", "placement_base",
           "placement_position", "resize_rect", "offset_for", "EDGE_LEFT", "EDGE_RIGHT", "EDGE_TOP",
           "EDGE_BOTTOM"]

PLACEMENTS = ("topLeft", "topCenter", "topRight",
              "middleLeft", "middleCenter", "middleRight",
              "bottomLeft", "bottomCenter", "bottomRight")
PLACEMENT_LABELS = ("左上", "上", "右上", "左", "中央", "右", "左下", "下", "右下")
VIEW_MARGIN = 10   # ビューの端からパネルまで
PANEL_MIN_SIZE = (260, 140)   # パネルの大きさの下限 (設定の範囲。行が入る幅はパネルがさらに決める)
# パネルの端 (ドラッグで大きさを変える辺。角は 2 つを足したもの)
EDGE_LEFT, EDGE_RIGHT, EDGE_TOP, EDGE_BOTTOM = 1, 2, 4, 8


def _parts(placement):
    for horizontal in ("Left", "Center", "Right"):
        if placement.endswith(horizontal):
            vertical = placement[:-len(horizontal)]
            if vertical in ("top", "middle", "bottom"):
                return vertical, horizontal
    raise ValueError("知らない置き場所: {}".format(placement))


def placement_base(placement, view_size, panel_size, margin=VIEW_MARGIN):
    """ずれを足す前のパネルの左上 (x, y) (ビューに収める前)。"""
    vertical, horizontal = _parts(placement)
    vw, vh = view_size
    pw, ph = panel_size
    x = {"Left": margin, "Center": (vw - pw) // 2, "Right": vw - pw - margin}[horizontal]
    y = {"top": margin, "middle": (vh - ph) // 2, "bottom": vh - ph - margin}[vertical]
    return int(x), int(y)


def placement_position(placement, view_size, panel_size, offset=(0, 0), margin=VIEW_MARGIN):
    """パネルの左上 (x, y) と、収めたあとの実際のずれ (dx, dy)。"""
    vw, vh = view_size
    pw, ph = panel_size
    base_x, base_y = placement_base(placement, view_size, panel_size, margin)
    # ビューの中に収める (ビューより大きいときは左上に合わせる)
    x = min(max(base_x + int(offset[0]), 0), max(vw - pw, 0))
    y = min(max(base_y + int(offset[1]), 0), max(vh - ph, 0))
    return int(x), int(y), (int(x - base_x), int(y - base_y))


def offset_for(placement, view_size, rect, margin=VIEW_MARGIN):
    """パネルを rect (x, y, w, h) に置くための、置き場所からのずれ (dx, dy)。"""
    x, y, w, h = rect
    base_x, base_y = placement_base(placement, view_size, (w, h), margin)
    return int(x - base_x), int(y - base_y)


def resize_rect(rect, edges, delta, minimum, bounds=None):
    """端・角のドラッグで変えた矩形 (x, y, w, h)。動かす辺は edges、反対側の辺は動かさない。

    delta は押した位置からのマウスの移動量、minimum は (最小の幅, 最小の高さ)。
    bounds (ビューの幅, 高さ) を渡すと、動かす辺をビューの端で止める (止めないと、ビューに収めるときに
    反対側の辺が押し戻されて、反対側が伸びて見えた。GUI で確認)。
    """
    x, y, w, h = rect
    dx, dy = delta
    if edges & EDGE_RIGHT:
        w = w + dx if bounds is None else min(w + dx, bounds[0] - x)
        w = max(w, minimum[0])
    elif edges & EDGE_LEFT:
        right = x + w
        left = x + dx if bounds is None else max(x + dx, 0)
        w = max(right - left, minimum[0])
        x = right - w
    if edges & EDGE_BOTTOM:
        h = h + dy if bounds is None else min(h + dy, bounds[1] - y)
        h = max(h, minimum[1])
    elif edges & EDGE_TOP:
        bottom = y + h
        top = y + dy if bounds is None else max(y + dy, 0)
        h = max(bottom - top, minimum[1])
        y = bottom - h
    return int(x), int(y), int(w), int(h)
