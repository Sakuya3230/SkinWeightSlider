# -*- coding: utf-8 -*-
"""
インフルエンスの表示名 (Maya に依存しない)。

    influence_labels(["|root|L_arm|joint1", "|root|R_arm|joint1"], NAME_UNIQUE)
        -> ["L_arm|joint1", "R_arm|joint1"]

名前の出し方 (設定 nameStyle):
    short    ノードの名前だけ (重複していても)。既定
    unique   インフルエンスの中で区別できる最短の名前 (同じ名前があるものだけ親の名前を足す)。
             partialPathName (シーン全体で一意) だと、シーンに同じ名前のノードがあるだけでパス付きに
             なって読みにくかった
名前空間 (設定 namespace) を出さないときも、省くと区別できないものは名前空間を残す。
"""

__all__ = ["NAME_SHORT", "NAME_UNIQUE", "NAME_STYLES", "strip_namespace", "influence_labels"]

NAME_SHORT = "short"
NAME_UNIQUE = "unique"
NAME_STYLES = (NAME_SHORT, NAME_UNIQUE)


def strip_namespace(name):
    """名前空間を省いた名前 (chr:arm:joint1 -> joint1)。"""
    return name.rsplit(":", 1)[-1]


def influence_labels(full_paths, style=NAME_SHORT, namespace=True):
    """インフルエンスのフルパスから表示名のリストを作る。"""
    full = [[name for name in path.split("|") if name] for path in full_paths]
    parts = full if namespace else [[strip_namespace(name) for name in names] for names in full]
    if style == NAME_SHORT:
        return [names[-1] if names else "" for names in parts]
    if style != NAME_UNIQUE:
        raise ValueError("知らない名前の出し方: {}".format(style))
    depth = [1] * len(parts)   # 後ろから何個の名前を使うか

    def label(i):
        return "|".join(parts[i][-depth[i]:])

    changed = True
    while changed:
        groups = {}
        for i in range(len(parts)):
            groups.setdefault(label(i), []).append(i)
        changed = False
        for members in groups.values():
            if len(members) < 2:
                continue
            for i in members:
                if depth[i] < len(parts[i]):
                    depth[i] += 1
                    changed = True
    labels = [label(i) for i in range(len(parts))]
    if not namespace:
        # 名前空間を省いたせいで区別できないものは、名前空間付きで作り直す
        counts = {}
        for text in labels:
            counts[text] = counts.get(text, 0) + 1
        clash = [i for i, text in enumerate(labels) if counts[text] > 1]
        if clash:
            fixed = influence_labels([full_paths[i] for i in clash], NAME_UNIQUE, True)
            for i, text in zip(clash, fixed):
                labels[i] = text
    return labels
