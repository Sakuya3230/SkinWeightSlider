# -*- coding: utf-8 -*-
"""
選択・ウェイト・ロックの変更の通知 (Maya のコールバック)。

    watcher = SceneWatcher(on_selection, on_weights)
    watcher.start()               # ツールを有効にしたとき
    watcher.watch(data)           # 読んだ skinCluster とインフルエンスを見る (読むたびに付け替える)
    watcher.stop()                # ツールを無効にしたとき (必ず外す。残すと古いコードが呼ばれ続ける)

通知:
    on_selection()  選択が変わった (SelectionChanged)・ソフト選択の設定が変わった
                    (softSelectOptionsChanged。範囲を変えても SelectionChanged は来ないことがある)
    on_weights()    Undo / Redo (イベント)、外 (Component Editor・ペイント・skinPercent・スクリプト) で
                    ウェイト (skinCluster の weightList[n].weights)・ロック (lockInfluenceWeights)・
                    色 (objectColor) を変えた (MNodeMessage.addAttributeChangedCallback。旧版の mayapy で
                    届くことを確認。ジョイントの移動も届くが、除いている)
自分の書き込み (scene/writer.py の writing の中) の通知は無視する。通知はまとめて何度も来るので、
受け取る側 (tool/session.py) が後で 1 回にまとめる。
"""
import maya.api.OpenMaya as om

from .writer import is_writing

__all__ = ["SceneWatcher"]

_INFLUENCE_ATTRIBUTES = ("lockInfluenceWeights", "objectColor")


class SceneWatcher(object):
    def __init__(self, on_selection, on_weights):
        self._on_selection = on_selection
        self._on_weights = on_weights
        self._events = []
        self._nodes = []

    def start(self):
        self.stop()
        for name in ("SelectionChanged", "softSelectOptionsChanged"):
            self._events.append(om.MEventMessage.addEventCallback(name, self._selection_changed))
        for name in ("Undo", "Redo"):
            self._events.append(om.MEventMessage.addEventCallback(name, self._weights_changed))

    def stop(self):
        self.unwatch()
        _remove(self._events)
        self._events = []

    def watch(self, data):
        """data (SkinData) の skinCluster とインフルエンスを見る (前のものは外す)。None なら外すだけ。"""
        self.unwatch()
        if data is None:
            return
        for skin in data.skin_nodes():
            self._nodes.append(om.MNodeMessage.addAttributeChangedCallback(skin, self._skin_changed))
        for path in data.influence_dags:
            try:
                node = path.node()
            except RuntimeError:
                continue
            self._nodes.append(om.MNodeMessage.addAttributeChangedCallback(node, self._influence_changed))

    def unwatch(self):
        _remove(self._nodes)
        self._nodes = []

    def _selection_changed(self, *args):
        self._on_selection()

    def _weights_changed(self, *args):
        self._on_weights()

    def _skin_changed(self, message, plug, other, data):
        if message & om.MNodeMessage.kAttributeSet and not is_writing() \
                and plug.partialName().startswith("wl"):
            self._on_weights()

    def _influence_changed(self, message, plug, other, data):
        if not message & om.MNodeMessage.kAttributeSet or is_writing():
            return
        if plug.partialName(False, False, False, False, False, True) in _INFLUENCE_ATTRIBUTES:
            self._on_weights()


def _remove(callbacks):
    for callback in callbacks:
        try:
            om.MMessage.removeCallback(callback)
        except RuntimeError:
            pass
