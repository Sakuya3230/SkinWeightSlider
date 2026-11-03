# -*- coding: utf-8 -*-
"""
SkinWeightSlider: 選んだ頂点のインフルエンスごとのウェイトを、ビューの上のパネル (Qt) のスライダーで
微調整するツール。ジョイントへの線と名前は Maya の描画 (マニピュレータ) で出す。

    import SkinWeightSlider
    SkinWeightSlider.tool()              # プラグインを読み込んで、このツールにする
    SkinWeightSlider.add_shelf_button()  # 今のシェルフにボタンを作る

開発中のリロード:

    import SkinWeightSlider.reloader as r; r.reload().reload_modules()
    import SkinWeightSlider; SkinWeightSlider.tool()

使い方・構成・仕組み・落とし穴は docs/README.md。Python 3 だけ (Maya 2022〜)。
"""
from .api import *
