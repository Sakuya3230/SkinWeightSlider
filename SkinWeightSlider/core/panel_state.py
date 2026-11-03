# -*- coding: utf-8 -*-
"""
パネルに出す内容 (PanelState) を組み立てる (Maya にも Qt にも依存しない)。

    state = build_panel_state(model, order, settings_values, ...)
    panel.setState(state)            # ui/panel.py が表示する

パネル (Qt) はこの PanelState だけを見て描き、操作はシグナルでセッション (tool/session.py) に頼む。
表示の決まり (何を出すか・文字) をここに集めて、pytest で検査できるようにする。
"""

__all__ = ["RowState", "ZeroInfluence", "PanelState", "build_panel_state", "mesh_notes",
           "normalize_warnings", "NORMALIZE_NAMES", "empty_message"]

from .modes import format_threshold, input_text

NORMALIZE_NAMES = {0: "なし", 2: "後で"}   # normalizeWeights がインタラクティブ (1) でないとき


class RowState(object):
    """パネルの 1 行 (1 つのインフルエンス)。"""

    def __init__(self, index, key, name, average, minimum, maximum, locked, color=None,
                 partner=False, active=False, preview=None, edit_text=""):
        self.index = index        # WeightModel の列の番号
        self.key = key            # インフルエンスのフルパス
        self.name = name          # 表示名 (名前の設定どおり。省くのはパネル)
        self.average = average
        self.minimum = minimum
        self.maximum = maximum
        self.locked = locked
        self.color = color        # インフルエンスの色 (r, g, b)。出さないなら None
        self.partner = partner    # 移動モードの相手
        self.active = active      # ドラッグ中の行
        self.preview = preview    # ドラッグ中のマウスの位置の値 (印を出す)。無ければ None
        self.edit_text = edit_text   # 数値の欄を押したときに入れる文字 (input_text)


class ZeroInfluence(object):
    """「＋ インフルエンスを足す」のメニューの 1 項目 (選んだ頂点のどれでも 0 のインフルエンス)。"""

    def __init__(self, key, name, pinned):
        self.key = key
        self.name = name
        self.pinned = pinned      # 行に出している (チェック)


class PanelState(object):
    """パネル全体に出す内容。model が無ければ message だけ。"""

    def __init__(self):
        self.message = ""         # 頂点を選んでいないなどのとき、行の代わりに出す文
        self.info = ""            # 上の小さな文字 (メッシュと頂点の数)
        self.mode = "scale"
        self.rows = []            # RowState のリスト (並び順)
        self.zero = []            # ZeroInfluence のリスト
        self.prune_label = ""     # 「－ 小さいウェイトを刈り取る (0.001 未満)」
        self.clipboard_count = 0  # コピーしたインフルエンスの数 (0 ならペーストは押せない)
        self.can_average = False  # 頂点が 2 つ以上
        self.notes = []           # 下の注記の行
        self.decimals = 3
        self.elide_front = True
        self.dragging = False
        self.generation = 0       # 選択を読み直すたびに増える (パネルはスクロールを先頭に戻す)
        self.offset_moved = False # パネルを動かしている (戻すボタンを明るく)
        self.partner = None       # 移動の相手の番号 (どのモードでも。行の右クリックのメニューに出す)
        self.partner_name = ""
        self.smooth_strength = 0.5   # スムーズの強さと回数 (ボタンの説明・右クリックのメニュー)
        self.smooth_iterations = 3
        self.smooth_method = "uniform"


def normalize_warnings(normalize_modes):
    """正規化がインタラクティブでない skinCluster の注意書き。normalize_modes は {名前: 番号}。"""
    return ["{} は正規化「{}」です (合計は今のまま保ちます)".format(name, NORMALIZE_NAMES[mode])
            for name, mode in sorted(normalize_modes.items()) if mode in NORMALIZE_NAMES]


def mesh_notes(mesh_counts, strengths, normalize_modes):
    """パネルの下の注記: 複数のメッシュならメッシュごとの頂点の数、正規化の注意、ソフト選択の頂点の数。"""
    notes = []
    if len(mesh_counts) >= 2:
        notes.append(" / ".join("{}: {}".format(name, count) for name, count in mesh_counts))
    notes.extend(normalize_warnings(normalize_modes))
    if strengths is not None:
        hard = sum(1 for value in strengths if value >= 1.0 - 1e-6)
        notes.append("ソフト選択: {} 頂点 (選択 {} + 範囲 {})".format(len(strengths), hard,
                                                                    len(strengths) - hard))
    return notes


def empty_message(has_vertices, skipped):
    """行を出せないときの文。"""
    if skipped:
        return "スキンが付いていません: {}".format(", ".join(skipped))
    if not has_vertices:
        return "スキンの付いたメッシュの頂点・エッジ・フェースを選んでください"
    return "スキンが付いていません"


def build_panel_state(model, order, values, colors=None, mesh_counts=(), normalize_modes=None,
                      pinned=(), partner=None, drag_index=None, drag_value=None, clipboard_count=0,
                      limit_note=None, message="", generation=0):
    """PanelState を作る。

    model       WeightModel (None なら message だけ)
    order       行に出すインフルエンスの番号のリスト
    values      設定の値の dict (Settings.values())
    colors      インフルエンスごとの色のリスト (無ければ None)
    pinned      行に出している 0 のインフルエンスのキー (フルパス) の集合
    partner     移動モードの相手の番号 (無ければ None)
    drag_index  ドラッグ中の番号、drag_value はそのマウスの位置の値
    """
    state = PanelState()
    state.mode = values["mode"]
    state.decimals = values["decimals"]
    state.elide_front = values["elideFront"]
    state.clipboard_count = clipboard_count
    state.generation = generation
    state.offset_moved = tuple(values["panelOffset"]) != (0, 0)
    state.smooth_strength = values["smoothStrength"]
    state.smooth_iterations = values["smoothIterations"]
    state.smooth_method = values["smoothMethod"]
    if model is None:
        state.message = message or empty_message(False, ())
        return state
    show_colors = values["influenceColor"] and colors is not None
    for i in order:
        average = model.average(i)
        state.rows.append(RowState(
            i, model.keys[i], model.influences[i], average, model.minimum(i), model.maximum(i),
            model.locks[i], colors[i] if show_colors else None,
            partner=state.mode == "move" and i == partner, active=i == drag_index,
            preview=drag_value if i == drag_index else None,
            edit_text=input_text(state.mode, average, state.decimals)))
    if partner is not None:
        state.partner = partner
        state.partner_name = model.influences[partner]
    nonzero = set(model.rows())
    pinned = set(pinned)
    state.zero = [ZeroInfluence(model.keys[i], model.influences[i], model.keys[i] in pinned)
                  for i in range(len(model.influences)) if i not in nonzero]
    state.prune_label = "－ 小さいウェイトを刈り取る ({} 未満)".format(
        format_threshold(values["pruneThreshold"]))
    state.can_average = len(model.vertices) >= 2
    state.dragging = drag_index is not None
    count = len(model.vertices)
    meshes = len(mesh_counts)
    if meshes == 1:
        state.info = "{}: 頂点 {} 個".format(mesh_counts[0][0], count)
    else:
        state.info = "頂点 {} 個 (メッシュ {} 個)".format(count, meshes)
    state.notes = mesh_notes(list(mesh_counts), model.strengths, normalize_modes or {})
    if limit_note:
        state.notes.append(limit_note)
    return state
