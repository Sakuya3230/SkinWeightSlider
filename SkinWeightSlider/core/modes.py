# -*- coding: utf-8 -*-
"""
ドラッグのモード・数値の入力の読み方・刻み (Maya に依存しない)。

モード (設定 mode):
    割合 (scale)      全頂点に同じ倍率を掛ける。頂点どうしの比を保つ。0 の頂点は 0 のまま
    加算 (add)        全頂点に同じ量を足す。頂点どうしの差を保つ。0 からも増える
    絶対 (absolute)   全頂点を同じ値にする
    移動 (move)       相手のインフルエンスとのあいだだけでやり取りする (ほかは変えない)

数値の入力 (行の右端の数値の欄): 意味はモードごと。割合は倍率、加算は足す量、絶対は値、移動は相手から
移す量。先頭に * x × (割合) / + (加算) / = (絶対) があればそのモードにする。先頭の - はどのモードでも
「引く」(加算で負の量。移動では相手へ戻す量)。欄を押したときの最初の文字は input_text
(「×1.0」「+0.0」「=0.250」) で、先頭の記号でモードが分かるようにしてある。
"""

__all__ = ["MODE_SCALE", "MODE_ADD", "MODE_ABSOLUTE", "MODE_MOVE", "MODES", "MODE_LABELS",
           "MODE_KEYS", "INPUT_PREFIXES", "INPUT_SYMBOLS", "parse_input", "input_text",
           "snap_value", "drag_step", "format_value", "format_threshold"]

MODE_SCALE = "scale"
MODE_ADD = "add"
MODE_ABSOLUTE = "absolute"
MODE_MOVE = "move"
MODES = (MODE_SCALE, MODE_ADD, MODE_ABSOLUTE, MODE_MOVE)
MODE_LABELS = {MODE_SCALE: "割合", MODE_ADD: "加算", MODE_ABSOLUTE: "絶対", MODE_MOVE: "移動"}
MODE_KEYS = {"1": MODE_SCALE, "2": MODE_ADD, "3": MODE_ABSOLUTE, "4": MODE_MOVE}   # パネルの上のキー

# 数値の入力の先頭の記号 -> モード (今のモードに関係なく、その処理にする)
INPUT_PREFIXES = {"*": MODE_SCALE, "x": MODE_SCALE, "X": MODE_SCALE, "×": MODE_SCALE,
                  "+": MODE_ADD, "=": MODE_ABSOLUTE}
INPUT_SYMBOLS = {MODE_SCALE: "×", MODE_ADD: "+", MODE_ABSOLUTE: "=", MODE_MOVE: "⇄"}


def parse_input(text, mode):
    """数値の入力の文字列を (モード, 値) にする。読めない・範囲外なら ValueError (理由)。

    今のモード mode で読む。先頭の記号でモードを上書きする (上の説明)。範囲:
      割合 倍率は 0 以上 / 加算・移動 -1〜1 / 絶対 0〜1
    """
    text = text.strip()
    if text.startswith("-"):
        if mode != MODE_MOVE:   # 移動モードでは、負の数は「相手へ戻す」量のまま
            mode = MODE_ADD
        text = "-" + text[1:].strip()   # "- 0.05" の空白も除く
    elif text and text[0] in INPUT_PREFIXES:
        mode = INPUT_PREFIXES[text[0]]
        text = text[1:].strip()
    try:
        value = float(text)
    except ValueError:
        raise ValueError("数として読めません: {}".format(text or "(空)"))
    if mode == MODE_SCALE and value < 0.0:
        raise ValueError("倍率は 0 以上にしてください: {}".format(value))
    if mode in (MODE_ADD, MODE_MOVE) and not -1.0 <= value <= 1.0:
        raise ValueError("{}は -1 から 1 にしてください: {}".format(
            "足す量" if mode == MODE_ADD else "移す量", value))
    if mode == MODE_ABSOLUTE and not 0.0 <= value <= 1.0:
        raise ValueError("値は 0 から 1 にしてください: {}".format(value))
    return mode, value


def input_text(mode, average, decimals=3):
    """数値の欄を押したときに入れておく文字 (先頭の記号でモードが分かる)。

    割合は「×1.0」、加算は「+0.0」、絶対は「=今の平均」、移動は「0.0」(⇄ は読めないので付けない)。
    """
    if mode == MODE_SCALE:
        return "×1.0"
    if mode == MODE_ADD:
        return "+0.0"
    if mode == MODE_MOVE:
        return "0.0"
    return "=" + format_value(average, decimals)


def format_value(value, decimals=3):
    return "{:.{}f}".format(value, int(decimals))


def format_threshold(value):
    """しきい値の表示 (0.001 -> "0.001"、0.0005 -> "0.0005")。"""
    return "{:.6f}".format(value).rstrip("0").rstrip(".")


def snap_value(value, step):
    """値を 0〜1 に収め、step の倍数に丸める。step が None なら丸めない。"""
    value = min(max(value, 0.0), 1.0)
    if not step:
        return value
    return min(max(round(value / step) * step, 0.0), 1.0)


def drag_step(ctrl, shift, step_ctrl, step_shift):
    """押している修飾キーからドラッグの刻み (両方なら細かい Ctrl)。無ければ None。"""
    if ctrl:
        return step_ctrl
    if shift:
        return step_shift
    return None
