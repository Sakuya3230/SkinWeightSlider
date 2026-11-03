# -*- coding: utf-8 -*-
"""
スムーズ: 選んだ頂点のウェイトを、隣の頂点 (辺でつながった頂点) の平均へ寄せる (Maya に依存しない)。

    weights = smooth_weights(model, neighbors, outside, strength=0.5, iterations=3)

- 1 回のスムーズで、各頂点の全インフルエンスを「隣の平均」へ strength の割合だけ寄せる。全頂点を同時に
  更新し (順番で結果が偏らないように)、それを iterations 回くり返す。1 回だと隣とだけ混ざるので、
  回数を増やすほど遠くの頂点の値まで伝わり、広い範囲がなだらかになる
- 隣には選んでいない頂点も入る (outside)。値の元として使い、自分は変えない (選んだ範囲の端が周りと
  つながる)
- ロックされたインフルエンスは変えない。残り (頂点の合計 - ロック) を、寄せた値の比率で配り直すので、
  頂点ごとの合計は変わらない。その頂点で使えない列 (複数のメッシュで skinCluster に無い列) は 0 のまま
- ソフト選択の重み s の頂点は、1 回ごとに strength × s だけ寄せる
- 平均の取り方 (方式。設定 smoothMethod):
    均等 (uniform)       どの隣も同じ重み。メッシュの割り方が不均一だと、細かく割れている側へ偏る
    距離 (distance)      隣ごとに 1 / 距離 の重み (近い頂点の値を強く受け継ぐ)。形に沿ってなだらかになる。
                         距離はスキンで変形する前の形で測る (scene/skin.input_points。変形後だとウェイトで
                         伸び縮みした形になり、元の形に沿わない)
    コタンジェント (cotangent)  辺の向かいの角から決める重み (cot α + cot β) / 2。メッシュ処理で「形を保つ」
                         重みとしてよく使われ、割り方の偏り (細長い面・密度の差) に最も強い。多角形は三角形に
                         分けて扱う。鈍角で負になる重みは 0、全部 0 の頂点は均等 (cotangent_weights)
  重みは neighbor_weights (隣と同じ並び) で渡す。inverse_distance_weights が距離から作る
"""

__all__ = ["smooth_weights", "inverse_distance_weights", "cotangent_weights", "cotangent_edge_weights",
           "SMOOTH_UNIFORM", "SMOOTH_DISTANCE", "SMOOTH_COTANGENT", "SMOOTH_METHODS"]

SMOOTH_UNIFORM = "uniform"
SMOOTH_DISTANCE = "distance"
SMOOTH_COTANGENT = "cotangent"
SMOOTH_METHODS = (SMOOTH_UNIFORM, SMOOTH_DISTANCE, SMOOTH_COTANGENT)


def cotangent_edge_weights(triangles, points):
    """辺ごとのコタンジェントの重み {(小さい頂点, 大きい頂点): (cot α + cot β) / 2}。

    triangles は頂点の番号の 3 つ組のリスト、points は {頂点: (x, y, z)}。辺 (i, j) の重みは、その辺を
    はさむ三角形ごとに、辺の向かいの頂点の角のコタンジェントを足して 2 で割る (境界の辺は 1 つだけ)。
    鈍角では負になる (そのまま返す。使う側で 0 にする)。
    """
    weights = {}
    for triangle in triangles:
        for k in range(3):
            a, b, o = triangle[k], triangle[(k + 1) % 3], triangle[(k + 2) % 3]   # o は辺 ab の向かい
            u = [p - q for p, q in zip(points[a], points[o])]
            v = [p - q for p, q in zip(points[b], points[o])]
            cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            area = sum(c * c for c in cross) ** 0.5
            cot = sum(p * q for p, q in zip(u, v)) / area if area > 1e-12 else 0.0
            edge = (a, b) if a < b else (b, a)
            weights[edge] = weights.get(edge, 0.0) + cot / 2.0
    return weights


def cotangent_weights(rows, triangles, points, epsilon=1e-9):
    """行ごとの、隣ごとのコタンジェントの重み。rows は [(頂点, [隣の頂点, ...])] (隣の並びはスムーズと同じ)。

    負の重み (鈍角の三角形) は 0 にする (負のまま平均すると、値が 0〜1 の外へ出て振動するため)。
    全部 0 になった頂点 (とがった形など) は均等にする。
    """
    edges = cotangent_edge_weights(triangles, points)
    result = []
    for vertex, near in rows:
        row = [max(edges.get((vertex, n) if vertex < n else (n, vertex), 0.0), 0.0) for n in near]
        if sum(row) <= epsilon:
            row = [1.0] * len(near)
        result.append(row)
    return result


def inverse_distance_weights(distances, epsilon=1e-9):
    """行ごとの隣の距離のリストから、隣ごとの重み (1 / 距離) のリスト。重なった頂点は最も近い扱い。"""
    result = []
    for row in distances:
        nearest = min([d for d in row if d > epsilon] or [1.0])
        result.append([1.0 / max(d, nearest * 1e-3, epsilon) for d in row])
    return result


def smooth_weights(model, neighbors, outside, strength, iterations, neighbor_weights=None):
    """スムーズしたウェイト (model の行・列の並び)。model は変えない。

    neighbors         行ごとの隣のリスト。隣は番号: 0〜(行の数 - 1) は model の行 (選んだ頂点)、
                      それ以上は outside[番号 - 行の数] (選んでいない隣の頂点)
    outside           選んでいない隣の頂点のウェイト (model の列の並び。使えない列は 0)
    neighbor_weights  行ごとの、隣ごとの重み (neighbors と同じ並び)。None なら均等
    """
    count = len(model.weights)
    current = [list(row) for row in model.weights]
    columns = len(model.influences)
    locked = [i for i in range(columns) if model.locks[i]]
    for _ in range(max(int(iterations), 0)):
        source = current + list(outside)
        updated = []
        for r, row in enumerate(current):
            near = neighbors[r]
            amount = strength * model.strength(r)
            if not near or amount <= 0.0:
                updated.append(row)
                continue
            factors = neighbor_weights[r] if neighbor_weights is not None else [1.0] * len(near)
            total = float(sum(factors))
            average = [sum(f * source[n][c] for n, f in zip(near, factors)) / total
                       for c in range(columns)]
            target = [w + amount * (a - w) if model.is_available(r, c) else 0.0
                      for c, (w, a) in enumerate(zip(row, average))]
            updated.append(_keep_locks_and_total(model, r, row, target, locked))
        current = updated
    return current if count else []


def _keep_locks_and_total(model, r, row, target, locked):
    """ロックの値を戻し、ロックされていない列を、頂点の今の合計に合うよう比率で配り直す。"""
    room = sum(row) - sum(row[i] for i in locked)
    free = [i for i in range(len(row)) if not model.locks[i] and model.is_available(r, i)]
    total = sum(max(target[i], 0.0) for i in free)
    if total <= 1e-12 or room <= 1e-12:
        return list(row)
    result = list(row)
    for i in free:
        result[i] = max(target[i], 0.0) * room / total
    return result
