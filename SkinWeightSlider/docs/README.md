# スキンウェイトスライダー (SkinWeightSlider)

選んだ頂点のインフルエンスごとのウェイトを、ビューの上のパネル（Qt）のスライダーで微調整するツールです。行に乗せたインフルエンスのジョイントへ、選んだ頂点の重心から線を引き、ジョイントの位置に名前を出します（Maya の描画）。

旧版（1 ファイルのプラグイン `plug-ins/old/skinWeightSlider_v1.py`）を、パネルを Qt にした形で、役割ごとのモジュールに作り直したものです。Python 3 だけ（Maya 2022〜2027）。

---

## 1. 使い始める

```python
import SkinWeightSlider
SkinWeightSlider.tool()               # プラグインを読み込んで、このツールにする
SkinWeightSlider.add_shelf_button()   # 今のシェルフにボタンを作る (ダブルクリックでツール設定)
```

1. スキンの付いたメッシュの頂点・エッジ・フェースを選ぶ（複数のメッシュ・ソフト選択も可）。
2. ビューの右上（設定で 9 か所）にパネルが出る。行のバーを左右にドラッグすると、そのインフルエンスのウェイトが変わる。
3. 1 回のドラッグが 1 回の Undo。ドラッグ中の Esc で取り消し。

ツールを使っている間も、ビューのクリック・矩形・Shift / Ctrl の選択・ダブルクリックのループ選択・ソフト選択は、標準の選択ツールと同じです。

---

## 2. パネル

```
┌──────────────────────────────────────────────┐
│ ::  [1: 割合] [2: 加算] [3: 絶対] [4: 移動] ↺ │  つまみ・モード・置き場所に戻す
│ body: 頂点 12 個                             │
│ 🔒 ■ joint1   ████████░░░░░░░░   0.488       │  鍵・色・名前・バー・数値
│ 🔒 ■ joint2   █████░░░░░░░░░░░   0.502       │  (バーの下の細い線 = 頂点ごとの最小〜最大)
│ ＋ インフルエンスを足す                      │
│ － 小さいウェイトを刈り取る (0.001 未満)     │
│ [コピー] [ペースト (3)] [平均化]             │
│ 注記 (複数メッシュ・正規化・ソフト選択・最大数)│
└──────────────────────────────────────────────┘
```

| 部分 | 操作 |
|---|---|
| バー | ドラッグでウェイトを変える。Ctrl で 0.01、Shift で 0.1 刻み。Esc で取り消し |
| 数値 | 押すと入力。先頭の記号でモードが分かる（`×1.0` 割合の倍率 / `+0.0` 加算の量 / `=0.250` 絶対の値）。記号を打ち替えればそのモードに、先頭の `-` はどのモードでも「引く」。Enter で決定、Esc で取り消し |
| 鍵 | ロック（lockInfluenceWeights）の切り替え。1 回の Undo |
| 色 | スキンのペイントの一覧と同じインフルエンスの色 |
| 行に乗せる | 重心からそのジョイントへ線、ジョイントの位置に名前（ジョイントを動かしても付いてくる）。選んだ頂点（ソフト選択の範囲も）にそのウェイトを色の点で出す（0 は灰色、小さいほど青、大きいほど赤。ドラッグ中は変えた値） |
| 行の右クリック | ジョイントを選ぶ / 影響を受ける頂点を選ぶ（メッシュ全体から）/ これ以外をすべてロック / すべてロック / すべてロック解除 / 0 にする（ほかへ配る）/ 1 にする（ほかを 0 に）/ 移動の相手へ全部移す / 移動の相手にする・外す。ロックと値の変更はそれぞれ 1 回の Undo |
| モード / 1〜4 キー | 割合（全頂点に同じ倍率）/ 加算（同じ量）/ 絶対（同じ値）/ 移動（相手とのあいだだけ）。キーはマウスがパネルの上にあるときだけ |
| 移動モード | 行をクリックで相手を選ぶ（もう一度で外す）。別の行をドラッグで、相手とのあいだだけで移す |
| ＋ | 選んだ頂点のどれでも 0 のインフルエンスを行に出す（0 からも加算で付けられる） |
| － | しきい値より小さいウェイトを今すぐ 0 にして、残りへ配る |
| コピー / ペースト / 平均化 | パネルの上の Ctrl+C / Ctrl+V でも。ペーストはロックを残して比率で配る |
| スムーズ | 選んだ頂点のウェイトを、隣の頂点（選んでいない頂点も値の元に使う）の平均へ寄せる。強さ（1 回で寄せる割合）× 回数（多いほど遠くまで伝わり、広くなだらか）。ロックは変えず、頂点の合計を保つ。ボタンの右クリックで方式・強さ・回数を選ぶ。方式は「均等」（どの隣も同じ）・「距離に応じて」（近い隣ほど重い 1 / 距離）・「コタンジェント」（辺の向かいの角から決める重み。割り方の偏りに最も強く、平らな所で一様に変わるウェイトはそのまま保つ。鈍角で負になる重みは 0）。距離・角はスキンで変形する前の形で測る。1 回の Undo |
| つまみ / ↺ | ドラッグでパネルを動かす / 置き場所に戻す |
| 端・角 | ドラッグで大きさを変える（反対側の辺は動かない。行が入らない幅・ビューより大きくはならない）。大きさは設定に保存され、選択の前後で変わらない |
| ホイール | 行が入りきらないときにスクロール（カメラのズームにはならない） |

どの編集も、頂点ごとの合計を保ちます（増減分はほかのロックされていないインフルエンスへ今の比率で配る）。正規化が「なし」「後で」の skinCluster でも今の合計を保ち、注記と警告で知らせます。

---

## 3. 設定

ツールのアイコン（かシェルフのボタン）をダブルクリックすると、ツール設定のウィンドウが開きます。値は optionVar `skinWeightSliderSettings`（既定と違う項目だけの JSON）に保存され、Maya を起動し直しても残ります。ウィンドウの上の **Reset Tool** で、すべて既定に戻ります。

| 欄 | 項目（キー） | 既定 |
|---|---|---|
| 操作 | モード（mode）/ Ctrl の刻み（stepCtrl）/ Shift の刻み（stepShift） | 割合 / 0.01 / 0.1 |
| パネル | 出し方（host: window / view）/ 置き場所（placement）/ 背景の不透明度（opacity）/ 幅・高さ（panelWidth / panelHeight）/ 小数の桁数（decimals）/ 並び順（sort）/ インフルエンスの色（influenceColor） | ウィンドウ / 右上 / 210 / 380×300 / 3 / 番号順 / オン |
| 名前 | 名前の出し方（nameStyle: short / unique）/ 名前空間（namespace）/ 長い名前は前を省く（elideFront） | 名前のみ / オン / オン |
| ジョイントの表示 | 線と名前を出す（hoverName）/ 文字の大きさ（labelSize）/ 名前の背景（labelBackground）/ 線・名前・背景の色 / ウェイトの色の点（weightDisplay）/ 点の大きさ（weightPointSize）/ 裏を向いた頂点にも出す（weightBackfaces） | オン / 14 / オン / マゼンタ・白・暗い灰色 / オン / 7 / オフ |
| 最大インフルエンス数 | 守る（maxInfluencesEnabled）/ 数（maxInfluences） | オフ / 6 |
| スムーズ | 方式（smoothMethod: uniform / distance / cotangent）/ 強さ（smoothStrength）/ 回数（smoothIterations） | 均等 / 0.5 / 3 |
| 刈り取り | 自動（pruneAuto）/ しきい値（pruneThreshold） | オン / 0.001 |

パネルの出し方:

- **ウィンドウ**（既定）: ビューの上に重ねた枠なしの小さなウィンドウ。背景を半透明にできる（文字は透けない）。Maya のウィンドウを動かすと、少し遅れて付いてくる。
- **ビューの中**: ビューの描画面の子。不透明。

スクリプトから:

```python
ctx = "skinWeightSliderContext"
cmds.skinWeightSliderCtx(ctx, edit=True, mode="add")                # 設定 (キーがそのままフラグ)
cmds.skinWeightSliderCtx(ctx, query=True, placement=True)           # 選択肢は番号で返る
cmds.skinWeightSliderCtx(ctx, edit=True, setColor="lineColor 1 0 0")
cmds.skinWeightSliderCtx(ctx, edit=True, copyWeights=True)          # 操作: prune / copyWeights /
                                                                    # pasteWeights / averageWeights / smoothWeights
cmds.skinWeightSliderCtx(ctx, edit=True, resetPosition=True)        # パネルを置き場所に戻す
cmds.skinWeightSliderCtx(ctx, edit=True, resetSize=True)            # パネルの大きさを既定に戻す
cmds.skinWeightSliderCtx(ctx, edit=True, resetSettings=True)        # すべて既定に戻す
```

---

## 4. 構成

依存の向きは `tool -> (ui, scene) -> core`（`tests/SkinWeightSlider/test_dependencies.py` が検査）。

```
plug-ins/skinWeightSlider.py   登録だけ (creator がパッケージのクラスを毎回 importlib で引く)
scripts/SkinWeightSlider/
  api.py / constants.py / log.py / reloader.py
  core/          Maya にも Qt にも依存しない (pytest で検査)
    modes          モード・数値の入力の読み方・刻み
    smooth         スムーズ (隣の頂点の平均へ寄せる)
    model          WeightModel (計算) と行の並び
    cleanup        後始末 (最大数・刈り取り) と元のウェイトの記録
    names          インフルエンスの表示名
    clipboard      コピーしたウェイト
    settings       設定の定義表と Settings (フラグ・ツール設定のウィンドウ・保存の元)
    placement      パネルの置き場所 (9 か所 + ずれ)
    guide          ジョイントへの線と名前の箱 (画面の計算)
    panel_state    パネルに出す内容 (PanelState) を組み立てる
    tool_ui_text   ツール設定のウィンドウの MEL を組み立てる
  scene/         Maya を読み書きする (Qt を使わない)
    selection      選んだ頂点・頂点の選択モード
    skin           skinCluster を探して読む (SkinData)・重心・ジョイントの位置
    writer         ウェイト・ロックを書く・自分の書き込みの印
    undo           書いた変更を 1 回の Undo にするコマンド
    prefs          設定の保存先 (optionVar)
    colors         カラーマネジメントを打ち消す色
    watch          選択・ウェイト・ロック・Undo の通知
  ui/            Qt だけ (maya を使わない。offscreen の Qt で検査)
    qt / widgets / panel   パネル (PanelState を出し、操作をシグナルで知らせる)
    host           パネルをビューの上に置く (ウィンドウ / ビューの中)
    keys           パネルの上のキーとドラッグ中の Esc
  tool/          Maya と Qt をつなぐ
    session        ツールの状態と操作 (WeightSession)。パネル・キー・コマンドはどれもここを呼ぶ
    manipulator    ジョイントへの線と名前を描く (2D)
    context        コンテキスト。セッション・パネル・キー・通知・マニピュレータをつなぐ
    command        コンテキストのコマンド (フラグは設定の定義表から) とツールのコマンド
    tool_ui / icon / maya_qt
```

流れ:

```
パネル (Qt) --シグナル--> WeightSession --書く--> skinCluster (scene.writer)
    ^                        |  └--離したら--> scene.undo.commit (1 回の Undo)
    └--setState(PanelState)--┘
                             └--guide()--> GuideManip が線と名前を描く
Maya の通知 (scene.watch) --> WeightSession が読み直す (QTimer で 1 回にまとめる)
設定 (core.settings) --> WeightSession・PanelHost・ツール設定のウィンドウ
```

---

## 5. 旧版からの見直し

| 旧版 | 今の版 | 理由 |
|---|---|---|
| パネルもマニピュレータで描き、押せる部品は 3D の板（ScreenPlane）、背景は押せる部品をくり抜く、色はカラーマネジメントを打ち消す | パネルは Qt のウィジェット。マニピュレータは線と名前だけを 2D で描く（押せる部品を持たない） | 2D で描いたものはハンドルにならないための回避策・z ファイティング・文字の幅を測れない・描けない記号（「〜」）がすべて不要になる |
| 操作の中身がマニピュレータ（ドラッグ）とコンテキスト（入力・ロック・コピー）に分かれていた | `tool/session.py` の WeightSession 1 か所 | パネル・キー・コマンドから同じ操作を呼べ、standalone の mayapy でそのまま検査できる |
| 30 近いフラグを、編集・問い合わせ・ツール設定のウィンドウの 3 か所に手で書いていた | 設定の定義表（core/settings.py）から、フラグ・正規化・保存・ウィンドウの MEL を作る（UVPathCut と同じ形） | 項目を足すときは表に 1 行 |
| 設定は全項目を保存（既定を変えても前の値が使われ続けた） | 既定と違う項目だけを保存 | 既定を変えたら新しい既定になる |
| WeightModel に Maya の情報（parts・MDagPath など）を後から属性で足していた | WeightModel は計算と列・行のキーだけ。Maya の情報は scene/skin.py の SkinData | core を Maya 無しで検査できる |
| Undo / Redo のあとはコマンドがコンテキストを直接呼んで読み直していた | Maya の Undo / Redo のイベント（scene/watch.py）で読み直す | 外の変更と同じ経路 |
| パネルの大きさは中身で決まり、選択の前後で変わった。行の数は設定（maxRows） | 大きさは設定（panelWidth / panelHeight。端・角のドラッグでも変わる）。行は残りの高さいっぱいでスクロール | 選択の前後で大きさが変わって見づらかった（ユーザーの指摘） |
| 置き場所の既定は重心の横（引き出し線つき） | ビューの 9 か所（既定は右上）とつまみのずれ | パネルを Qt にしたため（ユーザーの決定。重心に追従させると 1 フレーム遅れて揺れる） |
| シェルフのボタンはプラグインのコマンド（skinWeightSliderShelf） | `SkinWeightSlider.add_shelf_button()` | 他のパッケージと同じ |
| アイコンは plug-ins/icons | リポジトリの直下の icons（XBMLANGPATH） | 他のパッケージと同じ |

---

## 6. 仕組みと落とし穴（実機で確かめたもの）

パネル（Qt の試作 `plug-ins/old/skinWeightQtPanel.py` で確かめた）:

- 描画面（Maya が OpenGL で描く）の子の半透明は、下を Qt が描き直さないので前の絵が残って重なる。ビューの中では不透明に塗り、パネルが縮んだ・動いたら空いた所をビューに描き直させる。
- パネルをネイティブの子ウィンドウ（WA_NativeWindow）にすると、ツールにした途端にビューの操作（選択など）が一切効かなくなった。しない。
- 枠なしのウィンドウの背景の半透明は、QScrollArea の viewport が背景を塗っていると効かない（Maya のスタイルシート）。viewport と中身を透明にする。
- `MQtUtil` は API 1.0（`maya.OpenMayaUI`）にしか無い。
- 部品はキーボードのフォーカスを取らない（数値の欄だけクリックで取り、確定・Esc でビュー / メインウィンドウへ返す）。Maya のホットキーがそのまま効く。
- パネルの上のクリック・ホイールはビューへ抜けない（パネルが受け取って消費する）。

旧版から引き継いだもの:

- API 2.0 の MPxSelectionContext で基底の `toolOnSetup` を `super()` で呼ぶと SystemError。基底の `doPress` / `doRelease` は `omui.MPxSelectionContext.doPress(self, ...)` で呼べる。
- マニピュレータはプラグをつながないので `finishAddingManips` を呼ばない（kFailure）。
- Undo の名前は実行した MEL の文字列なので、Undo のコマンドは `mel.eval('skinWeightSliderApply -n "..."')` で呼ぶ（Python の cmds だと空、`commandString` も効かない）。
- `MSelectionList` は同じメッシュの vtx と f を 1 項目にまとめ、`getComponent()` が最初の種類しか返さない。選択の文字列ごとに読む。
- 選んであるコンポーネントをクリックすると、MPxSelectionContext は `select -add <対象>` を実行させる（何も変わらない）。直前の Undo の記録の名前から対象を読み、`cmds.undo()` で取り消してから対象だけを選ぶ（Undo / Redo が 1 回で済む）。
- MUIDrawManager の色は 2D・文字もカラーマネジメントの変換を通る。`display_color` で打ち消す（Qt のパネルは通らない）。
- コンテキストのコマンドの問い合わせ（setResult）は文字列を返せない。選択肢は番号で返す。
- ツール設定のウィンドウ: Values の先頭で古いレイアウトを消して Properties を呼び直す。見出し・アイコンは `toolPropertySetCommon`（Reset Tool のコマンドも resetTool に替えるので、既定に戻すコマンドへの差し替えはその後）。

---

## 7. 開発・テスト

```python
import SkinWeightSlider.reloader as r; r.reload().reload_modules()   # ツールのコンテキストも消える
import SkinWeightSlider; SkinWeightSlider.tool()
```

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest scripts/tests/SkinWeightSlider        # core と依存の向き
"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" scripts\tests\SkinWeightSlider\mayapy\run_all.py   # scene・session・プラグイン・Qt
"C:\Program Files\Autodesk\Maya2022\bin\mayapy.exe" scripts\tests\SkinWeightSlider\mayapy\run_all.py   # PySide2
```

standalone の mayapy ではコンテキストを作れないので、ツールそのもの（パネルの表示・ビューの描画・キー・ツール設定のウィンドウ）は GUI で確かめます。旧版と Qt の試作のテストは `scripts/tests/SkinWeightSlider/old/`。

旧版（`plug-ins/old/skinWeightSlider_v1.py`）は同じコマンド名・ノードの番号を使うので、同時には読み込めません。
