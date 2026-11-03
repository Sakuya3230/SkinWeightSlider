# -*- coding: utf-8 -*-
"""
選んだ頂点の skinCluster を探してウェイトを読む (SkinData)。

    data = read_skin_data(selection, name_style="short", namespace=True)
    data.model            # WeightModel (計算)
    data.writer()         # MultiWeightWriter (書く)

- skinCluster はメッシュのヒストリーから探し、そのメッシュを出力しているもの
  (MFnSkinCluster.indexForOutputShape が通るもの) だけを使う
- getWeights(シェイプ, 頂点のコンポーネント) で選んだ頂点の分だけ読む。配列は頂点ごとに
  その skinCluster の全インフルエンス (influenceObjects() の順)
- 複数のメッシュは、インフルエンスをフルパスでまとめる (列はジョイントの和集合。順は最初のメッシュの
  skinCluster の順、その後ろに次のメッシュで初めて出てきたもの)。そのメッシュの skinCluster に無い
  列は 0 で、WeightModel.available で変えない
- インフルエンスの色は、スキンのペイントの一覧と同じく objectColor (0〜7) + 1 のユーザー定義の色
  (colorIndex -q -userColor。objectColorRGB ではない。mayapy では None なので色は無し)
- 重心は、ソフト選択なら選んだ頂点 (重み 1) だけ。マニピュレータが描くたびに今の位置を読み直す
  (ジョイントを動かすとメッシュが変形するため。頂点が多すぎるときは読んだときの位置のまま)
"""
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import maya.cmds as cmds

from ..core.model import WeightModel
from ..core.smooth import cotangent_weights
from ..core.names import influence_labels
from .selection import mesh_label
from .writer import MultiWeightWriter, vertex_component

__all__ = ["SkinData", "find_skin_cluster", "read_skin_data", "live_center", "LIVE_CENTER_LIMIT",
           "joint_position", "affected_components", "smooth_neighbors", "input_points"]

LIVE_CENTER_LIMIT = 1000   # 重心を描くたびに読み直す頂点の数の上限


def find_skin_cluster(path):
    """メッシュ (シェイプの MDagPath) を変形している skinCluster の MObject。無ければ None。"""
    history = cmds.listHistory(path.fullPathName(), pruneDagObjects=True) or []
    for name in cmds.ls(history, type="skinCluster") or []:
        selection = om.MSelectionList()
        selection.add(name)
        node = selection.getDependNode(0)
        try:
            oma.MFnSkinCluster(node).indexForOutputShape(path.node())
        except RuntimeError:
            continue   # 別のメッシュの skinCluster
        return node
    return None


def _is_locked(path):
    fn = om.MFnDependencyNode(path.node())
    return fn.hasAttribute("liw") and fn.findPlug("liw", False).asBool()


def user_color_palette():
    """ユーザー定義の色 {番号 1〜8: (r, g, b)}。GUI でないと (mayapy では) 空。"""
    palette = {}
    for number in range(1, 9):
        try:
            rgb = cmds.colorIndex(number, query=True, userColor=True)
        except RuntimeError:
            rgb = None
        if rgb and len(rgb) == 3:
            palette[number] = tuple(float(c) for c in rgb)
    return palette


def _influence_color(path, palette):
    fn = om.MFnDependencyNode(path.node())
    if not fn.hasAttribute("objectColor"):
        return None
    return palette.get(fn.findPlug("objectColor", False).asInt() + 1)


def points_center(meshes, live=True):
    """[(MDagPath, [頂点])] の全頂点のワールドの重心 (MPoint)。無ければ None。

    live なら頂点ごとに getPoint で読む (変形したあとの位置。メッシュ全体は読まない)。
    """
    x = y = z = 0.0
    n = 0
    for path, vertices in meshes:
        fn = om.MFnMesh(path)
        if live:
            points = [fn.getPoint(v, om.MSpace.kWorld) for v in vertices]
        else:
            every = fn.getPoints(om.MSpace.kWorld)
            points = [every[v] for v in vertices]
        for p in points:
            x += p.x
            y += p.y
            z += p.z
            n += 1
    return om.MPoint(x / n, y / n, z / n) if n else None


def live_center(meshes):
    return points_center(meshes, live=True)


def joint_position(path):
    """インフルエンス (MDagPath) の今のワールドの位置 (MPoint)。"""
    matrix = path.inclusiveMatrix()
    return om.MPoint(matrix[12], matrix[13], matrix[14])


class SkinData(object):
    """選んだ頂点のウェイトと、Maya 側の情報。

    model            WeightModel (ドラッグ中はセッションが新しいものに替える)
    parts            メッシュごとの dict (skin / path / vertices / columns / start / end)。書き込みに使う
    influence_dags   インフルエンスの MDagPath (列の順)。ジョイントの位置を描くたびに読む
    colors           インフルエンスの色 (列の順。無ければ None)
    normalize_modes  {skinCluster の名前: normalizeWeights (0 なし / 1 インタラクティブ / 2 後で)}
    mesh_counts      [(メッシュの名前, 頂点の数)]
    skipped          スキンが無くて使わなかったメッシュの名前
    skin_names       skinCluster の名前 (重なりなし)
    center           読んだときの重心 (MPoint)
    center_meshes    重心を描くたびに読み直す頂点 [(MDagPath, [頂点])] (多すぎれば [])
    """

    def __init__(self, model, parts):
        self.model = model
        self.parts = parts
        self.influence_dags = []
        self.colors = None
        self.normalize_modes = {}
        self.mesh_counts = []
        self.skipped = []
        self.skin_names = []
        self.center = None
        self.center_meshes = []
        self._writer = None

    def writer(self):
        if self._writer is None:
            self._writer = MultiWeightWriter(self.parts)
        return self._writer

    def skin_nodes(self):
        """skinCluster の MObject (重なりなし)。"""
        nodes = []
        for part in self.parts:
            if all(part["skin"] != other for other in nodes):
                nodes.append(part["skin"])
        return nodes


def affected_components(data, index):
    """インフルエンス index の影響を受ける (ウェイトが 0 でない) 頂点の名前のリスト。

    選んだ頂点の skinCluster (複数のメッシュならそれぞれ) の、メッシュ全体から探す
    (MFnSkinCluster.getPointsAffectedByInfluence)。
    """
    key = data.model.keys[index]
    names = []
    for skin in data.skin_nodes():
        fn = oma.MFnSkinCluster(skin)
        for influence in fn.influenceObjects():
            if influence.fullPathName() != key:
                continue
            selection, _weights = fn.getPointsAffectedByInfluence(influence)
            names.extend(selection.getSelectionStrings())
    return names


def input_points(skin, shape):
    """skinCluster に入ってくる (スキンで変形する前の) メッシュの頂点の位置 (MPointArray。オブジェクト空間)。

    skinCluster の input[n].inputGeometry (n は indexForOutputShape) のメッシュのデータ。バインドしたときの形
    (ブレンドシェイプなど skinCluster より前の変形があれば、それを通したあと)。読めなければ None。
    変形したあとの位置で距離を測ると、ウェイトで伸び縮みした形の距離になり、元の形に沿ったスムーズに
    ならない (ユーザーの指摘) ので、距離に応じたスムーズはこの位置で測る。
    """
    try:
        fn = oma.MFnSkinCluster(skin)
        index = fn.indexForOutputShape(shape)
        plug = fn.findPlug("input", False).elementByLogicalIndex(index).child(fn.attribute("inputGeometry"))
        geometry = plug.asMObject()   # 変数に持ってから MFnMesh に渡す
        if geometry.isNull() or not geometry.hasFn(om.MFn.kMeshData):
            return None
        return om.MFnMesh(geometry).getPoints(om.MSpace.kObject)
    except RuntimeError:
        return None


def smooth_neighbors(data, with_distances=False, with_cotangents=False):
    """スムーズに使う隣の頂点 (core/smooth.smooth_weights の neighbors と outside)。

    with_distances なら、隣ごとの距離 (neighbors と同じ並び) も返す: (neighbors, outside, distances)。
    with_cotangents なら、隣ごとのコタンジェントの重み (core/smooth.cotangent_weights) を返す:
    (neighbors, outside, weights)。選んだ頂点のまわりの面を三角形に分け (MItMeshPolygon.getTriangles)、
    角を測る。距離・角はスキンで変形する前の形 (input_points) で測る。読めなければ今のワールドの位置。

    隣は辺でつながった頂点 (MItMeshVertex.getConnectedVertices)。選んだ頂点ならその行の番号、
    選んでいない頂点は outside に足して「行の数 + その番号」。outside のウェイトは getWeights でまとめて読み、
    model の列の並びに直す (その skinCluster に無い列は 0)。
    """
    count = len(data.model.weights)
    neighbors = [[] for _ in range(count)]
    distances = [[] for _ in range(count)]
    cotangents = [[] for _ in range(count)]
    outside = []
    for part in data.parts:
        path = om.MDagPath(part["path"])
        rows = dict((v, part["start"] + k) for k, v in enumerate(part["vertices"]))
        iterator = om.MItMeshVertex(path)   # path は変数に持ってから渡す (MItMesh の落とし穴)
        points = None
        if with_distances or with_cotangents:
            points = input_points(part["skin"], path.node())
            if points is None:
                points = om.MFnMesh(path).getPoints(om.MSpace.kWorld)
        extra = {}   # 選んでいない頂点 -> outside の番号
        around = []  # コタンジェント: [(行, 頂点, [隣の頂点])]
        faces = set()
        for v, r in rows.items():
            iterator.setIndex(v)
            connected = list(iterator.getConnectedVertices())
            if with_cotangents:
                around.append((r, v, connected))
                faces.update(iterator.getConnectedFaces())
            for other in connected:
                if with_distances:
                    distances[r].append((points[other] - points[v]).length())
                if other in rows:
                    neighbors[r].append(rows[other])
                else:
                    if other not in extra:
                        extra[other] = count + len(outside) + len(extra)
                    neighbors[r].append(extra[other])
        if with_cotangents:
            triangles, used = _triangles(path, faces)
            positions = dict((v, (points[v].x, points[v].y, points[v].z)) for v in used)
            weights = cotangent_weights([(v, near) for _r, v, near in around], triangles, positions)
            for (r, _v, _near), row in zip(around, weights):
                cotangents[r] = row
        if not extra:
            continue
        ordered = sorted(extra, key=extra.get)
        component = vertex_component(ordered)
        flat, size = oma.MFnSkinCluster(part["skin"]).getWeights(path, component)
        width = len(data.model.influences)
        for k in range(len(ordered)):
            row = [0.0] * width
            for local, column in enumerate(part["columns"]):
                row[column] = flat[k * size + local]
            outside.append(row)
    if with_cotangents:
        return neighbors, outside, cotangents
    if with_distances:
        return neighbors, outside, distances
    return neighbors, outside


def _triangles(path, faces):
    """面 (番号の集合) を三角形に分けた、頂点の番号の 3 つ組のリストと、使った頂点の集合。"""
    polygon = om.MItMeshPolygon(path)   # path は変数に持ってから渡す
    triangles = []
    used = set()
    for face in sorted(faces):
        polygon.setIndex(face)
        _points, ids = polygon.getTriangles(om.MSpace.kObject)
        ids = list(ids)
        for k in range(0, len(ids) - 2, 3):
            triangles.append((ids[k], ids[k + 1], ids[k + 2]))
            used.update(ids[k:k + 3])
    return triangles, used


def _hard_meshes(parts, strengths):
    """重心に使う頂点 [(MDagPath, [頂点])]。ソフト選択なら選んだ頂点 (重み 1) だけ。"""
    meshes = []
    for part in parts:
        rows = range(part["start"], part["end"])
        vertices = [v for row, v in zip(rows, part["vertices"])
                    if strengths is None or strengths[row] >= 1.0 - 1e-6]
        meshes.append((part["path"], vertices))
    if not any(vertices for _path, vertices in meshes):
        meshes = [(part["path"], part["vertices"]) for part in parts]
    return meshes


def read_skin_data(selection, name_style="short", namespace=True):
    """選んだ頂点 (VertexSelection) の SkinData。頂点が無い・どれにもスキンが無ければ None。"""
    union_paths, union_dags, union_index = [], [], {}
    locals_, parts, vertices, row_keys, skins, skipped, mesh_counts = [], [], [], [], [], [], []
    normalize_modes = {}
    for path, mesh_vertices in selection.meshes:
        skin = find_skin_cluster(path)
        if skin is None:
            skipped.append(mesh_label(path))
            continue
        fn = oma.MFnSkinCluster(skin)
        columns = []
        for influence in fn.influenceObjects():
            key = influence.fullPathName()
            if key not in union_index:
                union_index[key] = len(union_paths)
                union_paths.append(key)
                union_dags.append(om.MDagPath(influence))
            columns.append(union_index[key])
        component = vertex_component(mesh_vertices)   # 変数に持ってから渡す
        flat, count = fn.getWeights(path, component)
        start = len(vertices)
        locals_.append(([list(flat[i * count:(i + 1) * count]) for i in range(len(mesh_vertices))],
                        columns))
        vertices.extend(mesh_vertices)
        full = path.fullPathName()
        row_keys.extend((full, v) for v in mesh_vertices)
        parts.append({"skin": skin, "path": om.MDagPath(path), "vertices": list(mesh_vertices),
                      "columns": columns, "start": start, "end": len(vertices)})
        if fn.name() not in skins:
            skins.append(fn.name())
            plug = fn.findPlug("normalizeWeights", False)
            normalize_modes[fn.name()] = plug.asInt()
        mesh_counts.append((mesh_label(path), len(mesh_vertices)))
    if not parts:
        return None
    strengths = []
    for part in parts:
        strengths.extend(selection.strengthsOf(part["path"], part["vertices"]))
    weights, available = [], []
    for local_rows, columns in locals_:
        for local in local_rows:
            row = [0.0] * len(union_paths)
            for k, column in enumerate(columns):
                row[column] = local[k]
            weights.append(row)
            available.append(columns)
    soft = any(value < 1.0 - 1e-9 for value in strengths)
    model = WeightModel(influence_labels(union_paths, name_style, namespace),
                        [_is_locked(p) for p in union_dags], vertices, weights,
                        None if len(parts) == 1 else available, strengths if soft else None,
                        keys=union_paths, row_keys=row_keys)
    data = SkinData(model, parts)
    data.influence_dags = union_dags
    palette = user_color_palette()
    colors = [_influence_color(p, palette) for p in union_dags]
    data.colors = colors if any(c is not None for c in colors) else None
    data.normalize_modes = normalize_modes
    data.mesh_counts = mesh_counts
    data.skipped = skipped
    data.skin_names = skins
    meshes = _hard_meshes(parts, model.strengths)
    data.center = points_center(meshes, live=False)
    count = sum(len(v) for _path, v in meshes)
    data.center_meshes = meshes if count <= LIVE_CENTER_LIMIT else []
    return data
