# -*- coding: utf-8 -*-
"""
スキンウェイトスライダーのプラグイン (登録だけ)。中身は scripts/SkinWeightSlider パッケージ。

    cmds.loadPlugin("skinWeightSlider")    # または  import SkinWeightSlider; SkinWeightSlider.tool()

仕組み (UVPathCut と同じ):
- Maya はプラグインのファイルを名前の無い名前空間で実行し、initializePlugin で登録する。このファイルには
  登録の処理だけを書き、ツールの中身はパッケージに置く (scripts/ は起動用のバッチが PYTHONPATH に足す)
- 登録する creator は、パッケージのクラスを「呼ばれるたびに」importlib で引いて作る。クラスそのものを
  登録すると、パッケージをリロードしても登録したときの古いクラスが使われ続けるため
- コマンド・ノードの名前は SkinWeightSlider.constants から読む
- 旧版 (plug-ins/old/skinWeightSlider_v1.py) と同じ名前・ノードの番号を使うので、同時には読み込めない
"""
import importlib

import maya.api.OpenMaya as om

_VENDOR = "MayaPy"
_VERSION = "2.0"
_CONTEXT_MODULE = "SkinWeightSlider.tool.context"
_MANIP_MODULE = "SkinWeightSlider.tool.manipulator"
_UNDO_MODULE = "SkinWeightSlider.scene.undo"


def maya_useNewAPI():
    """この関数があると、Maya はこのプラグインを API 2.0 (maya.api.OpenMaya) として扱う。"""
    pass


def _context_module():
    return importlib.import_module(_CONTEXT_MODULE)


def _create_context_command():
    return _context_module().SkinWeightSliderContextCommand()


def _create_tool_command():
    return _context_module().ToolCommand()


def _create_manip():
    return importlib.import_module(_MANIP_MODULE).GuideManip()


def _initialize_manip():
    importlib.import_module(_MANIP_MODULE).GuideManip.initialize()


def _create_undo_command():
    return importlib.import_module(_UNDO_MODULE).ApplyWeightsCommand()


def _undo_syntax():
    return importlib.import_module(_UNDO_MODULE).ApplyWeightsCommand.syntax()


def _constants():
    try:
        return importlib.import_module("SkinWeightSlider.constants")
    except ImportError:
        raise RuntimeError("SkinWeightSlider パッケージが見つかりません。scripts/ を PYTHONPATH に"
                           "足してください (起動用のバッチ maya20XX.bat が足します)")


def initializePlugin(plugin):
    """loadPlugin のときに 1 回呼ばれる。"""
    names = _constants()
    _context_module()   # 読めることを先に確かめる (ツール設定のウィンドウの MEL もここで定義される)
    fn = om.MFnPlugin(plugin, _VENDOR, _VERSION, "Any")
    fn.registerNode(names.MANIP_NODE, om.MTypeId(names.MANIP_TYPE_ID), _create_manip,
                    _initialize_manip, om.MPxNode.kManipulatorNode)
    fn.registerContextCommand(names.CONTEXT_COMMAND, _create_context_command)
    fn.registerCommand(names.TOOL_COMMAND, _create_tool_command)
    fn.registerCommand(names.UNDO_COMMAND, _create_undo_command, _undo_syntax)
    _context_module().record_registration()   # 今のフラグの一覧 (変わったらリロードのあとに読み直す)


def uninitializePlugin(plugin):
    """unloadPlugin のときに 1 回呼ばれる。"""
    names = _constants()
    _context_module().delete_tool_context()   # 登録を外す前に、このツールのコンテキストを消す
    fn = om.MFnPlugin(plugin)
    fn.deregisterCommand(names.UNDO_COMMAND)
    fn.deregisterCommand(names.TOOL_COMMAND)
    fn.deregisterContextCommand(names.CONTEXT_COMMAND)
    fn.deregisterNode(om.MTypeId(names.MANIP_TYPE_ID))
