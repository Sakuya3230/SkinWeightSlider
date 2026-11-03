# -*- coding: utf-8 -*-
"""
選んだ頂点 (VertexSelection) と、頂点の選択モードへの切り替え。

    selection = selected_vertices()      # ソフト選択がオンなら範囲と重みも
    selection.meshes                     # [(シェイプの MDagPath, [頂点の番号]), ...]

- エッジ・フェース・頂点フェースを選んだら、それに含まれる頂点として扱う。複数のメッシュでもよい
- 選択は MGlobal.getActiveSelectionList() ではなく、cmds.ls の文字列ごとに別の MSelectionList で読む。
  MSelectionList は同じメッシュの頂点とフェースを 1 項目にまとめ、getComponent() が最初の種類しか
  返さないため (フェースの頂点が抜けた。旧版で確認)
- ソフト選択がオンなら MGlobal.getRichSelection() で範囲の頂点と重み (選んだ頂点は 1) を読む。
  エッジ・フェースを選んでも頂点のコンポーネントで返る (mayapy で確認)
- メッシュをオブジェクトとして選んでいるだけなら、そのメッシュは含めない
"""
import maya.api.OpenMaya as om
import maya.cmds as cmds

__all__ = ["VertexSelection", "component_vertices", "selected_vertices", "soft_select_enabled",
           "soft_selected_vertices", "mesh_label", "added_by_click", "selected_mesh_transform",
           "needs_vertex_mode", "enter_vertex_mode", "select_names"]


def component_vertices(path, component):
    """コンポーネント (頂点・エッジ・フェース・頂点フェース) に含まれる頂点の番号の集合。扱えなければ None。"""
    kind = component.apiType()
    mesh = om.MFnMesh(path)
    try:
        if kind == om.MFn.kMeshVtxFaceComponent:
            return set(om.MFnDoubleIndexedComponent(component).getElements()[0])
        elements = om.MFnSingleIndexedComponent(component).getElements()
        if kind == om.MFn.kMeshVertComponent:
            return set(elements)
        vertices = set()
        if kind == om.MFn.kMeshEdgeComponent:
            for e in elements:
                vertices.update(mesh.getEdgeVertices(e))
            return vertices
        if kind == om.MFn.kMeshPolygonComponent:
            for f in elements:
                vertices.update(mesh.getPolygonVertices(f))
            return vertices
    except (RuntimeError, TypeError, ValueError):
        pass
    return None


def mesh_label(path):
    """シェイプの MDagPath から表示に使う名前 (トランスフォームの短い名前)。"""
    transform = om.MDagPath(path)
    transform.pop()
    return transform.partialPathName()


class VertexSelection(object):
    """選んだ頂点。meshes は [(シェイプの MDagPath, 頂点の番号の昇順のリスト)] (選んだ順)。

    strengths はソフト選択の重み: {メッシュのフルパス: {頂点: 重み}}。含まれない頂点は 1。
    """

    def __init__(self, meshes=(), strengths=None):
        self.meshes = [(om.MDagPath(path), sorted(vertices)) for path, vertices in meshes if vertices]
        self.strengths = strengths or {}

    def strengthsOf(self, path, vertices):
        table = self.strengths.get(path.fullPathName(), {})
        return [table.get(v, 1.0) for v in vertices]

    def isEmpty(self):
        return not self.meshes

    def vertexCount(self):
        return sum(len(vertices) for _path, vertices in self.meshes)


def _mesh_path(path):
    if path.apiType() != om.MFn.kMesh:
        path.extendToShape()   # コンポーネントの持ち主は普通シェイプだが、念のため
    return path if path.apiType() == om.MFn.kMesh else None


def soft_select_enabled():
    try:
        return bool(cmds.softSelect(query=True, softSelectEnabled=True))
    except RuntimeError:
        return False


def selected_vertices():
    """今の選択から、メッシュごとの選んだ頂点 (VertexSelection)。"""
    if soft_select_enabled():
        return soft_selected_vertices()
    order, found = [], {}
    for text in cmds.ls(selection=True) or []:
        selection = om.MSelectionList()
        try:
            selection.add(text)
            item_path, component = selection.getComponent(0)
        except (RuntimeError, TypeError):
            continue   # DAG ノードでないもの (マテリアルなど)
        if component.isNull():
            continue   # オブジェクトの選択
        path = _mesh_path(item_path)
        if path is None:
            continue   # NURBS のコントロールポイントなど
        name = path.fullPathName()
        if name not in found:
            order.append(name)
            found[name] = (om.MDagPath(path), set())
        vertices = component_vertices(path, component)
        if vertices:
            found[name][1].update(vertices)
    return VertexSelection([found[name] for name in order])


def soft_selected_vertices():
    """ソフト選択がオンのとき: 範囲の頂点と重み (同じ頂点が何度か出たら大きい重み。0 は除く)。"""
    selection = om.MGlobal.getRichSelection().getSelection()
    order, found, strengths = [], {}, {}
    for i in range(selection.length()):
        try:
            item_path, component = selection.getComponent(i)
        except (RuntimeError, TypeError):
            continue
        if component.isNull():
            continue
        path = _mesh_path(item_path)
        if path is None:
            continue
        name = path.fullPathName()
        if name not in found:
            order.append(name)
            found[name] = (om.MDagPath(path), set())
            strengths[name] = {}
        table = strengths[name]
        if component.apiType() == om.MFn.kMeshVertComponent:
            fn = om.MFnSingleIndexedComponent(component)
            weighted = fn.hasWeights
            for k in range(fn.elementCount):
                v = fn.element(k)
                found[name][1].add(v)
                table[v] = max(table.get(v, 0.0), fn.weight(k).influence if weighted else 1.0)
        else:
            for v in component_vertices(path, component) or ():
                found[name][1].add(v)
                table[v] = 1.0
    meshes = []
    for name in order:
        path, vertices = found[name]
        meshes.append((path, set(v for v in vertices if strengths[name].get(v, 0.0) > 1e-6)))
    return VertexSelection(meshes, strengths)


def added_by_click(undo_name):
    """Undo の記録の名前が「select -add <対象> ...」なら対象の名前のリスト。違えば []。

    選んであるコンポーネントをクリックすると、MPxSelectionContext は Maya に「select -add <対象>」を
    実行させる (選んでいないものなら select -r。旧版の実機のログで確認)。何も変わらないので、
    コンテキストがクリックしたものだけの選択に置き換える。cmds.undoInfo(q=True, undoName=True) は
    引数まで含む文字列を返す (mayapy で確認)。
    """
    parts = undo_name.split()
    if len(parts) < 3 or parts[0] != "select" or parts[1] != "-add":
        return []
    return [part for part in parts[2:] if not part.startswith("-")]


def select_names(names):
    """名前 (ノード・コンポーネント) のリストだけを選ぶ (1 回の Undo)。"""
    cmds.select(names, replace=True)


def selected_mesh_transform():
    """オブジェクトとして選んでいる、メッシュを持つ最初のトランスフォームの名前 (無ければ None)。"""
    for name in cmds.ls(selection=True, objectsOnly=True, long=True) or []:
        if cmds.nodeType(name) == "mesh":
            parents = cmds.listRelatives(name, parent=True, fullPath=True) or []
            return parents[0] if parents else None
        if cmds.listRelatives(name, shapes=True, type="mesh", fullPath=True, noIntermediate=True):
            return name
    return None


def needs_vertex_mode(transform):
    """メッシュ transform を、頂点を選べる状態にする必要があるか (選択のモード・マスクは GUI の状態)。"""
    if transform not in (cmds.ls(hilite=True, long=True) or []):
        return True
    if cmds.selectMode(query=True, object=True):
        return not cmds.selectType(query=True, objectComponent=True, vertex=True)
    return not cmds.selectType(query=True, vertex=True)


def enter_vertex_mode(transform):
    """メッシュを頂点の選択モードにする (マーキングメニューの「頂点」と同じことを cmds で)。

    MEL の doMenuComponentSelection (dagMenuProc.mel) は、右クリックのマーキングメニューを一度も
    使っていないと読み込まれておらず「Cannot find procedure」になった (旧版で確認)。
    """
    if cmds.selectMode(query=True, object=True):
        cmds.selectType(objectComponent=True, allComponents=False)
        cmds.selectType(objectComponent=True, vertex=True)
        cmds.selectType(vertex=True)
    else:
        cmds.selectType(allComponents=False)
        cmds.selectType(vertex=True)
    cmds.hilite(transform)
