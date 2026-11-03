# -*- coding: utf-8 -*-
"""
ツール本体 (Maya と Qt を使う)。

    session      ツールの状態と操作 (WeightSession)。パネルとコンテキストのあいだ
    manipulator  ジョイントへの線と名前を描くマニピュレータ
    maya_qt      Maya の Qt のウィジェット (ビューの描画面・メインウィンドウ)
    tool_ui      ツール設定のウィンドウ (MEL を定義する)
    icon         アイコンとシェルフのボタン
    command      コンテキストのコマンド・ツールのコマンド
    context      コンテキスト (ツール)。セッション・パネル・キー・通知・マニピュレータをつなぐ
"""
