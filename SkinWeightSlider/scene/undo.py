# -*- coding: utf-8 -*-
"""
すでに書いた変更を、1 回の Undo として積む。

    writer.write(after)
    commit(WeightChange(writer, before, after), "joint2 割合 0.484 -> 0.620")

仕組み (旧版と同じ。GUI で確認済み):
- ウェイトはドラッグ中に API で直接書くので、Maya の Undo には載らない。離したときに、変更の前後を
  持つ Undo できるコマンド (skinWeightSliderApply = ApplyWeightsCommand) を 1 つ積む。doIt は何も
  書かず、undoIt / redoIt が前 / 後を書き戻す
- コマンドには Python のオブジェクトを引数で渡せないので、_PENDING に置いてから呼ぶ。プラグインの
  creator はこのモジュールを毎回引いてコマンドを作るので、コマンドとここは同じ _PENDING を見る
- Undo の記録の名前は「実行した MEL の文字列」(Python の cmds で呼ぶと空になる。MPxCommand の
  commandString も効かなかった)。そこで名前用の引数 -n (中身は使わない) を付け、MEL で
  skinWeightSliderApply -n "<名前>" と呼ぶ。Undo すると「Undo: skinWeightSliderApply -n "..."」と出る
- Undo / Redo のあとのパネルの読み直しは、Maya の Undo / Redo のイベント (scene/watch.py)
"""
import maya.api.OpenMaya as om
import maya.mel as mel

from ..constants import UNDO_COMMAND
from .writer import write_lock

__all__ = ["WeightChange", "LockChange", "ApplyWeightsCommand", "commit"]

_PENDING = []


class WeightChange(object):
    """選んだ頂点のウェイトの変更前と変更後 (writer は MultiWeightWriter)。"""

    def __init__(self, writer, before, after):
        self.writer = writer
        self.before = [list(row) for row in before]
        self.after = [list(row) for row in after]

    def redo(self):
        self.writer.write(self.after)

    def undo(self):
        self.writer.write(self.before)


class LockChange(object):
    """インフルエンスのロック (lockInfluenceWeights) の切り替え。"""

    def __init__(self, influence_path, locked):
        self.influence_path = influence_path
        self.after = bool(locked)

    def redo(self):
        write_lock(self.influence_path, self.after)

    def undo(self):
        write_lock(self.influence_path, not self.after)


class ApplyWeightsCommand(om.MPxCommand):
    """変更 (すでに書いてある) を Undo のキューに積むだけのコマンド。"""

    def __init__(self):
        super().__init__()
        self._changes = []

    @staticmethod
    def syntax():
        syntax = om.MSyntax()
        syntax.addFlag("-n", "-name", om.MSyntax.kString)   # Undo の名前にするためだけ
        return syntax

    def doIt(self, args):
        self._changes = list(_PENDING)
        del _PENDING[:]

    def redoIt(self):
        for change in self._changes:
            change.redo()

    def undoIt(self):
        for change in reversed(self._changes):
            change.undo()

    def isUndoable(self):
        return True


def commit(change, label):
    """変更 (すでに書いてある) を 1 回の Undo にする。label は Undo / Redo のときに出る名前。

    change は変更 1 つか、変更のリスト (まとめて 1 回の Undo。ロックをまとめて切り替えるときなど)。
    """
    _PENDING[:] = list(change) if isinstance(change, (list, tuple)) else [change]
    text = label.replace("\\", "/").replace('"', "'")   # MEL の文字列に入れられない文字を避ける
    try:
        mel.eval('{} -n "{}"'.format(UNDO_COMMAND, text))
    finally:
        del _PENDING[:]
