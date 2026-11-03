# -*- coding: utf-8 -*-
"""
マニピュレータ: ビューに、選んだ頂点の重心から強調しているインフルエンス (パネルで乗せている行・
ドラッグしている行) のジョイントへの線と、ジョイントの位置の四角と名前、頂点ごとのウェイトの色の点を描く。

    manip, node = omui.MPxManipulatorNode.newManipulator(MANIP_NODE)
    manip.session = session      # 描くものは session.guide() から
    context.addManipulator(node)

旧版はパネルもマニピュレータで描き、押せる部品のために 3D の板 (ScreenPlane) を使っていた
(2D で描いたものはハンドルにならないため)。パネルを Qt にしたので、マニピュレータは押せる部品を
持たない。ビューのクリックはすべて普段の選択になり、描くものは 2D (line2d / rect2d / text2d) で済む。

- preDrawUI(view) は描く直前に呼ばれ、M3dView を受け取る。ここで重心とジョイントを画面に投影する。
  ジョイントの位置は描くたびに MDagPath.inclusiveMatrix で読み、重心も頂点の今の位置から読み直す
  (ジョイントを動かすとメッシュが変形するため。頂点が多いときは読んだときの位置のまま)
- 色はカラーマネジメントの変換を通る (2D・文字も) ので、display_color で打ち消して渡す
- 線は名前の箱で切り取る (奥行きの順に頼らない。背景と線の切れ目が一致する)
- プラグをつながないので connectToDependNode / finishAddingManips は呼ばない (つながずに
  finishAddingManips を呼ぶと kFailure になった。旧版で確認)
- ウェイトの色 (設定 weightDisplay): 強調しているインフルエンスの、選んだ頂点 (ソフト選択の範囲も) の
  ウェイトを、頂点の位置の点の色で出す (core/guide.weight_color。色は段階に丸めて、打ち消す変換を
  段階ごとに覚える)。点は 3D (頂点の今の位置。描くたびに読む) で、面より手前に出るよう、点の奥行きの
  優先度 (sActivePointDepthPriority) で描く。ドラッグ中はドラッグで変えた値が出る。
  マニピュレータの点はメッシュの陰でも透けて見えた (GUI で確認) ので、頂点の法線がカメラのほうを
  向いていない (裏の) 頂点は出さない (設定 weightBackfaces で出す。ほかの物の陰は隠さない)
"""
import maya.api.OpenMaya as om
import maya.api.OpenMayaRender as omr
import maya.api.OpenMayaUI as omui

from ..core.guide import (JOINT_PIXELS, faces_camera, label_box, label_text, segment_outside_rect,
                          weight_color)
from ..scene.colors import color_management_key, display_color
from ..scene.skin import joint_position, live_center

__all__ = ["GuideManip", "LABEL_BACKGROUND_ALPHA", "CENTER_PIXELS", "POINT_GETPOINT_LIMIT"]

LABEL_BACKGROUND_ALPHA = 0.85   # 名前の背景の不透明度 (少し透ける)
CENTER_PIXELS = 3               # 重心の点の半分の大きさ
LINE_WIDTH = 2.0
POINT_GETPOINT_LIMIT = 3000     # これより多い頂点のメッシュは、頂点ごとでなくまとめて位置を読む


def vertex_positions(path, vertices):
    """メッシュの頂点の今のワールドの位置 (MPoint のリスト)。"""
    fn = om.MFnMesh(path)
    if len(vertices) <= POINT_GETPOINT_LIMIT:
        return [fn.getPoint(v, om.MSpace.kWorld) for v in vertices]
    every = fn.getPoints(om.MSpace.kWorld)
    return [every[v] for v in vertices]


def vertex_normals(path, vertices):
    """メッシュの頂点の今のワールドの法線 (MVector のリスト。角度で重みを付けた平均)。"""
    fn = om.MFnMesh(path)
    if len(vertices) <= POINT_GETPOINT_LIMIT:
        return [fn.getVertexNormal(v, True, om.MSpace.kWorld) for v in vertices]
    every = fn.getVertexNormals(True, om.MSpace.kWorld)
    return [every[v] for v in vertices]


def camera_of(view):
    """ビューのカメラの (位置, 視線の向き)。透視なら位置 (視線は None)、平行投影なら視線 (位置は None)。"""
    camera = om.MFnCamera(view.getCamera())
    if camera.isOrtho():
        return None, tuple(camera.viewDirection(om.MSpace.kWorld))
    return tuple(camera.eyePoint(om.MSpace.kWorld))[:3], None


def weight_points(points, key, camera=None):
    """[(MDagPath, [頂点], [ウェイト])] から、点の位置と色 (MPointArray, MColorArray)。

    camera ((位置, 視線) 。camera_of) を渡すと、裏を向いた頂点を除く。
    """
    positions = om.MPointArray()
    colors = om.MColorArray()
    for path, vertices, weights in points:
        places = vertex_positions(path, vertices)
        normals = vertex_normals(path, vertices) if camera is not None else [None] * len(places)
        for position, normal, weight in zip(places, normals, weights):
            if normal is not None and not faces_camera(
                    (position.x, position.y, position.z), (normal.x, normal.y, normal.z), *camera):
                continue
            positions.append(position)
            colors.append(om.MColor(display_color(weight_color(weight), key)))
    return positions, colors


class GuideManip(omui.MPxManipulatorNode):
    def __init__(self):
        super().__init__()
        self.session = None
        self._draw = None   # preDrawUI で決めた、描くもの (dict)

    @staticmethod
    def initialize():
        pass   # アトリビュートは持たない

    def preDrawUI(self, view):
        self._draw = None
        session = self.session
        guide = session.guide() if session is not None else None
        if guide is None:
            return
        settings = session.settings
        key = color_management_key()
        draw = {"line": None, "points": None, "point_size": settings.value("weightPointSize")}
        if guide.points:
            try:
                camera = None if settings.value("weightBackfaces") else camera_of(view)
                draw["points"] = weight_points(guide.points, key, camera)
            except RuntimeError:
                pass   # メッシュが消えたなど
        if guide.show_line:
            draw["line"] = self._line(view, guide, settings, key)
        if draw["points"] is not None or draw["line"] is not None:
            self._draw = draw

    def _line(self, view, guide, settings, key):
        """重心からジョイントへの線と名前 (画面の位置)。ジョイントが映っていなければ None。"""
        center = guide.center
        if guide.center_meshes:
            try:
                center = live_center(guide.center_meshes) or center
            except RuntimeError:
                pass
        try:
            joint = joint_position(guide.joint)
        except RuntimeError:
            return None
        cx, cy, center_visible = view.worldToView(center)
        jx, jy, joint_visible = view.worldToView(joint)
        if not joint_visible:
            return None   # ジョイントがカメラの後ろ
        return {
            "center": (cx, cy) if center_visible else None,
            "joint": (jx, jy),
            "name": guide.name,
            "size": settings.value("labelSize"),
            "background": settings.value("labelBackground"),
            "colors": [display_color(settings.value(name), key) for name in
                       ("lineColor", "labelColor", "labelBackgroundColor")],
        }

    def drawUI(self, drawMgr, frameContext):
        draw = self._draw
        if draw is None:
            return
        if draw["points"] is not None:
            positions, colors = draw["points"]
            drawMgr.beginDrawable(omr.MUIDrawManager.kNonSelectable, 0)
            drawMgr.setDepthPriority(omr.MRenderItem.sActivePointDepthPriority)   # 面より手前
            drawMgr.setPointSize(float(draw["point_size"]))
            drawMgr.mesh(omr.MUIDrawManager.kPoints, positions, None, colors)
            drawMgr.endDrawable()
        if draw["line"] is not None:
            self._draw_line(drawMgr, draw["line"])

    def _draw_line(self, drawMgr, draw):
        line, text_color, background = draw["colors"]
        jx, jy = draw["joint"]
        text = label_text(draw["name"])
        box = label_box(jx, jy, text, draw["size"])
        drawMgr.beginDrawable(omr.MUIDrawManager.kNonSelectable, 0)
        drawMgr.setColor(om.MColor(line))
        drawMgr.setLineWidth(LINE_WIDTH)
        if draw["center"] is not None:
            for start, end in segment_outside_rect(draw["center"], (jx, jy), box):
                drawMgr.line2d(om.MPoint(start[0], start[1]), om.MPoint(end[0], end[1]))
            cx, cy = draw["center"]
            drawMgr.rect2d(om.MPoint(cx, cy), om.MVector(0, 1, 0), CENTER_PIXELS, CENTER_PIXELS, True)
        drawMgr.rect2d(om.MPoint(jx, jy), om.MVector(0, 1, 0), JOINT_PIXELS, JOINT_PIXELS, True)
        # 名前: 箱の左下に置く text2d。背景を付けないときは透明の箱 (箱を渡すと文字が上下の中心に来る)
        drawMgr.setFontSize(int(draw["size"]))
        drawMgr.setFontWeight(omr.MUIDrawManager.kWeightNormal)   # 指定しないと太く詰まって見えた
        drawMgr.setColor(om.MColor(text_color))
        if draw["background"]:
            box_color = om.MColor(tuple(background) + (LABEL_BACKGROUND_ALPHA,))
        else:
            box_color = om.MColor((0.0, 0.0, 0.0, 0.0))
        left, bottom, right, top = box
        drawMgr.text2d(om.MPoint(left, bottom), text, omr.MUIDrawManager.kLeft,
                       [int(right - left), int(top - bottom)], box_color)
        drawMgr.endDrawable()
