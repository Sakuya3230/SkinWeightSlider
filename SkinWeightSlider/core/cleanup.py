# -*- coding: utf-8 -*-
"""
編集のあとの後始末と、最大インフルエンス数を守る前の「元のウェイト」の記録 (Maya に依存しない)。

    weights, messages = cleanup_weights(model, weights, keep, limit, threshold)
    memory = InfluenceLimitMemory()
    base = memory.base_weights(model)      # 頂点ごとの元のウェイト
    memory.record(model, base, written)    # 元のウェイトと、書いた値を覚える

後始末 (ドラッグを離したとき・数値の入力・ペーストのあと。その編集と同じ 1 回の Undo):
    1. 最大インフルエンス数を守る (設定 maxInfluencesEnabled / maxInfluences。skinCluster の
       maintainMaxInfluences ではなく、このツールの設定)
    2. 小さいウェイトを刈り取る (設定 pruneAuto / pruneThreshold)

元のウェイト: 最大数を守ると、外したインフルエンスの値が消える。数を 4 -> 3 -> 5 と変えても削れた分が
戻るよう、守る前の値を頂点ごとに覚える (ツールを使っている間だけ)。頂点を読んだとき、今の値が
「最後に書いた値」と違えば (Undo・外での変更・初めての頂点)、今の値を新しい元のウェイトにする。
"""

__all__ = ["cleanup_weights", "InfluenceLimitMemory", "row_to_dict", "dict_to_row", "same_values",
           "changed_rows"]


def cleanup_weights(model, weights, keep=(), limit=None, threshold=None):
    """最大数を守り (limit)、刈り取る (threshold)。どちらも None なら何もしない。

    戻り値は (新しいウェイト, ログに出す文のリスト)。keep は今いじったインフルエンス (必ず残す)。
    """
    current = model.with_weights(weights)
    messages = []
    if limit is not None:
        limited, removed, vertices = current.limit_influences(limit, keep)
        if removed:
            current = current.with_weights(limited)
            messages.append("最大インフルエンス数 {}: {} 頂点で {} 個のウェイトを 0 にしました".format(
                limit, vertices, removed))
    if threshold is not None:
        pruned, count = current.prune(threshold)
        if count:
            current = current.with_weights(pruned)
            messages.append("刈り取り: {} 個のウェイトを 0 にしました".format(count))
    return current.weights, messages


def row_to_dict(model, weights, row):
    """行 row のウェイトを {列のキー: 値} にする (その頂点で使えない列は入れない)。"""
    return dict((key, weights[row][i]) for i, key in enumerate(model.keys)
                if model.is_available(row, i))


def dict_to_row(model, row, values):
    """{列のキー: 値} を、model の列の並びの行にする (無い列は 0)。"""
    return [values.get(key, 0.0) if model.is_available(row, i) else 0.0
            for i, key in enumerate(model.keys)]


def same_values(a, b, tolerance=1e-6):
    """2 つの {キー: 値} がほぼ同じか。"""
    return all(abs(a.get(k, 0.0) - b.get(k, 0.0)) <= tolerance for k in set(a) | set(b))


def changed_rows(model, before, after):
    """2 つのウェイト (model の並び) で値が変わった行があるか。"""
    return any(not same_values(row_to_dict(model, before, r), row_to_dict(model, after, r))
               for r in range(len(model.row_keys)))


class InfluenceLimitMemory(object):
    """最大インフルエンス数を守る前の「元のウェイト」を頂点ごとに覚える。

    キーは model.row_keys の (メッシュのフルパス, 頂点)。値は {列のキー: ウェイト}。
      baseline  元のウェイト (最大数を守る前)
      applied   このツールが最後に書いた値
    """

    def __init__(self):
        self.baseline = {}
        self.applied = {}

    def clear(self):
        self.baseline.clear()
        self.applied.clear()

    def base_weights(self, model):
        """model の行ごとの元のウェイト (model の列の並び)。今の値が最後に書いた値と違えば今の値。"""
        rows = []
        for r, key in enumerate(model.row_keys):
            current = row_to_dict(model, model.weights, r)
            if key in self.baseline and same_values(self.applied.get(key, {}), current):
                base = self.baseline[key]
            else:
                base = current
                self.baseline[key] = current
            rows.append(dict_to_row(model, r, base))
        return rows

    def record(self, model, base, written):
        """元のウェイト base と、書いた値 written を覚える (どちらも model の列の並び)。"""
        for r, key in enumerate(model.row_keys):
            self.baseline[key] = row_to_dict(model, base, r)
            self.applied[key] = row_to_dict(model, written, r)
