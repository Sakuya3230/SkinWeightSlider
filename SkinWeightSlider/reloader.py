# -*- coding: utf-8 -*-
"""
SkinWeightSlider のモジュールを依存順に import / リロードする (UVPathCut と同じ形)。

    import SkinWeightSlider.reloader as r; r.reload().reload_modules()
    import SkinWeightSlider; SkinWeightSlider.tool()

reload() はこの reloader 自身を読み直して返す (読み込み済みの古い reloader の一覧だと、足した
モジュールがリロードされないため)。reload_modules() の流れ:
1. ツールのコンテキストを消す (コンテキストのインスタンスは作ったときのクラスのままなので、消さないと
   古いコードが動き続ける。消すと toolOffCleanup でパネル・キーのフィルター・コールバックも外れる)
2. MODULES -> UI_MODULES -> MAYA_MODULES の順に読み直す (読み込まれていなければ import)
3. 一覧に無いのに読み込まれている SkinWeightSlider のモジュールがあれば知らせる
4. 読み込み済みのプラグインに constants.PLUGIN_COMMANDS / PLUGIN_NODES がそろっているか確かめ、
   足りなければプラグインを読み直す (Undo の履歴は消える)
プラグインは普段は読み直さなくてよい (creator がモジュールを毎回引くので、次に作るものは新しいクラス)。

モジュールを追加したら、正しい一覧の正しい位置に足すこと (tests/SkinWeightSlider/test_dependencies.py
が漏れを検出する)。
"""
import importlib
import sys

__all__ = ["MODULES", "UI_MODULES", "MAYA_MODULES", "reload", "reload_modules", "reload_module"]

# Maya にも Qt にも依存しないもの (依存の浅い順)
MODULES = [
    "SkinWeightSlider.constants",
    "SkinWeightSlider.log",
    "SkinWeightSlider.core",
    "SkinWeightSlider.core.modes",
    "SkinWeightSlider.core.model",
    "SkinWeightSlider.core.names",
    "SkinWeightSlider.core.placement",
    "SkinWeightSlider.core.smooth",
    "SkinWeightSlider.core.settings",
    "SkinWeightSlider.core.cleanup",
    "SkinWeightSlider.core.clipboard",
    "SkinWeightSlider.core.guide",
    "SkinWeightSlider.core.panel_state",
    "SkinWeightSlider.core.tool_ui_text",
]

# Qt が要るもの (Maya は要らない)
UI_MODULES = [
    "SkinWeightSlider.ui",
    "SkinWeightSlider.ui.qt",
    "SkinWeightSlider.ui.widgets",
    "SkinWeightSlider.ui.panel",
    "SkinWeightSlider.ui.host",
    "SkinWeightSlider.ui.keys",
]

# Maya が要るもの (Maya の中でだけリロードする)
MAYA_MODULES = [
    "SkinWeightSlider.scene",
    "SkinWeightSlider.scene.writer",
    "SkinWeightSlider.scene.selection",
    "SkinWeightSlider.scene.skin",
    "SkinWeightSlider.scene.undo",
    "SkinWeightSlider.scene.prefs",
    "SkinWeightSlider.scene.colors",
    "SkinWeightSlider.scene.watch",
    "SkinWeightSlider.tool",
    "SkinWeightSlider.tool.maya_qt",
    "SkinWeightSlider.tool.icon",
    "SkinWeightSlider.tool.tool_ui",
    "SkinWeightSlider.tool.session",
    "SkinWeightSlider.tool.manipulator",
    "SkinWeightSlider.tool.command",
    "SkinWeightSlider.tool.context",
    "SkinWeightSlider.api",
    "SkinWeightSlider",
]


def _has(module_name):
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


def reload_module(module_name):
    """モジュールを、読み込まれていればリロード、まだなら import する。"""
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def reload():
    """この reloader 自身を読み直して返す。r.reload().reload_modules() と使う。"""
    return reload_module(__name__)


def reload_modules():
    """一覧のモジュールを依存順にリロードする。読み直したモジュールのリストを返す。"""
    in_maya = _has("maya.cmds")
    if in_maya and "SkinWeightSlider.tool.command" in sys.modules:
        sys.modules["SkinWeightSlider.tool.command"].delete_tool_context()
    names = list(MODULES)
    if _has("SkinWeightSlider.ui.qt"):
        names += UI_MODULES
    names += MAYA_MODULES if in_maya else ["SkinWeightSlider.api", "SkinWeightSlider"]
    modules = [reload_module(name) for name in names]
    unlisted = sorted(name for name in sys.modules
                      if name.startswith("SkinWeightSlider.") and name not in names
                      and name != __name__ and sys.modules[name] is not None)
    if unlisted:
        print("スキンウェイトスライダー: 一覧 (reloader) に無いので読み直していないモジュール: {}".format(
            ", ".join(unlisted)))
    if in_maya:
        sys.modules["SkinWeightSlider.api"].ensure_plugin_current()
    return modules
