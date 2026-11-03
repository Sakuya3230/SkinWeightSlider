# -*- coding: utf-8 -*-
"""
ウェイト・ロックを書く (Undo には載らない。1 回の Undo にまとめるのは scene/undo.py)。

    writer = MultiWeightWriter(data.parts)
    writer.write(weights)          # WeightModel の行・列の並び
    with writing(): ...            # 自分の書き込み (変更の通知で読み直さない)

- MFnSkinCluster.setWeights(シェイプ, 頂点のコンポーネント, インフルエンスの番号, ウェイト,
  normalize=False) で書く。合計は WeightModel が保つので、Maya には正規化させない
- 複数のメッシュでは、行をメッシュごとに分け、和集合の列からその skinCluster の列の並びに取り出す
- 頂点のコンポーネントは変数に持っておく (MItMesh と同じく、一時オブジェクトを渡さない用心)
"""
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

__all__ = ["writing", "is_writing", "vertex_component", "WeightWriter", "MultiWeightWriter",
           "write_lock"]

_WRITING = [0]


class writing(object):
    """with writing(): の中の書き込みを「自分の書き込み」にする (入れ子でもよい)。

    scene/watch.py は、この間に届いたウェイト・ロックの変更の通知を無視する (ドラッグ中に毎回
    読み直さないため)。
    """

    def __enter__(self):
        _WRITING[0] += 1

    def __exit__(self, *args):
        _WRITING[0] -= 1


def is_writing():
    return _WRITING[0] > 0


def vertex_component(vertices):
    fn = om.MFnSingleIndexedComponent()
    component = fn.create(om.MFn.kMeshVertComponent)
    fn.addElements(list(vertices))
    return component


class WeightWriter(object):
    """1 つのメッシュの選んだ頂点のウェイトを、その skinCluster に書く。"""

    def __init__(self, skin_node, path, vertices, influence_count):
        self.fn = oma.MFnSkinCluster(skin_node)
        self.path = om.MDagPath(path)
        self.component = vertex_component(vertices)
        self.influences = om.MIntArray(list(range(influence_count)))

    def write(self, weights):
        flat = om.MDoubleArray([value for row in weights for value in row])
        with writing():
            self.fn.setWeights(self.path, self.component, self.influences, flat, normalize=False)


class MultiWeightWriter(object):
    """複数のメッシュに書く。parts は scene/skin.py の SkinData.parts。"""

    def __init__(self, parts):
        self.parts = [(WeightWriter(part["skin"], part["path"], part["vertices"], len(part["columns"])),
                       part["columns"], part["start"], part["end"]) for part in parts]

    def write(self, weights):
        for writer, columns, start, end in self.parts:
            writer.write([[row[c] for c in columns] for row in weights[start:end]])


def write_lock(influence_path, locked):
    """インフルエンス (フルパス) の lockInfluenceWeights を書く。MPlug で直接 (Undo は scene/undo.py)。"""
    selection = om.MSelectionList()
    selection.add(influence_path)
    fn = om.MFnDependencyNode(selection.getDependNode(0))
    with writing():
        fn.findPlug("liw", False).setBool(bool(locked))
