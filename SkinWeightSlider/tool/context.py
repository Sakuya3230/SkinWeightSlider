# -*- coding: utf-8 -*-
"""
コンテキスト (ツール本体)。セッション・パネル・キー・通知・マニピュレータをつなぐ。

    SkinWeightSlider.tool()      # プラグインを読み込んで、このツールにする

ツールを有効にしたとき (toolOnSetup):
    session  = WeightSession(settings)          操作の中身 (tool/session.py)
    watcher  = SceneWatcher(...)                選択・ウェイト・ロックの変更 -> session が読み直す
    host     = PanelHost(...)                   Qt のパネルをビューの上に置く (ui/host.py)
    keys     = PanelKeys(...)                   パネルの上のキーとドラッグ中の Esc (ui/keys.py)
    manip    = GuideManip                       ジョイントへの線と名前 (tool/manipulator.py)
パネルの操作はシグナルでセッションのメソッドへ、セッションの変更はリスナーでパネル (setState) と
ビューの描き直しへ流れる。ツールを無効にしたとき (toolOffCleanup) に、全部外して消す
(残すと、ツールを抜けても呼ばれ続け、リロードのあとは古いコードが呼ばれる)。

MPxSelectionContext なので、ビューのクリック・矩形・Shift / Ctrl の選択は標準の選択ツールと同じ。
パネルは Qt のウィジェットなので、パネルの上のクリックはビュー (選択・カメラ) へ抜けない。

旧版から引き継いだ選択の手当て (GUI で確認済み):
- ダブルクリックのスマートな選択 (setAllowDoubleClickAction。コマンドを通さずに作ったコンテキストでは
  失敗するので、コンストラクタで失敗しても toolOnSetup でもう一度)・選ぶ前のハイライト
  (setAllowPreSelectHilight。toolOnSetup の中で呼ぶ)・ソフト選択 (setAllowSoftSelect)
- ツールを有効にしたとき、メッシュをオブジェクトとして選んでいたら頂点の選択モードにする
  (選択を変えるたびに切り替えるのは安定しなかったのでしない)
- 選んであるコンポーネントをクリックすると、MPxSelectionContext は「select -add <対象>」を
  実行させる (何も変わらない)。直前の Undo の記録の名前から対象を読み、何も変えていない select -add を
  cmds.undo() で取り消してから、対象だけの選択に置き換える (Undo / Redo が 1 回で済む)
- 基底の toolOnSetup / toolOffCleanup は呼ばない (API 2.0 では super() で呼ぶと SystemError)。
  基底の doPress / doRelease は omui.MPxSelectionContext.doPress(self, ...) で呼べる
- クラスでは引数なしの super() を使う (リロードのあとに古いインスタンスへイベントが届いても TypeError に
  ならない)。プラグインは creator でこのモジュールを毎回引くので、リロードのあとに作るものは新しいクラス
"""
import maya.api.OpenMayaUI as omui
import maya.cmds as cmds

from .. import log
from ..constants import CLASS_NAME, MANIP_NODE, PANEL_OBJECT_NAME, TITLE
from ..core.modes import MODES
from ..core.settings import Settings
from ..scene.prefs import OptionVarStorage
from ..scene.selection import (added_by_click, enter_vertex_mode, needs_vertex_mode,
                               selected_mesh_transform, selected_vertices)
from ..scene.watch import SceneWatcher
from ..ui.host import PanelHost, remove_panels
from ..ui.keys import PanelKeys
from ..ui.panel import PanelWidget
from ..ui.qt import QtCore, alive
from . import tool_ui
from .command import (SkinWeightSliderContextCommand, ToolCommand, delete_tool_context,
                      record_registration)
from .icon import icon_path
from .manipulator import GuideManip
from .maya_qt import active_view_widget, maya_main_window, refresh_view
from .session import WeightSession

__all__ = ["SkinWeightSliderContext", "SkinWeightSliderContextCommand", "ToolCommand",
           "delete_tool_context", "record_registration", "active_context", "known_context",
           "CLICK_PIXELS"]

CLICK_PIXELS = 3   # 押してから離すまでにこれより動かさなければクリック (選択の置き換え)
_HOST_KEYS = ("host", "placement", "panelOffset", "opacity", "panelWidth", "panelHeight")

_ACTIVE = [None]   # 有効なコンテキスト
_KNOWN = [None]    # 最後に作ったコンテキスト (コマンドが見失ったとき用)


def active_context():
    return _ACTIVE[0]


def known_context():
    return _ACTIVE[0] or _KNOWN[0]


def _defer(function):
    """通知・マウスの処理を抜けてから呼ぶ (Qt のイベントループの次の回)。"""
    QtCore.QTimer.singleShot(0, function)


class SkinWeightSliderContext(omui.MPxSelectionContext):
    def __init__(self):
        super().__init__()
        self.setTitleString(TITLE)
        try:
            self.setImage(icon_path(), omui.MPxContext.kImage1)
        except RuntimeError:
            pass
        self.settings = Settings(OptionVarStorage())
        self.settings.addListener(self._on_setting)
        self.session = None
        self.host = None
        self.keys = None
        self.watcher = None
        self.manip = None
        self._host_paused = False
        self._click = None
        self._double_click = False
        self._enable_double_click(report=False)
        _KNOWN[0] = self

    def stringClassName(self):
        # Maya はこの名前に Properties / Values を付けた MEL でツール設定のウィンドウを作る (tool_ui)
        return CLASS_NAME

    # -- ツールの有効・無効 -----------------------------------------------------

    def toolOnSetup(self, event):
        self.setHelpString("{}: スキンの付いた頂点を選び、パネルの行をドラッグ".format(TITLE))
        self._enable_double_click()
        self._enable("setAllowPreSelectHilight", "選ぶ前のハイライト")
        self._enable("setAllowSoftSelect", "ソフト選択")
        if selected_vertices().isEmpty():
            transform = selected_mesh_transform()
            if transform and needs_vertex_mode(transform):
                enter_vertex_mode(transform)
        remove_panels(PANEL_OBJECT_NAME)   # リロードの前のパネルが残っていれば消す
        _ACTIVE[0] = self
        self.session = WeightSession(self.settings, defer=_defer)
        self.session.addListener(self._on_session_changed)
        self.watcher = SceneWatcher(self.session.schedule_selection, self.session.schedule_reload)
        self.watcher.start()
        self.session.watcher = self.watcher
        self.host = PanelHost(self._make_panel, active_view_widget, maya_main_window, refresh_view,
                              on_offset=self._on_offset, on_resize=self._on_resize)
        self.keys = PanelKeys(self.host.containsCursor, self.session.isDragging, self._on_key)
        self.keys.install()
        # マニピュレータ: newManipulator の引数は registerNode で登録したノードの型の名前。
        # (Python のインスタンス, MObject) が返る。プラグをつながないので finishAddingManips は呼ばない
        manip, node = GuideManip.newManipulator(MANIP_NODE)
        manip.session = self.session
        self.addManipulator(node)
        self.manip = manip
        self.session.read_selection()
        self._configure_host()

    def toolOffCleanup(self):
        if self.keys is not None:
            self.keys.uninstall()
            self.keys = None
        if self.session is not None:
            self.session.close()   # ドラッグ中なら押す前に戻す
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher = None
        if self.host is not None:
            self.host.close()
            self.host = None
        self.deleteManipulators()
        self.manip = None
        self.session = None
        if _ACTIVE[0] is self:
            _ACTIVE[0] = None

    def _enable_double_click(self, report=True):
        if self._double_click:
            return
        try:
            self.setAllowDoubleClickAction()
            self._double_click = True
        except RuntimeError as error:
            if report:
                log.warning("ダブルクリックの選択を有効にできませんでした: {}".format(error))

    def _enable(self, method, title):
        try:
            getattr(self, method)()
        except RuntimeError as error:
            log.warning("{}を有効にできませんでした: {}".format(title, error))

    # -- パネル -----------------------------------------------------------------

    def _make_panel(self):
        """PanelHost が呼ぶ (はじめと、パネルが壊されて作り直すとき)。"""
        panel = PanelWidget(PANEL_OBJECT_NAME)
        session = self.session
        panel.rowPressed.connect(session.press)
        panel.rowMoved.connect(session.move)
        panel.rowReleased.connect(session.release)
        panel.rowHovered.connect(session.set_focus)
        panel.lockClicked.connect(session.toggle_lock)
        panel.rowAction.connect(session.row_action)
        panel.valueEntered.connect(session.enter_value)
        panel.modeClicked.connect(session.set_mode)
        panel.addToggled.connect(session.toggle_pin)
        panel.pruneClicked.connect(session.prune_now)
        panel.actionClicked.connect(session.run_action)
        panel.settingChosen.connect(self.settings.set)
        panel.resetPositionClicked.connect(lambda: self.settings.set("panelOffset", (0, 0)))
        panel.interacted.connect(self._return_focus)
        panel.setState(session.panel_state())
        return panel

    def _configure_host(self):
        if self.host is not None:
            values = self.settings.values()
            self.host.configure(host=values["host"], placement=values["placement"],
                                offset=values["panelOffset"], opacity=values["opacity"],
                                size=(values["panelWidth"], values["panelHeight"]))

    def _on_session_changed(self, view_only):
        panel = self.host.panel if self.host is not None else None
        if not view_only and alive(panel):
            panel.setState(self.session.panel_state())
        refresh_view()

    def _on_offset(self, offset):
        self.settings.set("panelOffset", offset)   # つまみで動かし終えた (ビューの中に収めたずれ)

    def _on_resize(self, size, offset):
        """端・角で大きさを変え終えた。幅・高さ・ずれをまとめて保存し、置き直すのは最後に 1 回だけ
        (1 つずつ置き直すと、途中で新しい大きさと古いずれの組み合わせになり、パネルが動いた)。"""
        self._host_paused = True
        try:
            self.settings.set("panelWidth", size[0])
            self.settings.set("panelHeight", size[1])
            self.settings.set("panelOffset", offset)
        finally:
            self._host_paused = False
        self._configure_host()

    def _return_focus(self):
        if self.host is not None:
            self.host.returnFocus()

    def _on_key(self, name):
        session = self.session
        if session is None:
            return
        if name == "escape":
            session.cancel_drag()
        elif name in MODES:
            session.set_mode(name)
        else:
            session.run_action(name)

    def _on_setting(self, key, value):
        if key == "placement":
            self.settings.set("panelOffset", (0, 0))   # 置き場所を替えたら、ずれは戻す
        if key in _HOST_KEYS and not self._host_paused:
            self._configure_host()
        if key != "panelOffset":
            tool_ui.refresh()   # パネル・キーで変えたとき、開いているツール設定のウィンドウも合わせる

    def runAction(self, action):
        """コンテキストのコマンドの操作のフラグ (-copyWeights など) から。"""
        if self.session is None:
            log.warning("ツールを有効にしてから実行してください")
            return
        self.session.run_action(action)

    def abortAction(self):
        # Esc を押したとき (ドラッグ中の Esc は ui/keys.py が受け取る。念のため)
        if self.session is not None:
            self.session.cancel_drag()

    # -- 選んであるコンポーネントのクリック ---------------------------------------

    def doPress(self, event, drawMgr, context):
        self._click = None
        if event.mouseButton() == omui.MEvent.kLeftMouse and not (
                event.isModifierShift() or event.isModifierControl()):
            self._click = (event.position, cmds.ls(selection=True) or [])
        omui.MPxSelectionContext.doPress(self, event, drawMgr, context)

    def doRelease(self, event, drawMgr, context):
        omui.MPxSelectionContext.doRelease(self, event, drawMgr, context)
        click, self._click = self._click, None
        if click is None:
            return
        (x0, y0), before = click
        x, y = event.position
        if abs(x - x0) > CLICK_PIXELS or abs(y - y0) > CLICK_PIXELS:
            return   # 矩形選択
        if (cmds.ls(selection=True) or []) != before:
            return   # 選んでいないものをクリックした (今までどおり置き換わった)
        undo_name = cmds.undoInfo(query=True, undoName=True) or ""
        targets = added_by_click(undo_name)
        if targets:
            _defer(lambda: self._replace_selection(targets, undo_name))

    def _replace_selection(self, targets, undo_name):
        """選択を targets だけにする。直前の記録がまだ何も変えていない select -add なら取り消してから。"""
        if _ACTIVE[0] is not self:
            return
        try:
            if (cmds.undoInfo(query=True, undoName=True) or "") == undo_name:
                cmds.undo()
            cmds.select(targets, replace=True)
        except (RuntimeError, ValueError) as error:
            log.warning("選択を置き換えられませんでした: {}".format(error))
