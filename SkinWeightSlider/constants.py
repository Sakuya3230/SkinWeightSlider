# -*- coding: utf-8 -*-
"""
プラグインとパッケージの両方が使う名前 (Maya に依存しない)。

プラグイン (plug-ins/skinWeightSlider.py) は initializePlugin でこのモジュールを読み、ここにある名前で
コマンド・ノードを登録する。パッケージの側も同じ名前でコマンドを呼ぶので、名前を 1 か所にまとめる。
"""

PLUGIN_NAME = "skinWeightSlider"            # プラグインの名前 (plug-ins/skinWeightSlider.py)
CONTEXT_COMMAND = "skinWeightSliderCtx"     # コンテキストを作る / 編集する / 問い合わせるコマンド
TOOL_COMMAND = "skinWeightSliderTool"       # このツールにするコマンド (コンテキストを作るか使い回す)
TOOL_CONTEXT = "skinWeightSliderContext"    # skinWeightSliderTool が作って使うコンテキストの名前
UNDO_COMMAND = "skinWeightSliderApply"      # すでに書いた変更を 1 回の Undo として積むコマンド
MANIP_NODE = "skinWeightSliderManip"        # マニピュレータ (ジョイントへの線と名前を描く) のノードの型
# マニピュレータのノードの型の番号。0x00000000〜0x0007ffff は社内・個人用 (配布しないもの) の範囲。
# 旧版 (plug-ins/old/skinWeightSlider_v1.py) と同じ番号なので、同時には読み込めない
MANIP_TYPE_ID = 0x0007F201
CLASS_NAME = "skinWeightSlider"             # コンテキストの stringClassName (ツール設定の MEL の頭)
OPTION_VAR = "skinWeightSliderSettings"     # 設定を保存する Maya の設定 (optionVar。JSON)
PANEL_OBJECT_NAME = "skinWeightSliderPanel"   # Qt のパネルの objectName (残ったものを探して消す)
ICON_NAME = "skinWeightSlider.png"          # ツールのアイコン (リポジトリの直下の icons。XBMLANGPATH で探す)
TITLE = "スキンウェイトスライダー"            # ツールの名前 (ツール設定の見出し・シェルフ)
LOG_PREFIX = "スキンウェイトスライダー"        # スクリプトエディタに出すメッセージの頭

# プラグインが登録するもの。コマンド・ノードを足したら、ここにも足す。
# リロード (reloader.reload_modules) のあとに、読み込み済みのプラグインにこれがそろっているかを
# 確かめ、足りなければプラグインを読み直す (api.ensure_plugin_current)
PLUGIN_COMMANDS = (CONTEXT_COMMAND, TOOL_COMMAND, UNDO_COMMAND)
PLUGIN_NODES = (MANIP_NODE,)
# プラグインを読み込んだときの、コンテキストのコマンドのフラグの一覧 (環境変数に置く。リロードしても消えない)。
# コンテキストのコマンドのフラグは、プラグインを読み込んだときのものから変わらない (モジュールをリロードしても
# 新しいフラグは「Invalid flag」になった。GUI で確認) ので、一覧が変わっていたらプラグインを読み直す
FLAGS_ENV = "SKIN_WEIGHT_SLIDER_REGISTERED_FLAGS"
