# -*- coding: utf-8 -*-
"""
ツールの状態と操作 (WeightSession)。パネル (Qt) とコンテキストのあいだに立つ。

    session = WeightSession(settings, defer=QTimer で後回しにする関数)
    session.addListener(listener)        # listener(view_only) 表示を更新する
    session.read_selection()             # 選択を読む (選択が変わったとき)
    session.press(index, value, ctrl, shift) / move(...) / release()   # 行のドラッグ
    session.panel_state()                # パネルに出す内容 (core/panel_state.PanelState)
    session.guide()                      # ジョイントへの線と名前 (マニピュレータが描く)

旧版はこの中身がマニピュレータ (描画・ハンドル) とコンテキストに分かれていた。パネルを Qt にした
ので、操作の中身はここ 1 か所に集め、パネル・キー・ツール設定のコマンドは、どれもここを呼ぶ。
Qt を使わない (後回しは defer で受け取る) ので、mayapy でそのまま検査できる。

決まりごと (旧版から引き継いだもの。GUI で確認済み):
- 操作を始めるときは、必ず skinCluster から読み直す (外で変えた分を、古い値から計算して戻さない)
- ドラッグは、押したときのウェイトから毎回計算し直して書く (行き来しても誤差が溜まらない)。
  離したら、押す前後を 1 回の Undo にする。Esc で押す前に戻す (Undo には積まない)
- 割合モードで平均が 0 の行は、そのドラッグだけ加算で動かす
- 移動モード: 行をクリック (動かさずに離す) で相手を選ぶ / 外す。別の行をドラッグで相手とのあいだで移す
- 編集のあとの後始末 (最大インフルエンス数・刈り取り) は、その編集と同じ 1 回の Undo
- 行の並びは、選択を変えたとき・並び順を変えたときだけ並べ直す (Undo などで入れ替わらない)
- 「＋」で足した (0 でも出す) インフルエンスと、移動の相手は、フルパスで覚え、選択を変えても保つ
"""
from .. import log
from ..core.cleanup import InfluenceLimitMemory, changed_rows, cleanup_weights
from ..core.clipboard import CLIPBOARD
from ..core.modes import (INPUT_SYMBOLS, MODE_ABSOLUTE, MODE_ADD, MODE_LABELS, MODE_MOVE, MODE_SCALE, MODES,
                          drag_step, format_threshold, parse_input, snap_value)
from ..core.model import keep_order, visible_order
from ..core.panel_state import build_panel_state, empty_message, normalize_warnings
from ..core.smooth import SMOOTH_COTANGENT, SMOOTH_DISTANCE, inverse_distance_weights, smooth_weights
from ..scene.selection import VertexSelection, mesh_label, select_names, selected_vertices
from ..scene.skin import affected_components, find_skin_cluster, read_skin_data, smooth_neighbors
from ..scene.undo import LockChange, WeightChange, commit

__all__ = ["WeightSession", "Drag", "Guide", "MOVE_CLICK_PIXELS"]

MOVE_CLICK_PIXELS = 3   # 移動モードで、これより動かしたらドラッグ (動かさなければクリック)

# 設定が変わったときの反応
_RELOAD_KEYS = ("sort", "nameStyle", "namespace")             # 読み直して並べ直す
_LIMIT_KEYS = ("maxInfluencesEnabled", "maxInfluences")       # 元のウェイトから最大数を反映し直す
_VIEW_KEYS = ("hoverName", "labelSize", "labelBackground", "lineColor", "labelColor",
              "labelBackgroundColor", "weightDisplay", "weightPointSize", "weightBackfaces")                         # ビューの描画だけ


class Drag(object):
    """行のドラッグ。base は押したときの WeightModel。pending は移動モードでまだクリックかも分からない。"""

    def __init__(self, index, mode, base, pending=False):
        self.index = index
        self.mode = mode
        self.base = base
        self.pending = pending
        self.value = None   # マウスの位置の値 (刻みに丸めたもの)


class Guide(object):
    """マニピュレータが描くもの: 重心からジョイントへの線とジョイントの名前 (show_line)、
    頂点ごとのウェイトの色の点 (points)。"""

    def __init__(self, center_meshes, center, joint, name, show_line=True, points=None):
        self.center_meshes = center_meshes   # 描くたびに読み直す頂点 (多ければ [])
        self.center = center                 # 読んだときの重心 (MPoint)
        self.joint = joint                   # インフルエンスの MDagPath
        self.name = name                     # 表示名 (省かない)
        self.show_line = show_line           # 線と名前を出すか (設定 hoverName)
        self.points = points or []           # [(シェイプの MDagPath, [頂点], [ウェイト])] (設定 weightDisplay)


class WeightSession(object):
    def __init__(self, settings, defer=None):
        self.settings = settings
        self._defer = defer or (lambda function: function())
        self.watcher = None              # scene.watch.SceneWatcher (読んだ skinCluster を見る)
        self.selection = VertexSelection()
        self.data = None                 # scene.skin.SkinData (無ければ None)
        self.order = []                  # 行に出すインフルエンスの番号
        self.pinned = set()              # 「＋」で足したインフルエンスのフルパス
        self.partner = None              # 移動の相手のフルパス
        self.focus = None                # マウスを乗せている行の番号
        self.drag = None
        self.limit_memory = InfluenceLimitMemory()
        self.limit_note = None
        self.generation = 0
        self._listeners = []
        self._pending = set()
        self._closed = False
        settings.addListener(self._on_setting)

    # -- 通知 ----------------------------------------------------------------

    def addListener(self, listener):
        if listener not in self._listeners:
            self._listeners.append(listener)

    def _changed(self, view_only=False):
        for listener in list(self._listeners):
            listener(view_only)

    def close(self):
        """ツールを抜けるとき。ドラッグ中なら押す前に戻し、元のウェイトの記録を捨てる。"""
        self.cancel_drag(report=False)
        self.settings.removeListener(self._on_setting)
        self.limit_memory.clear()
        self._listeners = []
        self._closed = True
        if self.watcher is not None:
            self.watcher.unwatch()

    # -- 読む ------------------------------------------------------------------

    @property
    def model(self):
        return self.data.model if self.data is not None else None

    def isDragging(self):
        return self.drag is not None

    def _read(self, selection):
        try:
            return read_skin_data(selection, self.settings.value("nameStyle"),
                                  self.settings.value("namespace"))
        except RuntimeError as error:   # 読んでいるあいだにメッシュが消えたなど
            log.warning("ウェイトを読めませんでした: {}".format(error))
            return None

    def _order_for(self, model):
        pinned = [i for i in (model.index_of(key) for key in self.pinned) if i is not None]
        return visible_order(model, self.settings.value("sort"), pinned)

    def _set_data(self, data, order):
        self.data = data
        self.order = order
        if self.watcher is not None:
            self.watcher.watch(data)

    def read_selection(self):
        """選択を読み直す (選択が変わったとき)。行は並び順の設定で並べ直す。"""
        if self.drag is not None:
            return
        self.selection = selected_vertices()
        data = self._read(self.selection)
        self.focus = None
        self.limit_note = None
        self.generation += 1
        self._set_data(data, self._order_for(data.model) if data is not None else [])
        skipped = data.skipped if data is not None else [
            mesh_label(path) for path, _v in self.selection.meshes if find_skin_cluster(path) is None]
        if skipped:
            log.info("スキンが付いていないので使いません: {}".format(", ".join(skipped)))
        if data is not None:
            for warning in normalize_warnings(data.normalize_modes):
                log.warning(warning)
        self._changed()
        if data is not None and self.settings.value("maxInfluencesEnabled"):
            self.request_limit()   # 選んだ頂点にも最大数を反映する (選択の通知を抜けてから)

    def reload(self, resort=False):
        """選択はそのままで、ウェイトを skinCluster から読み直す。

        resort が False なら今の並びを保つ (Undo / Redo・ロックの切り替えで行が入れ替わらない)。
        """
        if self.drag is not None:
            return
        data = self._read(self.selection)
        if data is None:
            self.read_selection()   # スキンが外れた・メッシュが消えたなど
            return
        order = self._order_for(data.model)
        if not resort:
            order = keep_order(self.order, order)
        self._set_data(data, order)
        self._changed()

    def _fresh(self):
        """操作を始める前に読み直した WeightModel (並びは保つ)。"""
        self.reload()
        return self.model

    def schedule_selection(self):
        self._schedule("selection", self.read_selection)

    def schedule_reload(self):
        self._schedule("reload", self.reload)

    def request_limit(self):
        self._schedule("limit", self.apply_limit)

    def _schedule(self, name, function):
        """通知の中では読み書きせず、抜けてから 1 回だけ行う (同じものは 1 回にまとめる)。"""
        if name in self._pending:
            return
        self._pending.add(name)

        def run():
            self._pending.discard(name)
            if not self._closed and self.drag is None:
                function()

        self._defer(run)

    # -- 表示 ------------------------------------------------------------------

    def _partner_index(self, model):
        return model.index_of(self.partner) if self.partner is not None and model is not None else None

    def panel_state(self):
        model = self.model
        drag = self.drag
        data = self.data
        message = ""
        if data is None:
            skipped = [mesh_label(path) for path, _v in self.selection.meshes]
            message = empty_message(not self.selection.isEmpty(), skipped)
        return build_panel_state(
            model, self.order, self.settings.values(),
            colors=data.colors if data is not None else None,
            mesh_counts=data.mesh_counts if data is not None else (),
            normalize_modes=data.normalize_modes if data is not None else None,
            pinned=self.pinned, partner=self._partner_index(model),
            drag_index=drag.index if drag is not None and not drag.pending else None,
            drag_value=drag.value if drag is not None else None,
            clipboard_count=CLIPBOARD.count(), limit_note=self.limit_note, message=message,
            generation=self.generation)

    def guide(self):
        """ジョイントへの線と名前 (Guide)。出さないなら None。"""
        data = self.data
        show_line = self.settings.value("hoverName")
        show_points = self.settings.value("weightDisplay")
        if data is None or not (show_line or show_points):
            return None
        index = self.drag.index if self.drag is not None else self.focus
        if index is None or index >= len(data.influence_dags):
            return None
        points = []
        if show_points:
            # 今のウェイト (ドラッグ中はドラッグで変えた値) をメッシュごとに
            column = data.model.column(index)
            for part in data.parts:
                points.append((part["path"], part["vertices"], column[part["start"]:part["end"]]))
        return Guide(data.center_meshes, data.center, data.influence_dags[index],
                     data.model.influences[index], show_line, points)

    def set_focus(self, index):
        """マウスを乗せた行 (無ければ None)。ジョイントへの線を描き直す。"""
        index = None if index is None or index < 0 else index
        if index != self.focus:
            self.focus = index
            self._changed(view_only=True)

    # -- ドラッグ -------------------------------------------------------------

    def press(self, index, value, ctrl=False, shift=False):
        """行のバーを押した。"""
        if self.drag is not None:
            return
        model = self._fresh()
        if model is None or index >= len(model.influences):
            return
        name = model.influences[index]
        mode = self.settings.value("mode")
        if mode == MODE_MOVE:
            # 押しただけでは決めない。動かしたらドラッグ、動かさずに離したらクリック (相手)
            self.drag = Drag(index, MODE_MOVE, model, pending=True)
            return
        if mode == MODE_SCALE and model.average(index) <= 1e-9 and not model.locks[index]:
            mode = MODE_ADD
            log.info("{} は平均が 0 なので、加算で動かします".format(name))
        reason = model.can_edit(index, mode)
        if reason is not None:
            log.warning("{} は動かせません ({})".format(name, reason))
            return
        self.drag = Drag(index, mode, model)
        self.move(value, ctrl, shift)

    def move(self, value, ctrl=False, shift=False, distance=0):
        """ドラッグ中。マウスの位置の値に向けて、押したときのウェイトから計算し直して書く。"""
        drag = self.drag
        if drag is None:
            return
        if drag.pending:
            if distance <= MOVE_CLICK_PIXELS:
                return
            partner = self._partner_index(drag.base)
            reason = drag.base.can_move(drag.index, partner)
            if reason is not None:
                log.warning("{} は移せません ({})".format(drag.base.influences[drag.index], reason))
                self.drag = None
                return
            drag.pending = False
        step = drag_step(ctrl, shift, self.settings.value("stepCtrl"), self.settings.value("stepShift"))
        drag.value = snap_value(value, step)
        if drag.mode == MODE_MOVE:
            weights, _average = drag.base.move_influence(drag.index, self._partner_index(drag.base),
                                                         drag.value)
        else:
            weights, _average = drag.base.edit_influence(drag.index, drag.value, drag.mode)
        self.data.writer().write(weights)
        self.data.model = drag.base.with_weights(weights)
        self._changed()

    def release(self):
        """ドラッグを離した。後始末をして、押す前後を 1 回の Undo にする。"""
        drag, self.drag = self.drag, None
        if drag is None:
            return
        if drag.pending:
            self.toggle_partner(drag.index)   # 移動モードのクリック
            return
        index, base = drag.index, drag.base
        edited = self.model
        name = base.influences[index]
        label = MODE_LABELS[drag.mode]
        log.info("{} ({}): 平均 {:.3f} -> {:.3f} (頂点 {} 個)".format(
            name, label, base.average(index), edited.average(index), len(edited.vertices)))
        keep = [index]
        if drag.mode == MODE_MOVE:
            keep.append(self._partner_index(base))
        weights, messages = self._cleanup(edited, edited.weights, keep)
        if messages:
            self.data.writer().write(weights)
            self.data.model = edited.with_weights(weights)
            for message in messages:
                log.info(message)
        if self.model.weights != base.weights:
            commit(WeightChange(self.data.writer(), base.weights, self.model.weights),
                   "{} {} {:.3f} -> {:.3f}".format(name, label, base.average(index),
                                                   self.model.average(index)))
        self._changed()

    def cancel_drag(self, report=True):
        """ドラッグを取り消し、押す前のウェイトに戻す (Esc・ツールを抜けたとき)。"""
        drag, self.drag = self.drag, None
        if drag is None:
            return False
        if not drag.pending:
            self.data.writer().write(drag.base.weights)
            self.data.model = drag.base
            if report:
                log.info("ドラッグを取り消しました")
        self._changed()
        return True

    # -- 後始末と元のウェイト ---------------------------------------------------

    def _limit(self):
        return self.settings.value("maxInfluences") if self.settings.value("maxInfluencesEnabled") else None

    def _cleanup(self, model, weights, keep=()):
        """最大数と刈り取りの後始末 (同じ Undo)。元のウェイト (最大数を守る前) も覚える。"""
        threshold = self.settings.value("pruneThreshold") if self.settings.value("pruneAuto") else None
        cleaned, messages = cleanup_weights(model, weights, keep, self._limit(), threshold)
        base, _ = cleanup_weights(model, weights, keep, None, threshold)
        self._record_edit(model, base, cleaned)
        return cleaned, messages

    def _limit_note_text(self):
        return "最大数 {} で減らしています (オフで元に戻る)".format(self.settings.value("maxInfluences"))

    def _record_edit(self, model, base, written):
        """編集後の値 (最大数を守る前) を元のウェイトにし、書いた値を覚える。"""
        self.limit_memory.record(model, base, written)
        self.limit_note = None
        if self.settings.value("maxInfluencesEnabled") and changed_rows(model, base, written):
            self.limit_note = self._limit_note_text()

    def apply_limit(self):
        """選んだ頂点に、元のウェイトから最大インフルエンス数を反映する (オフなら元に戻す。1 回の Undo)。"""
        model = self._fresh()
        if model is None:
            return
        enabled = self.settings.value("maxInfluencesEnabled")
        count = self.settings.value("maxInfluences")
        base = self.limit_memory.base_weights(model)
        if enabled:
            target, removed, vertices = model.with_weights(base).limit_influences(count)
        else:
            target, removed, vertices = base, 0, 0
        self.limit_memory.record(model, base, target)
        self.limit_note = self._limit_note_text() if removed else None
        if changed_rows(model, model.weights, target):
            writer = self.data.writer()
            writer.write(target)
            commit(WeightChange(writer, model.weights, target),
                   "最大インフルエンス数 {}".format(count) if enabled else "最大インフルエンス数を戻す")
            if enabled:
                log.info("最大インフルエンス数 {}: {} 頂点で {} 個のウェイトを 0 にしました".format(
                    count, vertices, removed))
            else:
                log.info("元のウェイトに戻しました")
        self.reload()

    # -- そのほかの操作 ---------------------------------------------------------

    def _write_edit(self, model, weights, label):
        """weights を書いて 1 回の Undo にする (変わっていれば True)。"""
        if weights == model.weights:
            return False
        writer = self.data.writer()
        writer.write(weights)
        commit(WeightChange(writer, model.weights, weights), label)
        return True

    def toggle_lock(self, index):
        """行のインフルエンスのロックを切り替える (1 回の Undo)。"""
        model = self._fresh()
        if model is None or index >= len(model.influences):
            return
        change = LockChange(model.keys[index], not model.locks[index])
        change.redo()
        verb = "ロック" if change.after else "ロック解除"
        commit(change, "{} を{}".format(model.influences[index], verb))
        log.info("{} を{}しました".format(model.influences[index], verb))
        self.reload()

    def enter_value(self, index, text):
        """数値の欄に打った文字を使う (1 回の Undo)。"""
        try:
            mode, value = parse_input(text, self.settings.value("mode"))
        except ValueError as error:
            log.warning("{}".format(error))
            self._changed()   # 欄を元の値に戻す
            return
        model = self._fresh()
        if model is None or index >= len(model.influences):
            return
        name = model.influences[index]
        partner = self._partner_index(model)
        reason = model.can_move(index, partner) if mode == MODE_MOVE else model.can_edit(index, mode)
        if reason is not None:
            log.warning("{} は変えられません ({})".format(name, reason))
            return
        if mode == MODE_MOVE:
            weights, _average = model.apply_move(index, partner, value)
        else:
            weights, _average = model.apply_influence(index, mode, value)
        keep = [index] + ([partner] if mode == MODE_MOVE else [])
        weights, messages = self._cleanup(model, weights, keep)
        if not self._write_edit(model, weights, "{} {}{} (入力)".format(name, INPUT_SYMBOLS[mode], value)):
            log.info("{}: 変わりませんでした".format(name))
            return
        log.info("{} {}{}: 平均 {:.3f} -> {:.3f} (頂点 {} 個)".format(
            name, INPUT_SYMBOLS[mode], value, model.average(index),
            model.with_weights(weights).average(index), len(model.vertices)))
        for message in messages:
            log.info(message)
        self.reload()

    def toggle_pin(self, key):
        """「＋」のメニュー: 0 のインフルエンスを行に出す / 外す (今の並び順の設定で並べ直す)。"""
        if key in self.pinned:
            self.pinned.discard(key)
        else:
            self.pinned.add(key)
        self.reload(resort=True)

    # -- 行の右クリックのメニュー ---------------------------------------------------

    def row_action(self, index, action):
        """行の右クリックのメニューから (ui/panel.ROW_ACTIONS の名前)。"""
        model = self._fresh()
        if model is None or index >= len(model.influences):
            return
        name = model.influences[index]
        if action == "selectJoint":
            select_names([model.keys[index]])
        elif action == "selectAffected":
            names = affected_components(self.data, index)
            if names:
                select_names(names)
                log.info("{} の影響を受ける頂点を選びました".format(name))
            else:
                log.warning("{} の影響を受ける頂点はありません".format(name))
        elif action in ("soloLock", "lockAll", "unlockAll"):
            self._set_locks(model, index, action)
        elif action in ("zero", "full", "giveToPartner"):
            self._row_value(model, index, action)
        elif action == "setPartner":
            self.toggle_partner(index)
        else:
            raise ValueError("知らない操作です: {}".format(action))

    def _set_locks(self, model, index, action):
        """これ以外をロック / すべてロック / すべてロック解除 (まとめて 1 回の Undo)。"""
        wanted = [(i != index) if action == "soloLock" else action == "lockAll"
                  for i in range(len(model.influences))]
        changes = [LockChange(key, lock) for key, lock, now in zip(model.keys, wanted, model.locks)
                   if lock != now]
        if not changes:
            return
        for change in changes:
            change.redo()
        label = {"soloLock": "{} 以外をロック".format(model.influences[index]),
                 "lockAll": "すべてロック", "unlockAll": "すべてロック解除"}[action]
        commit(changes, label)
        log.info(label)
        self.reload()

    def _row_value(self, model, index, action):
        """0 にする / 1 にする / 移動の相手へ全部移す (1 回の Undo)。"""
        name = model.influences[index]
        if action == "giveToPartner":
            partner = self._partner_index(model)
            reason = model.can_move(index, partner)
            if reason is None:
                weights, _ = model.apply_move(index, partner, -1.0)
                label = "{} を {} へ移す".format(name, model.influences[partner])
                keep = [index, partner]
        else:
            reason = model.can_edit(index, MODE_ABSOLUTE)
            if reason is None:
                value = 0.0 if action == "zero" else 1.0
                weights, _ = model.apply_influence(index, MODE_ABSOLUTE, value)
                label = "{} を {:g} に".format(name, value)
                keep = [index]
        if reason is not None:
            log.warning("{} は変えられません ({})".format(name, reason))
            return
        weights, messages = self._cleanup(model, weights, keep)
        if not self._write_edit(model, weights, label):
            log.info("{}: 変わりませんでした".format(name))
            return
        log.info(label)
        for message in messages:
            log.info(message)
        self.reload()

    def toggle_partner(self, index):
        """移動モードで行をクリックした: その行を相手にする (相手の行なら外す)。"""
        model = self.model
        if model is None or index >= len(model.keys):
            return
        key = model.keys[index]
        if self.partner == key:
            self.partner = None
            log.info("移動の相手を外しました")
        else:
            self.partner = key
            log.info("移動の相手: {}".format(model.influences[index]))
        self._changed()

    def set_mode(self, mode):
        """モードを替える (ボタン・1〜4 キー)。ドラッグ中は替えない。"""
        if mode in MODES and self.drag is None:
            self.settings.set("mode", mode)

    def prune_now(self):
        """選んだ頂点の小さいウェイトを今すぐ刈り取る (1 回の Undo)。"""
        model = self._fresh()
        if model is None:
            log.warning("頂点を選んでください")
            return
        threshold = self.settings.value("pruneThreshold")
        weights, count = model.prune(threshold)
        if not count:
            log.info("刈り取り: {} 未満のウェイトはありません".format(format_threshold(threshold)))
            return
        self._record_edit(model, weights, weights)
        self._write_edit(model, weights, "刈り取り ({} 個)".format(count))
        log.info("刈り取り: {} 個のウェイトを 0 にしました".format(count))
        self.reload()

    def run_action(self, action):
        """パネルのボタン・キー・フラグから。"copy" / "paste" / "average" / "smooth" / "prune"。"""
        {"copy": self.copy_weights, "paste": self.paste_weights, "average": self.average_weights,
         "smooth": self.smooth_now, "prune": self.prune_now}[action]()

    def smooth_now(self):
        """選んだ頂点のウェイトを、隣の頂点の平均へ寄せる (設定の強さ × 回数。1 回の Undo)。"""
        model = self._fresh()
        if model is None:
            log.warning("スムーズする頂点を選んでください")
            return
        strength = self.settings.value("smoothStrength")
        iterations = self.settings.value("smoothIterations")
        method = self.settings.value("smoothMethod")
        if method == SMOOTH_DISTANCE:
            neighbors, outside, distances = smooth_neighbors(self.data, with_distances=True)
            factors = inverse_distance_weights(distances)
        elif method == SMOOTH_COTANGENT:
            neighbors, outside, factors = smooth_neighbors(self.data, with_cotangents=True)
        else:
            neighbors, outside = smooth_neighbors(self.data)
            factors = None
        smoothed = smooth_weights(model, neighbors, outside, strength, iterations, factors)
        weights, messages = self._cleanup(model, smoothed)
        prefix = {SMOOTH_DISTANCE: "距離 ", SMOOTH_COTANGENT: "コタンジェント "}.get(method, "")
        label = "スムーズ ({}強さ {:g} × {} 回)".format(prefix, strength, iterations)
        if not self._write_edit(model, weights, label):
            log.info("スムーズ: 変わりませんでした")
            return
        log.info("{}: 頂点 {} 個".format(label, len(model.vertices)))
        for message in messages:
            log.info(message)
        self.reload()

    def copy_weights(self):
        """選んだ頂点のウェイト (複数なら平均。ソフト選択なら重み付き) をコピーする。"""
        model = self._fresh()
        if model is None:
            log.warning("コピーする頂点を選んでください")
            return
        names = dict(zip(model.keys, model.influences))
        count = len(model.vertices)
        CLIPBOARD.store(model.copy_values(), names,
                        "頂点 {} 個{}".format(count, "の平均" if count > 1 else ""))
        log.info("コピー ({}): {}".format(CLIPBOARD.source, CLIPBOARD.describe()))
        self._changed()   # ペーストのボタンを押せるようにする

    def paste_weights(self):
        if CLIPBOARD.isEmpty():
            log.warning("先にウェイトをコピーしてください")
            return
        self._set_weights_to(dict(CLIPBOARD.values), "ペースト ({})".format(CLIPBOARD.source),
                             CLIPBOARD.names)

    def average_weights(self):
        """選んだ頂点を、選んだ頂点の平均のウェイトにそろえる。"""
        model = self._fresh()
        if model is None or len(model.vertices) < 2:
            log.warning("平均化は頂点を 2 つ以上選んでください")
            return
        self._set_weights_to(model.copy_values(), "平均化", dict(zip(model.keys, model.influences)))

    def _set_weights_to(self, values, label, names):
        model = self._fresh()
        if model is None:
            log.warning("頂点を選んでください")
            return
        pasted, changed, missing = model.paste_values(values)
        if missing:
            log.warning("{}: 貼れないインフルエンスがありました (skinCluster に無い・ロック): {}".format(
                label, ", ".join(sorted(names.get(key, key) for key in missing))))
        weights, messages = self._cleanup(model, pasted)
        if not self._write_edit(model, weights, label):
            log.info("{}: 変わりませんでした".format(label))
            return
        log.info("{}: 頂点 {} 個".format(label, changed))
        for message in messages:
            log.info(message)
        self.reload()

    # -- 設定 -----------------------------------------------------------------

    def _on_setting(self, key, value):
        if key in _RELOAD_KEYS:
            self.reload(resort=True)
        elif key in _LIMIT_KEYS:
            self.request_limit()
            self._changed()
        else:
            self._changed(view_only=key in _VIEW_KEYS)
