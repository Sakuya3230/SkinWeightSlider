# -*- coding: utf-8 -*-
"""
ジョイントへの線と名前の箱の、画面の計算 (Maya に依存しない)。座標は Maya のビューの向き
(左下が原点、y は上向き)、単位はピクセル。tool/manipulator.py が描く。

    box = label_box(jx, jy, text, font_size)          # (左, 下, 右, 上)
    pieces = segment_outside_rect(start, end, box)    # 線のうち箱の外の部分

名前の文字の幅は MUIDrawManager では測れないので、文字数と大きさから見積もる (全角は半角の 2 倍)。
背景はこの箱で描き、線もこの箱で切り取る (奥行きの順に頼らない) ので、見積もりが多少ずれても
背景と線の切れ目は必ず一致する。
"""

__all__ = ["JOINT_PIXELS", "LABEL_GAP", "label_text", "label_box", "segment_outside_rect",
           "weight_color", "ZERO_COLOR", "WEIGHT_RAMP", "WEIGHT_STEPS", "faces_camera"]

# ウェイトの色 (表示の色)。0 は灰色、0 より大きければ 青 -> 水色 -> 緑 -> 黄 -> 赤
ZERO_COLOR = (0.35, 0.35, 0.35)
WEIGHT_RAMP = ((0.0, (0.15, 0.25, 0.85)), (0.25, (0.0, 0.75, 1.0)), (0.5, (0.2, 0.9, 0.25)),
               (0.75, (1.0, 0.9, 0.0)), (1.0, (1.0, 0.15, 0.1)))
WEIGHT_STEPS = 32   # 色を何段階に分けるか (カラーマネジメントを打ち消す変換を段階ごとに覚えるため)


def weight_color(weight, steps=WEIGHT_STEPS):
    """ウェイト (0〜1) の表示の色 (r, g, b)。steps 段階に丸める。0 (1e-6 以下) は灰色。"""
    if weight <= 1e-6:
        return ZERO_COLOR
    t = round(min(max(weight, 0.0), 1.0) * steps) / float(steps)
    for (t0, c0), (t1, c1) in zip(WEIGHT_RAMP, WEIGHT_RAMP[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * k, 6) for a, b in zip(c0, c1))
    return WEIGHT_RAMP[-1][1]


def faces_camera(position, normal, eye=None, direction=None):
    """頂点 (位置・法線) がカメラのほうを向いているか (裏を向いた頂点の点を出さないため)。

    透視のカメラは eye (カメラの位置) から頂点への向き、平行投影は direction (視線の向き) と法線の
    内積が負なら表。点は面より手前に描くので、そのままだと裏側の頂点まで透けて見えた (GUI で確認)。
    """
    if eye is not None:
        sight = [p - e for p, e in zip(position, eye)]
    else:
        sight = list(direction)
    return sum(s * n for s, n in zip(sight, normal)) < 0.0


JOINT_PIXELS = 4          # ジョイントの位置の四角の、画面での半分の大きさ
LABEL_GAP = 3             # 四角と名前のあいだ
LABEL_CHAR_RATIO = 0.5    # 半角 1 文字の幅の目安 (文字の大きさに対する割合。旧版の実機の画面から)


def label_text(name):
    """箱に入れる文字。text2d は箱の左端に文字を付けて描くので、前後に空白を入れて余白にする。"""
    return " " + name + " "


def label_box(jx, jy, text, font_size):
    """ジョイントの画面の位置 (jx, jy) の右に出す名前の箱 (左, 下, 右, 上)。"""
    units = sum(2 if ord(c) > 0x2E7F else 1 for c in text)
    width = units * font_size * LABEL_CHAR_RATIO + 4
    height = font_size + 6
    left = jx + JOINT_PIXELS + LABEL_GAP
    bottom = jy - height / 2.0
    return (left, bottom, left + width, bottom + height)


def segment_outside_rect(start, end, rect):
    """線分 start -> end のうち、矩形 rect の外の部分のリスト (0〜2 本。Liang-Barsky の方法)。"""
    (x0, y0), (x1, y1) = start, end
    left, bottom, right, top = rect
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    # 各辺について p * t <= q が「その辺の内側」の条件
    for p, q in ((-dx, x0 - left), (dx, right - x0), (-dy, y0 - bottom), (dy, top - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return [(start, end)]   # 辺と平行で外側
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return [(start, end)]   # 交わらない

    def at(t):
        return (x0 + dx * t, y0 + dy * t)

    pieces = []
    if t0 > 1e-9:
        pieces.append((start, at(t0)))
    if t1 < 1.0 - 1e-9:
        pieces.append((at(t1), end))
    return pieces
