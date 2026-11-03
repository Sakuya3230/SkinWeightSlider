# -*- coding: utf-8 -*-
"""
SkinWeightSlider の公開 API。

    import SkinWeightSlider
    SkinWeightSlider.tool()              # プラグインを読み込んで、このツールにする
    SkinWeightSlider.add_shelf_button()  # 今のシェルフにボタンを作る
    SkinWeightSlider.load_plugin()       # プラグインを読み込むだけ
    SkinWeightSlider.reload_modules()    # reloader を読み直してから、全モジュールをリロードする
    SkinWeightSlider.reload_plugin()     # プラグインを読み直す (コマンド・ノードを足したとき)

maya はここでは import しない (関数を呼んだときに読む)。
"""
import os

from .constants import (CONTEXT_COMMAND, FLAGS_ENV, PLUGIN_COMMANDS, PLUGIN_NAME, PLUGIN_NODES,
                        TOOL_COMMAND)

__all__ = ["tool", "add_shelf_button", "load_plugin", "plugin_path", "reload_modules",
           "reload_plugin", "missing_registrations", "ensure_plugin_current"]


def plugin_path():
    """プラグインのファイルのフルパス (scripts/SkinWeightSlider から見た ../../plug-ins/skinWeightSlider.py)。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "plug-ins", PLUGIN_NAME + ".py"))


def load_plugin():
    """プラグインが読み込まれていなければ読み込む (名前で読めなければ、このパッケージからのフルパスで)。"""
    import maya.cmds as cmds
    if cmds.pluginInfo(PLUGIN_NAME, query=True, loaded=True):
        return
    try:
        cmds.loadPlugin(PLUGIN_NAME + ".py", quiet=True)
    except RuntimeError:
        cmds.loadPlugin(plugin_path(), quiet=True)


def tool():
    """プラグインを読み込んで、このツールにする。コンテキストの名前を返す。"""
    import maya.cmds as cmds
    load_plugin()
    return getattr(cmds, TOOL_COMMAND)()


def add_shelf_button(shelf=None):
    """今のシェルフ (か shelf) にボタンを作る (同じボタンがあれば作らない)。"""
    load_plugin()
    from .tool.icon import add_shelf_button as add
    return add(shelf)


def reload_modules():
    """reloader 自身を読み直してから、全モジュールを依存順にリロードする (ツールのコンテキストも消す)。"""
    from . import reloader
    return reloader.reload().reload_modules()


def missing_registrations():
    """読み込み済みのプラグインに足りないコマンド・ノードの名前のリスト (読み込まれていなければ None)。"""
    import maya.cmds as cmds
    if not cmds.pluginInfo(PLUGIN_NAME, query=True, loaded=True):
        return None
    nodes = cmds.pluginInfo(PLUGIN_NAME, query=True, dependNode=True) or []
    missing = [name for name in PLUGIN_COMMANDS if not hasattr(cmds, name)]
    missing += [name for name in PLUGIN_NODES if name not in nodes]
    # コンテキストのコマンドのフラグは、プラグインを読み込んだときのものから変わらない
    from .tool.command import flag_signature
    if os.environ.get(FLAGS_ENV) != flag_signature():
        missing.append("{} のフラグ".format(CONTEXT_COMMAND))
    return missing


def reload_plugin():
    """プラグインを読み直す。先にツールのコンテキストを消し、Undo の履歴を消す (プラグインのコマンドが
    Undo のキューに残っていると、プラグインを外せないため)。"""
    import maya.cmds as cmds
    from .tool.command import delete_tool_context
    if cmds.pluginInfo(PLUGIN_NAME, query=True, loaded=True):
        delete_tool_context()
        cmds.flushUndo()
        cmds.unloadPlugin(PLUGIN_NAME)
    load_plugin()


def ensure_plugin_current():
    """読み込み済みのプラグインに足りない登録があれば読み直す。足りなかった名前のリスト。"""
    from . import log
    missing = missing_registrations()
    if not missing:
        return []
    log.info("プラグインに {} が登録されていないので、読み直します (Undo の履歴は消えます)".format(
        ", ".join(missing)))
    reload_plugin()
    return missing
