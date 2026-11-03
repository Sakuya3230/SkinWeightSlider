# -*- coding: utf-8 -*-
"""
ツール設定のウィンドウの MEL を、設定の定義表から組み立てる (Maya に依存しない。UVPathCut と同じ形)。

    text = tool_ui_mel(icon)     # tool/tool_ui.py が mel.eval で定義する

ツールのアイコンをダブルクリックすると開くウィンドウは、Maya が MEL のプロシージャを呼んで作る:
    <クラス名>Properties             部品を作る (値は入れない)
    <クラス名>Values(ツールの名前)   ツールを有効にするたび・ウィンドウを開くたびに呼ばれる。
                                     今の値を部品に入れ、操作したらコンテキストのコマンドで値を変える
クラス名はコンテキストの stringClassName() ("skinWeightSlider")。レイアウトの名前も同じにする。

部品は設定の種類ごと (どれも見出しの列の幅を揃える):
    BOOL    checkBoxGrp       -changeCommand1 で skinWeightSliderCtx -e -<キー> #1
    CHOICE  radioButtonGrp (2〜4 個) / optionMenuGrp (5 個以上。置き場所の 9 か所)
    INT     intSliderGrp      FLOAT  floatSliderGrp (field_only なら floatFieldGrp)
    COLOR   colorSliderGrp    -setColor "キー r g b" (問い合わせは python() で tool_ui.color_value)
説明は部品のツールチップ (-annotation)。

旧版 (plug-ins/old/skinWeightSlider_v1.py) で確かめた落とし穴:
- Values の先頭で setParent してから、部品を名前だけで操作する (しないと Object not found)
- Properties はそのクラス名で最初に使ったときにしか呼ばれないらしいので、Values の先頭で古い
  レイアウトを消して Properties を呼び直す
- ウィンドウの上の見出し・アイコンは toolPropertySetCommon で入れる (呼ばないと前のツールの
  「Select Tool」のまま)。これは「Reset Tool」のコマンドも Maya の resetTool に替えるので、
  設定を既定に戻すコマンドへの差し替えはその後に行う (resetTool はプラグインの optionVar を戻せない)
- 問い合わせは文字列を返せないので、選択肢は番号で返る (-select は 1 から)
- 波ダッシュ (U+301C) が 1 つでも入ると、その後ろの日本語がすべて「?」になった (今の版の GUI で
  確認。旧版のパネルの text2d と同じ)。safe_text で全角のチルダ (U+FF5E) に置き換える
"""
from .settings import BOOL, CHOICE, COLOR, DEFINITIONS, FLOAT, INT

__all__ = ["CLASS_NAME", "CONTEXT_COMMAND", "control_name", "tool_ui_mel", "sections", "KEY_HELP"]

CLASS_NAME = "skinWeightSlider"      # constants.CLASS_NAME と同じ (core は constants を見ない)
CONTEXT_COMMAND = "skinWeightSliderCtx"
LABEL_WIDTH = 140
CHOICE_WIDTH = 100
COLOR_SWATCH_WIDTH = 50
COLOR_SLIDER_WIDTH = 160
TOOL_UI_MODULE = "SkinWeightSlider.tool.tool_ui"

KEY_HELP = (
    "行のバーをドラッグ: ウェイトを変える (Ctrl / Shift で刻み、Esc で取り消し)",
    "パネルの上で 1 / 2 / 3 / 4: 割合 / 加算 / 絶対 / 移動、Ctrl+C / Ctrl+V: コピー / ペースト",
    "移動: 行をクリックで相手を選び、別の行をドラッグで相手とのあいだだけで移す",
    "数値を押して入力 (×倍率 / +足す量 / =値。先頭の - で引く)、Enter で決定、Esc で取り消し",
    "鍵: ロック / ＋: 0 のインフルエンスを行に足す / －: 小さいウェイトを刈り取る",
    "行の右クリック: ジョイント・影響を受ける頂点を選ぶ / これ以外をロック / 0・1 にする / 移動の相手",
    "スムーズ: 隣の頂点の平均へ寄せる (強さ × 回数。ボタンの右クリックで変える)",
    "左上のつまみ: パネルを動かす / 右上の矢印: 置き場所に戻す / 端・角のドラッグ: 大きさを変える",
    "行に乗せる: 重心からそのジョイントへ線を引き、ジョイントの位置に名前を出す",
)


def control_name(key):
    return "{}_{}".format(CLASS_NAME, key)


# MEL に渡すと、その後ろの日本語がすべて「?」になる文字 (GUI と mayapy で確認。Python の cp932 では
# 変換できるが、Maya の変換では U+301C の波ダッシュを扱えない)。同じ形の文字に置き換える
UNSAFE_CHARACTERS = {"〜": "～"}


def safe_text(text):
    for bad, good in UNSAFE_CHARACTERS.items():
        text = text.replace(bad, good)
    return text


def mel_string(text):
    return '"{}"'.format(safe_text(text).replace("\\", "\\\\").replace('"', '\\"'))


def sections(definitions=DEFINITIONS):
    """[(欄の名前, [設定の定義])]。欄の無い (ウィンドウに出さない) 設定は除く。"""
    order = []
    for setting in definitions:
        if setting.section and setting.section not in order:
            order.append(setting.section)
    return [(name, [s for s in definitions if s.section == name]) for name in order]


def _uses_menu(setting):
    return setting.kind == CHOICE and len(setting.choices) > 4


def _control_command(setting):
    """部品の MEL のコマンドの名前。"""
    if setting.kind == BOOL:
        return "checkBoxGrp"
    if setting.kind == CHOICE:
        return "optionMenuGrp" if _uses_menu(setting) else "radioButtonGrp"
    if setting.kind == INT:
        return "intSliderGrp"
    if setting.kind == FLOAT:
        return "floatFieldGrp" if setting.field_only else "floatSliderGrp"
    if setting.kind == COLOR:
        return "colorSliderGrp"
    raise ValueError("ウィンドウに出せない種類です: {}".format(setting.key))


def _setting_control(setting):
    """設定 1 つの部品を作る MEL の行 (Properties の中)。"""
    name = control_name(setting.key)
    label = mel_string(setting.label)
    tip = "-annotation {} ".format(mel_string(setting.description)) if setting.description else ""
    first = "-columnWidth 1 {} ".format(LABEL_WIDTH)
    kind = setting.kind
    if kind == BOOL:
        return ["checkBoxGrp -numberOfCheckBoxes 1 -label {} -label1 {} {}{}{};".format(
            label, mel_string(setting.check_label), first, tip, name)]
    if kind == CHOICE and _uses_menu(setting):
        lines = ["optionMenuGrp -label {} {}{}{};".format(label, first, tip, name)]
        lines += ["    menuItem -label {};".format(mel_string(text)) for text in setting.choice_labels]
        return lines
    if kind == CHOICE:
        count = len(setting.choices)
        labels = " ".join(mel_string(text) for text in setting.choice_labels)
        widths = " ".join("-columnWidth {} {}".format(i + 2, CHOICE_WIDTH) for i in range(count))
        return ["radioButtonGrp -numberOfRadioButtons {} -label {} -labelArray{} {} {}{} {}{};".format(
            count, label, count, labels, first, widths, tip, name)]
    if kind == INT:
        return [("intSliderGrp -label {} -field true -minValue {} -maxValue {} -fieldMinValue {} "
                 "-fieldMaxValue {} {}{}{};").format(label, setting.minimum, setting.maximum,
                                                    setting.minimum, setting.maximum, first, tip, name)]
    if kind == FLOAT and setting.field_only:
        return ["floatFieldGrp -numberOfFields 1 -label {} -precision {} {}{}{};".format(
            label, setting.precision, first, tip, name)]
    if kind == FLOAT:
        return [("floatSliderGrp -label {} -field true -precision {} -minValue {} -maxValue {} "
                 "-fieldMinValue {} -fieldMaxValue {} {}{}{};").format(
            label, setting.precision, setting.minimum, setting.maximum, setting.minimum,
            setting.maximum, first, tip, name)]
    if kind == COLOR:
        # 列の幅を決めないと、色の四角が横に伸びてスライダーが見えなくなる (UVPathCut で確認)
        return ["colorSliderGrp -label {} -columnWidth3 {} {} {} {}{};".format(
            label, LABEL_WIDTH, COLOR_SWATCH_WIDTH, COLOR_SLIDER_WIDTH, tip, name)]
    raise ValueError("ウィンドウに出せない種類です: {}".format(setting.key))


def _setting_command(setting):
    """部品に、変えたときのコマンドを付ける MEL の行 (Values の中)。"""
    name = control_name(setting.key)
    kind = setting.kind
    edit = '("{} -edit -{} #1 " + $toolName)'.format(CONTEXT_COMMAND, setting.key)
    if kind == CHOICE and _uses_menu(setting):
        return 'optionMenuGrp -edit -changeCommand ("{}Pick {} " + $toolName) {};'.format(
            CLASS_NAME, setting.key, name)
    if kind == CHOICE:
        parts = ['-onCommand{} ("{} -edit -{} {} " + $toolName)'.format(
            i + 1, CONTEXT_COMMAND, setting.key, choice) for i, choice in enumerate(setting.choices)]
        return "radioButtonGrp -edit {} {};".format(" ".join(parts), name)
    if kind == COLOR:
        return 'colorSliderGrp -edit -changeCommand ("{}SetColor {} " + $toolName) {};'.format(
            CLASS_NAME, setting.key, name)
    if kind == BOOL:
        return "checkBoxGrp -edit -changeCommand1 {} {};".format(edit, name)
    return "{} -edit -changeCommand {} {};".format(_control_command(setting), edit, name)


def _setting_value(setting):
    """部品に今の値を入れる MEL の行 (SetValues の中)。"""
    name = control_name(setting.key)
    kind = setting.kind
    if kind == COLOR:
        query = 'python("__import__(\'{}\', fromlist=[\'x\']).color_value(\'{}\')")'.format(
            TOOL_UI_MODULE, setting.key)
        return "{{ float $c[] = {}; colorSliderGrp -edit -rgb $c[0] $c[1] $c[2] {}; }}".format(query, name)
    query = "`{} -q -{} $toolName`".format(CONTEXT_COMMAND, setting.key)
    if kind == CHOICE:
        return "{} -edit -select ({} + 1) {};".format(_control_command(setting), query, name)
    if kind == BOOL:
        return "checkBoxGrp -edit -value1 {} {};".format(query, name)
    if kind == FLOAT and setting.field_only:
        return "floatFieldGrp -edit -value1 {} {};".format(query, name)
    return "{} -edit -value {} {};".format(_control_command(setting), query, name)


def _button_row(buttons):
    """見出しの列 (空) の右にボタンを並べる。buttons は [(表示名, 説明, 部品の名前)]。"""
    count = len(buttons) + 1
    widths = " ".join("-columnWidth {} 150".format(i + 2) for i in range(len(buttons)))
    lines = ["rowLayout -numberOfColumns {} -columnWidth 1 {} {};".format(count, LABEL_WIDTH, widths),
             '    text -label "";']
    for title, tip, name in buttons:
        lines.append("    button -label {} -width 146 -annotation {} {};".format(
            mel_string(title), mel_string(tip), name))
    lines.append("setParent ..;")
    return lines


BUTTONS = (
    ("resetPosition", "パネルの位置を戻す", "つまみで動かしたパネルを、置き場所に戻す", "パネル"),
    ("resetSize", "パネルの大きさを戻す", "パネルの幅と高さを既定に戻す", "パネル"),
    ("prune", "今すぐ刈り取る", "選んだ頂点の、しきい値より小さいウェイトを今すぐ 0 にする", "刈り取り"),
    ("smoothWeights", "今すぐスムーズ", "選んだ頂点のウェイトを、隣の頂点の平均へ寄せる (強さ × 回数)", "スムーズ"),
)


def tool_ui_mel(icon="", definitions=DEFINITIONS):
    """ツール設定のウィンドウの MEL のプロシージャ (Properties / Values / SetValues / SetColor /
    Pick / RefreshUI)。icon はウィンドウの見出しのアイコン (名前かフルパス)。"""
    lines = []

    def add(text, depth=0):
        lines.append("    " * depth + text)

    # -- Properties: 部品を作る ------------------------------------------------
    add("global proc {}Properties()".format(CLASS_NAME))
    add("{")
    add("setUITemplate -pushTemplate OptionsTemplate;", 1)
    add("string $parent = `toolPropertyWindow -q -location`;", 1)
    add("setParent $parent;", 1)
    add("columnLayout -adjustableColumn true {};".format(CLASS_NAME), 1)
    for section, settings in sections(definitions):
        add("frameLayout -label {} -collapsable true -collapse false;".format(mel_string(section)), 2)
        add("columnLayout -adjustableColumn true;", 3)
        for setting in settings:
            for line in _setting_control(setting):
                add(line, 4)
        buttons = [(title, tip, control_name(key)) for key, title, tip, where in BUTTONS
                   if where == section]
        if buttons:
            for line in _button_row(buttons):
                add(line, 4)
        add("setParent ..;", 3)
        add("setParent ..;", 2)
    add('frameLayout -label "キーと操作" -collapsable true -collapse true;', 2)
    add("columnLayout -adjustableColumn true;", 3)
    for text in KEY_HELP:
        add('text -align "left" -label {};'.format(mel_string(text)), 4)
    add("setParent ..;", 3)
    add("setParent ..;", 2)
    add("setParent ..;", 1)
    add("setUITemplate -popTemplate;", 1)
    add("}")
    add("")
    # -- Values: 古いレイアウトを作り直し、コマンドを付け、値を入れる ----------------------
    add("global proc {}Values(string $toolName)".format(CLASS_NAME))
    add("{")
    add('string $parent = `toolPropertyWindow -q -location` + "|{}";'.format(CLASS_NAME), 1)
    add("if (`layout -exists $parent`) deleteUI $parent;", 1)
    add("{}Properties();".format(CLASS_NAME), 1)
    add("setParent $parent;   // 部品を名前だけで操作するため", 1)
    for setting in definitions:
        if setting.section:
            add(_setting_command(setting), 1)
    for key, _title, _tip, _where in BUTTONS:
        add('button -edit -command ("{} -edit -{} true " + $toolName) {};'.format(
            CONTEXT_COMMAND, key, control_name(key)), 1)
    add("{}SetValues $toolName;".format(CLASS_NAME), 1)
    add("// 見出し・アイコンをこのツールのものにする (Reset Tool のコマンドも resetTool に替わる)", 1)
    add("toolPropertySetCommon $toolName {} \"\";".format(mel_string(icon)), 1)
    add("// Reset Tool で設定を既定に戻す (resetTool はプラグインの optionVar を戻せない)", 1)
    add('string $resetCommand = "{} -edit -resetSettings true " + $toolName + "; {}Values " + $toolName;'
        .format(CONTEXT_COMMAND, CLASS_NAME), 1)
    add("string $resetButton = `toolPropertyWindow -query -resetButton`;", 1)
    add('if ($resetButton != "" && `button -exists $resetButton`)', 1)
    add("button -edit -enable true -command $resetCommand $resetButton;", 2)
    add("toolPropertySelect {};".format(CLASS_NAME), 1)
    add("}")
    add("")
    # -- SetValues: 今の値を入れる ------------------------------------------------
    add("global proc {}SetValues(string $toolName)".format(CLASS_NAME))
    add("{")
    for setting in definitions:
        if setting.section:
            add(_setting_value(setting), 1)
    add("}")
    add("")
    # -- SetColor: 色のスライダーで選んだ色を -setColor で設定する -------------------------
    add("global proc {}SetColor(string $key, string $toolName)".format(CLASS_NAME))
    add("{")
    add('setParent (`toolPropertyWindow -q -location` + "|{}");'.format(CLASS_NAME), 1)
    add('float $c[] = `colorSliderGrp -q -rgb ("{}_" + $key)`;'.format(CLASS_NAME), 1)
    add('{} -edit -setColor ($key + " " + $c[0] + " " + $c[1] + " " + $c[2]) $toolName;'.format(
        CONTEXT_COMMAND), 1)
    add("}")
    add("")
    # -- Pick: optionMenuGrp で選んだ番号を渡す (#1 は表示名なので使わない) ----------------
    add("global proc {}Pick(string $key, string $toolName)".format(CLASS_NAME))
    add("{")
    add('setParent (`toolPropertyWindow -q -location` + "|{}");'.format(CLASS_NAME), 1)
    add('int $index = `optionMenuGrp -q -select ("{}_" + $key)` - 1;'.format(CLASS_NAME), 1)
    add('eval ("{} -edit -" + $key + " " + $index + " " + $toolName);'.format(CONTEXT_COMMAND), 1)
    add("}")
    add("")
    # -- RefreshUI: パネル・キーで設定を変えたとき、開いているウィンドウを合わせる ---------------
    add("global proc {}RefreshUI()".format(CLASS_NAME))
    add("{")
    add('string $parent = `toolPropertyWindow -q -location` + "|{}";'.format(CLASS_NAME), 1)
    add("if (!`layout -exists $parent`) return;", 1)
    add("string $tool = `currentCtx`;", 1)
    add("// 今のツールがこのツールでなければ、問い合わせが失敗する (catch が 1 を返す)", 1)
    first_flag = next(s.key for s in definitions if s.short_flag)
    add("if (catch(`{} -q -{} $tool`)) return;".format(CONTEXT_COMMAND, first_flag), 1)
    add("string $old = `setParent -q`;", 1)
    add("setParent $parent;", 1)
    add("{}SetValues $tool;".format(CLASS_NAME), 1)
    add('if ($old != "") setParent $old;', 1)
    add("}")
    return safe_text("\n".join(lines) + "\n")
