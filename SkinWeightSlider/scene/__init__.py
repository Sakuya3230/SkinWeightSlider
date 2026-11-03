# -*- coding: utf-8 -*-
"""
Maya のシーンを読む・書く部分 (Qt と ui / tool を import しない)。

    selection  選んだ頂点 (頂点・エッジ・フェース・ソフト選択)、頂点の選択モードへの切り替え
    skin       skinCluster を探してウェイトを読む (SkinData)、重心
    writer     ウェイトを書く (MultiWeightWriter)、自分の書き込みの印 (writing)
    undo       すでに書いた変更を 1 回の Undo として積むコマンド
    prefs      設定の保存先 (optionVar)
    colors     カラーマネジメントを打ち消す色 (display_color)
    watch      選択・ウェイト・ロックの変更の通知
"""
