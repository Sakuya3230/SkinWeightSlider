# -*- coding: utf-8 -*-
"""
コンテキストのコマンド (skinWeightSliderCtx)・ツールのコマンド (skinWeightSliderTool)・コンテキストの削除。

    cmds.skinWeightSliderCtx("名前")                                   コンテキストを作る (makeObj)
    cmds.skinWeightSliderCtx("名前", edit=True, mode="add")            設定を変える
    cmds.skinWeightSliderCtx("名前", query=True, mode=True)            設定を問い合わせる (選択肢は番号)
    cmds.skinWeightSliderCtx("名前", edit=True, setColor="lineColor 1 0 0")
    cmds.skinWeightSliderCtx("名前", edit=True, copyWeights=True)      操作 (編集だけ)
    delete_tool_context()                                              リロードの前に消す

設定のフラグは設定の定義表 (core/settings.DEFINITIONS) から作る。表に無いフラグ (操作) は *_FLAG。
旧版は 30 近いフラグを 1 つずつ手で書いていた (編集・問い合わせ・ツール設定のウィンドウの 3 か所)。

問い合わせの戻り値 (setResult) は bool / int / float だけ。文字列を返すと kFailure になる (旧版で確認)
ので、選択肢は番号で返す。編集は名前でも番号でもよい。
"""
import os

import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
import maya.cmds as cmds

from .. import log
from ..constants import CONTEXT_COMMAND, FLAGS_ENV, TOOL_CONTEXT
from ..core import settings as settings_module
from ..core.settings import BOOL, CHOICE, COLOR, DEFINITIONS, FLOAT, INT, SettingsError

__all__ = ["SkinWeightSliderContextCommand", "ToolCommand", "delete_tool_context", "ACTION_FLAGS",
           "flag_signature", "record_registration",
           "RESET_FLAG", "RESET_POSITION_FLAG", "RESET_SIZE_FLAG", "SET_COLOR_FLAG"]

RESET_FLAG = ("-rs", "-resetSettings")            # 真偽値: すべての設定を既定に戻す (Reset Tool)
RESET_POSITION_FLAG = ("-rp", "-resetPosition")   # 真偽値: つまみで動かしたパネルを戻す
RESET_SIZE_FLAG = ("-rsz", "-resetSize")          # 真偽値: パネルの大きさを既定に戻す
SET_COLOR_FLAG = ("-stc", "-setColor")            # 文字列 "キー r g b": 色の設定を変える
# 操作 (編集だけ。真偽値で True なら行う): (短い名前, 長い名前, セッションの run_action の名前)
ACTION_FLAGS = (("-pr", "-prune", "prune"), ("-cw", "-copyWeights", "copy"),
                ("-pw", "-pasteWeights", "paste"), ("-aw", "-averageWeights", "average"),
                ("-smo", "-smoothWeights", "smooth"))

_FLAG_TYPES = {BOOL: om.MSyntax.kBoolean, CHOICE: om.MSyntax.kString, INT: om.MSyntax.kLong,
               FLOAT: om.MSyntax.kDouble}


def flag_signature():
    """コンテキストのコマンドのフラグの一覧 (文字列。変わったらプラグインを読み直す)。"""
    names = [setting.long_flag for setting in _settings_definitions()]
    names += [RESET_FLAG[1], RESET_POSITION_FLAG[1], RESET_SIZE_FLAG[1], SET_COLOR_FLAG[1]]
    names += [long_name for _short, long_name, _action in ACTION_FLAGS]
    return ",".join(sorted(names))


def record_registration():
    """プラグインを読み込んだときに呼ぶ (今のフラグの一覧を覚える)。"""
    os.environ[FLAGS_ENV] = flag_signature()


def _settings_definitions():
    return [setting for setting in DEFINITIONS if setting.short_flag is not None]


class SkinWeightSliderContextCommand(omui.MPxContextCommand):
    """skinWeightSliderCtx。cmds.skinWeightSliderCtx("名前") を呼ぶと Maya がこれを作って makeObj を呼び、
    返したインスタンスがその名前のツールになる。edit / query は、そのツールを作ったときのコマンドの
    インスタンスの doEditFlags / doQueryFlags が呼ばれる (だから self._context でツールに届く)。"""

    def __init__(self):
        super().__init__()
        self._context = None

    def makeObj(self):
        from .context import SkinWeightSliderContext   # context が command を import するので後で引く
        self._context = SkinWeightSliderContext()
        return self._context

    def _target(self):
        """編集・問い合わせの対象。作ったコンテキストを見失っていれば、作ったことのあるもの
        (試作で、編集のときに self._context が None になったことがあった)。"""
        if self._context is None:
            from .context import known_context
            self._context = known_context()
        if self._context is None:
            raise RuntimeError("{}: コンテキストがありません。先に {} してください".format(
                CONTEXT_COMMAND, "SkinWeightSlider.tool()"))
        return self._context

    def appendSyntax(self):
        syntax = self.syntax()
        for setting in _settings_definitions():
            syntax.addFlag(setting.short_flag, setting.long_flag, _FLAG_TYPES[setting.kind])
        for short, long_name in (RESET_FLAG, RESET_POSITION_FLAG, RESET_SIZE_FLAG):
            syntax.addFlag(short, long_name, om.MSyntax.kBoolean)
        syntax.addFlag(SET_COLOR_FLAG[0], SET_COLOR_FLAG[1], om.MSyntax.kString)
        for short, long_name, _action in ACTION_FLAGS:
            syntax.addFlag(short, long_name, om.MSyntax.kBoolean)

    def doEditFlags(self):
        parser = self.parser()
        context = self._target()
        settings = context.settings
        if parser.isFlagSet(RESET_FLAG[0]) and parser.flagArgumentBool(RESET_FLAG[0], 0):
            settings.reset()   # ほかのフラグより先に (一緒に指定した値を残す)
            log.info("設定を既定に戻しました")
        for setting in _settings_definitions():
            flag = setting.short_flag
            if not parser.isFlagSet(flag):
                continue
            if setting.kind == BOOL:
                value = parser.flagArgumentBool(flag, 0)
            elif setting.kind == INT:
                value = parser.flagArgumentInt(flag, 0)
            elif setting.kind == FLOAT:
                value = parser.flagArgumentDouble(flag, 0)
            else:
                value = parser.flagArgumentString(flag, 0)
            try:
                settings.set(setting.key, value)
            except SettingsError as error:
                raise RuntimeError("{}: {}".format(CONTEXT_COMMAND, error))
        if parser.isFlagSet(SET_COLOR_FLAG[0]):
            text = parser.flagArgumentString(SET_COLOR_FLAG[0], 0)
            parts = text.split(None, 1)
            try:
                if len(parts) != 2 or settings_module.definition(parts[0]).kind != COLOR:
                    raise SettingsError("「キー r g b」の形で、色の設定のキーを渡してください: {}".format(text))
                settings.set(parts[0], parts[1])
            except SettingsError as error:
                raise RuntimeError("{}: -setColor: {}".format(CONTEXT_COMMAND, error))
        if parser.isFlagSet(RESET_POSITION_FLAG[0]) and parser.flagArgumentBool(RESET_POSITION_FLAG[0], 0):
            settings.set("panelOffset", (0, 0))
        if parser.isFlagSet(RESET_SIZE_FLAG[0]) and parser.flagArgumentBool(RESET_SIZE_FLAG[0], 0):
            settings.reset(["panelWidth", "panelHeight"])
        for short, _long, action in ACTION_FLAGS:
            if parser.isFlagSet(short) and parser.flagArgumentBool(short, 0):
                context.runAction(action)

    def doQueryFlags(self):
        parser = self.parser()
        settings = self._target().settings
        for setting in _settings_definitions():
            if not parser.isFlagSet(setting.short_flag):
                continue
            if setting.kind == CHOICE:
                self.setResult(settings.choiceIndex(setting.key))
            elif setting.kind == INT:
                self.setResult(int(settings.value(setting.key)))
            elif setting.kind == FLOAT:
                self.setResult(float(settings.value(setting.key)))
            else:
                self.setResult(bool(settings.value(setting.key)))
            return


class ToolCommand(om.MPxCommand):
    """skinWeightSliderTool: このツールにする (決まった名前のコンテキストが無ければ作る)。"""

    def doIt(self, args):
        if not cmds.contextInfo(TOOL_CONTEXT, exists=True):
            getattr(cmds, CONTEXT_COMMAND)(TOOL_CONTEXT)
        cmds.setToolTo(TOOL_CONTEXT)
        self.setResult(TOOL_CONTEXT)


def delete_tool_context():
    """このツールのコンテキストを消す (使っていたら選択ツールに戻してから)。

    リロードの前に呼ぶ。コンテキストのインスタンスは作ったときのクラスのままなので、消して
    作り直さないと、リロードしても古いコードが動き続ける。
    """
    if not cmds.contextInfo(TOOL_CONTEXT, exists=True):
        return False
    if cmds.currentCtx() == TOOL_CONTEXT:
        cmds.setToolTo("selectSuperContext")
    cmds.deleteUI(TOOL_CONTEXT, toolContext=True)
    return True
