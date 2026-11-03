# -*- coding: utf-8 -*-
"""
Maya にも Qt にも依存しない部分 (計算・設定・パネルに出す内容)。pytest (Python 3.7) で検査する。

    modes        ドラッグのモード・数値の入力の読み方・刻み
    model        WeightModel (選んだ頂点のウェイトの計算) と行の並び
    cleanup      編集のあとの後始末 (最大インフルエンス数・刈り取り) と元のウェイトの記録
    names        インフルエンスの表示名
    clipboard    コピーしたウェイト
    settings     設定の定義表と Settings
    placement    パネルの置き場所 (ビューの 9 か所 + ずれ)
    guide        ジョイントへの線と名前の箱 (画面の計算)
    panel_state  パネルに出す内容 (PanelState) を組み立てる
    tool_ui_text ツール設定のウィンドウの MEL を組み立てる
"""
