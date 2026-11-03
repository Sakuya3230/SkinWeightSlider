# -*- coding: utf-8 -*-
"""
選んだ頂点のウェイト (WeightModel) と、パネルに出す行の並び (Maya に依存しない)。

WeightModel は計算だけのクラス。Maya から読む (scene/skin.py) と、書く (scene/writer.py) は別。
どの計算も self を変えず、新しいウェイト (頂点ごとのリスト) を返す。

変え方の共通の考え方 (_limits / _column / _redistribute):
- 頂点ごとの上限は「今の値 + ほかのロックされていないインフルエンスの合計」、下限は 0 (ほかに
  動かせるものが無い頂点は減らせないので今の値)。どのモードも頂点ごとにこの範囲で頭打ちにする
- 増えた・減った分は、ほかのロックされていないインフルエンスへ今の比率で引く・足す。
  頂点ごとの合計は変わらない (正規化が「なし」の skinCluster でも今の合計を保つ)
- ソフト選択の重み (strengths) が s の頂点は 今の値 + s × (変えた値 - 今の値)。平均もこの重み付き
- 頭打ちがあっても平均が目標になるよう、倍率・量を二分探索で決める (_solve)
- 複数のメッシュでは、そのメッシュの skinCluster に無いインフルエンスの列は 0 のまま変えない
  (available)
"""

__all__ = ["WeightModel", "SORT_INDEX", "SORT_AVERAGE", "SORT_NAME", "SORTS", "visible_order",
           "zero_influences", "keep_order"]

from .modes import MODE_ABSOLUTE, MODE_ADD, MODE_SCALE

# 行の並び順 (設定 sort)。既定はインフルエンスの番号順 (平均の大きい順だと Undo で行が入れ替わる)
SORT_INDEX = "index"
SORT_AVERAGE = "average"
SORT_NAME = "name"
SORTS = (SORT_INDEX, SORT_AVERAGE, SORT_NAME)

EPSILON = 1e-9


class WeightModel(object):
    """選んだ頂点のウェイト。

    influences  インフルエンスの表示名のリスト (列の順)
    locks       インフルエンスごとのロック (bool のリスト)
    vertices    頂点の番号のリスト (行の順)
    weights     頂点ごとのウェイト [[インフルエンス0, インフルエンス1, ...], ...]
    available   行ごとの、使えるインフルエンスの番号の集合のリスト。None ならすべて使える
                (複数のメッシュで、そのメッシュの skinCluster に無い列は変えない)
    strengths   行ごとの、変化を効かせる割合 (ソフト選択の重み。選んだ頂点は 1)。None ならすべて 1
    keys        列のキー (インフルエンスのフルパス)。コピー・ペースト・元のウェイトの記録に使う。
                None なら influences
    row_keys    行のキー ((メッシュのフルパス, 頂点の番号))。元のウェイトの記録に使う
    """

    def __init__(self, influences, locks, vertices, weights, available=None, strengths=None,
                 keys=None, row_keys=None):
        self.influences = list(influences)
        self.locks = list(locks)
        self.vertices = list(vertices)
        self.weights = [list(row) for row in weights]
        self.available = None if available is None else [frozenset(a) for a in available]
        self.strengths = None if strengths is None else [float(v) for v in strengths]
        self.keys = list(keys) if keys is not None else list(self.influences)
        self.row_keys = list(row_keys) if row_keys is not None else [(None, v) for v in self.vertices]

    def with_weights(self, weights):
        """ウェイトだけを替えた写し。"""
        return WeightModel(self.influences, self.locks, self.vertices, weights, self.available,
                           self.strengths, self.keys, self.row_keys)

    # -- 値を読む -----------------------------------------------------------------

    def strength(self, row):
        return 1.0 if self.strengths is None else self.strengths[row]

    def is_available(self, row, index):
        """行 row (頂点) で、インフルエンス index を変えられるか。"""
        return self.available is None or index in self.available[row]

    def column(self, index):
        return [row[index] for row in self.weights]

    def average(self, index):
        """インフルエンス index の平均。ソフト選択なら、その重み付きの平均。"""
        return self._weighted_average(self.column(index))

    def _weighted_average(self, values):
        if not values:
            return 0.0
        if self.strengths is None:
            return sum(values) / len(values)
        total = sum(self.strengths)
        if total <= 1e-12:
            return 0.0
        return sum(v * w for v, w in zip(values, self.strengths)) / total

    def minimum(self, index):
        return min(self.column(index)) if self.weights else 0.0

    def maximum(self, index):
        return max(self.column(index)) if self.weights else 0.0

    def rows(self, include_zero=False, sort=None):
        """出す行 (インフルエンスの番号) を、並び順 sort で返す。

        include_zero が False なら、どの頂点でも 0 のインフルエンスは除く。
        平均の大きい順・名前順で同じなら番号順。
        """
        indices = list(range(len(self.influences)))
        if not include_zero:
            indices = [i for i in indices if self.maximum(i) > EPSILON]
        sort = sort or SORT_INDEX
        if sort == SORT_AVERAGE:
            return sorted(indices, key=lambda i: (-self.average(i), i))
        if sort == SORT_NAME:
            return sorted(indices, key=lambda i: (self.influences[i].lower(), i))
        if sort == SORT_INDEX:
            return indices
        raise ValueError("知らない並び順: {}".format(sort))

    def index_of(self, key):
        """列のキー (フルパス) の番号。無ければ None。"""
        try:
            return self.keys.index(key)
        except ValueError:
            return None

    # -- 割合・加算・絶対 -------------------------------------------------------------

    def can_edit(self, index, mode=MODE_SCALE):
        """モード mode で index を動かせるか。動かせなければ理由の文字列、動かせれば None。"""
        if self.locks[index]:
            return "ロックされています"
        if mode == MODE_SCALE and self.average(index) <= EPSILON:
            return "平均が 0 です。割合モードでは 0 から増やせません (加算・絶対モードを使う)"
        if all(high - low <= EPSILON for _w, low, high, _free in self._limits(index)):
            return "ほかに動かせるインフルエンスがありません"
        return None

    def _limits(self, index):
        """頂点ごとの (今の値, 下限, 上限, ほかの動かせるインフルエンスの合計)。"""
        limits = []
        for r, row in enumerate(self.weights):
            if not self.is_available(r, index):
                limits.append((0.0, 0.0, 0.0, 0.0))   # その skinCluster に無い列。0 のまま
                continue
            w = row[index]
            free = sum(v for i, v in enumerate(row) if i != index and not self.locks[i])
            low = w if free <= 1e-12 else 0.0
            limits.append((w, low, w + free, free))
        return limits

    def _column(self, limits, value_of):
        """頂点ごとに value_of(今の値) を上限・下限で頭打ちにし、ソフト選択の重みの分だけ効かせた列。"""
        column = []
        for row, (w, low, high, _free) in enumerate(limits):
            changed = min(max(value_of(w), low), high)
            column.append(w + self.strength(row) * (changed - w))
        return column

    def _solve(self, limits, value_of, low_param, high_param, target, iterations=60):
        """value_of(w, param) の列の平均が target になる param を二分探索で求め、列を返す。

        param が大きいほど平均が大きくなる (単調) ことが前提。届かない target は届く端。
        """
        def column(param):
            return self._column(limits, lambda w: value_of(w, param))

        def average(param):
            return self._weighted_average(column(param))

        target = min(max(target, average(low_param)), average(high_param))
        for _ in range(iterations):
            middle = (low_param + high_param) / 2.0
            if average(middle) < target:
                low_param = middle
            else:
                high_param = middle
        return column((low_param + high_param) / 2.0)

    def _redistribute(self, index, limits, column):
        """index の列を column にし、増減分をほかのロックされていないインフルエンスへ比率で配る。"""
        weights = []
        for row, (w, _low, _high, free), new in zip(self.weights, limits, column):
            new_row = list(row)
            new_row[index] = new
            if free > 1e-12:
                factor = (free - (new - w)) / free
                for i in range(len(row)):
                    if i != index and not self.locks[i]:
                        new_row[i] = row[i] * factor
            weights.append(new_row)
        return weights

    def edit_influence(self, index, target, mode=MODE_SCALE):
        """ドラッグ: index の平均を target に向けて変える。(新しいウェイト, 実際の平均)。

        割合は平均が target になる倍率、加算は量を探す。絶対は全頂点を target にする
        (頭打ちの頂点があると、平均は target と少しずれる)。
        """
        limits = self._limits(index)
        if mode == MODE_SCALE:
            ratios = [high / w for w, _low, high, _free in limits if w > 1e-12]
            column = self._solve(limits, lambda w, k: k * w, 0.0, max(ratios) if ratios else 1.0, target)
        elif mode == MODE_ADD:
            column = self._solve(limits, lambda w, d: w + d, -1.0, 1.0, target)
        elif mode == MODE_ABSOLUTE:
            column = self._column(limits, lambda w: target)
        else:
            raise ValueError("知らないモード: {}".format(mode))
        return self._redistribute(index, limits, column), self._weighted_average(column)

    def apply_influence(self, index, mode, value):
        """数値の入力: 倍率 (割合)・量 (加算)・値 (絶対) をそのまま全頂点に使う。(新しいウェイト, 平均)。"""
        limits = self._limits(index)
        if mode == MODE_SCALE:
            column = self._column(limits, lambda w: w * value)
        elif mode == MODE_ADD:
            column = self._column(limits, lambda w: w + value)
        elif mode == MODE_ABSOLUTE:
            column = self._column(limits, lambda w: value)
        else:
            raise ValueError("知らないモード: {}".format(mode))
        return self._redistribute(index, limits, column), self._weighted_average(column)

    # -- 移動 (相手のインフルエンスとのあいだだけ) ---------------------------------

    def can_move(self, index, partner):
        """index と相手 partner のあいだで移せるか。移せなければ理由の文字列。"""
        if partner is None:
            return "移動の相手を選んでください (移動モードで行をクリック)"
        if partner == index:
            return "相手と同じインフルエンスです"
        if self.locks[index] or self.locks[partner]:
            return "ロックされています"
        if all(high - low <= EPSILON for _w, low, high, _p in self._move_limits(index, partner)):
            return "移せるウェイトがありません"
        return None

    def _move_limits(self, index, partner):
        """頂点ごとの (今の値, 下限 0, 上限 今の値 + 相手, 相手)。どちらかが無い頂点は変えない。"""
        limits = []
        for r, row in enumerate(self.weights):
            w = row[index]
            if not (self.is_available(r, index) and self.is_available(r, partner)):
                limits.append((w, w, w, 0.0))
                continue
            limits.append((w, 0.0, w + row[partner], row[partner]))
        return limits

    def _move_redistribute(self, index, partner, column):
        weights = []
        for row, new in zip(self.weights, column):
            new_row = list(row)
            new_row[partner] = row[partner] - (new - row[index])
            new_row[index] = new
            weights.append(new_row)
        return weights

    def move_influence(self, index, partner, target):
        """ドラッグ (移動): 相手とのあいだだけで、index の平均が target になる量を全頂点に移す。"""
        limits = self._move_limits(index, partner)
        column = self._solve(limits, lambda w, d: w + d, -1.0, 1.0, target)
        return self._move_redistribute(index, partner, column), self._weighted_average(column)

    def apply_move(self, index, partner, amount):
        """数値の入力 (移動): 相手から amount を全頂点に移す (負なら相手へ戻す)。"""
        limits = self._move_limits(index, partner)
        column = self._column(limits, lambda w: w + amount)
        return self._move_redistribute(index, partner, column), self._weighted_average(column)

    # -- 刈り取り・最大インフルエンス数 ---------------------------------------------

    def prune(self, threshold):
        """しきい値より小さいウェイトを 0 にし、その分を残りへ比率で配る。(新しいウェイト, 0 にした数)。

        0 にするのは 0 < w < threshold のロックされていないもの。配る先 (0 でなくロックされて
        いないもの) が無い頂点は刈り取らない。ソフト選択の重みは使わない (掃除なので範囲も同じ)。
        """
        weights = []
        count = 0
        for r, row in enumerate(self.weights):
            small = [i for i, w in enumerate(row)
                     if 0.0 < w < threshold and not self.locks[i] and self.is_available(r, i)]
            receivers = [i for i, w in enumerate(row) if i not in small and w > 0.0 and not self.locks[i]]
            total = sum(row[i] for i in receivers)
            if not small or total <= 1e-12:
                weights.append(list(row))
                continue
            factor = (total + sum(row[i] for i in small)) / total
            new_row = list(row)
            for i in small:
                new_row[i] = 0.0
            for i in receivers:
                new_row[i] = row[i] * factor
            weights.append(new_row)
            count += len(small)
        return weights, count

    def limit_influences(self, limit, keep=()):
        """頂点ごとに、0 でないインフルエンスを limit 個までにする。(新しいウェイト, 0 にした数, 変えた頂点の数)。

        ロックされたもの・keep (今いじったもの) は必ず残し、残りの枠を大きい順に埋める。外したものの分は
        残したもの (keep以外を優先) へ比率で配る。配る先が無い頂点はそのまま。
        """
        keep = set(keep)
        weights = []
        removed_total = 0
        vertices = 0
        for r, row in enumerate(self.weights):
            nonzero = [i for i, w in enumerate(row) if w > 0.0 and self.is_available(r, i)]
            if len(nonzero) <= limit:
                weights.append(list(row))
                continue
            must = [i for i in nonzero if self.locks[i] or i in keep]
            others = sorted((i for i in nonzero if i not in must), key=lambda i: (-row[i], i))
            slots = max(limit - len(must), 0)
            kept = must + others[:slots]
            removed = others[slots:]
            receivers = [i for i in kept if not self.locks[i] and i not in keep and row[i] > 0.0]
            if not receivers:
                receivers = [i for i in kept if not self.locks[i] and row[i] > 0.0]
            total = sum(row[i] for i in receivers)
            if not removed or total <= 1e-12:
                weights.append(list(row))
                continue
            factor = (total + sum(row[i] for i in removed)) / total
            new_row = list(row)
            for i in removed:
                new_row[i] = 0.0
            for i in receivers:
                new_row[i] = row[i] * factor
            weights.append(new_row)
            removed_total += len(removed)
            vertices += 1
        return weights, removed_total, vertices

    # -- コピー・ペースト ---------------------------------------------------------

    def copy_values(self):
        """{列のキー: 平均} (0 のものは入れない)。頂点が 1 つならその値。"""
        values = {}
        for i, key in enumerate(self.keys):
            value = self.average(i)
            if value > EPSILON:
                values[key] = value
        return values

    def paste_values(self, values, epsilon=1e-12):
        """全頂点を values ({列のキー: 値}) にする。(新しいウェイト, 変えた頂点の数, 貼れなかったキーの集合)。

        ロックは今の値のまま、残り (頂点の合計 - ロックの合計) を values の比率で配る。その頂点で
        使えない・ロックのキーは貼れないので、残りで比率を保つ。ソフト選択なら重みの分だけ効かせる。
        """
        index_of = dict((key, i) for i, key in enumerate(self.keys))
        missing = set(key for key in values if key not in index_of)
        weights = []
        changed = 0
        for r, row in enumerate(self.weights):
            targets = {}
            for key, value in values.items():
                i = index_of.get(key)
                if i is None:
                    continue
                if self.locks[i] or not self.is_available(r, i):
                    if value > epsilon:
                        missing.add(key)
                    continue
                targets[i] = value
            share = sum(targets.values())
            room = sum(row) - sum(w for i, w in enumerate(row) if self.locks[i])
            if share <= epsilon or room <= epsilon:
                weights.append(list(row))
                continue
            pasted = [w if self.locks[i] else targets.get(i, 0.0) * room / share
                      for i, w in enumerate(row)]
            s = self.strength(r)
            new_row = [w + s * (p - w) for w, p in zip(row, pasted)]
            if any(abs(a - b) > epsilon for a, b in zip(new_row, row)):
                changed += 1
            weights.append(new_row)
        return weights, changed, missing


def visible_order(model, sort, pinned=()):
    """パネルに出す行 (インフルエンスの番号) の並び。0 でないものと、ピン留め (pinned) したもの。"""
    shown = set(model.rows()) | set(pinned)
    return [i for i in model.rows(include_zero=True, sort=sort) if i in shown]


def zero_influences(model):
    """選んだ頂点のどれでも 0 のインフルエンスの番号 (「＋」のメニューに出す)。番号順。"""
    nonzero = set(model.rows())
    return [i for i in range(len(model.influences)) if i not in nonzero]


def keep_order(old_order, new_order):
    """読み直したときの行の並び。前の並びにある行は前の順のまま、増えた行は new_order の順で後ろに。

    Undo / Redo・ロックの切り替えで読み直すたびに並びが変わると、どの行を見ていたか分からなくなるため。
    """
    new_set = set(new_order)
    kept = [i for i in old_order if i in new_set]
    kept_set = set(kept)
    return kept + [i for i in new_order if i not in kept_set]
