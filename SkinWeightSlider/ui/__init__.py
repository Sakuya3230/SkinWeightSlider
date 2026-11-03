# -*- coding: utf-8 -*-
"""
Qt のパネル (maya と scene / tool を import しない。offscreen の Qt でテストできる)。

    qt       PySide6 / PySide2 の違いを吸収する
    widgets  行の部品 (バー・数値の欄・鍵・色・つまみ・戻すボタン)
    panel    パネル全体 (PanelState を表示し、操作をシグナルで知らせる)
    host     パネルをビューの上に置き続ける (ビューの中 / 枠なしのウィンドウ)
    keys     パネルの上のキー (1〜4・Ctrl+C / V) とドラッグ中の Esc
"""
