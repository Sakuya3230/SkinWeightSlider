# -*- coding: utf-8 -*-
"""
コピーしたウェイト (Maya に依存しない)。Maya を閉じるまで (このモジュールをリロードするまで) 残る。

    CLIPBOARD.store(values, names, source)   # {インフルエンスのフルパス: 値}
    CLIPBOARD.values                          # ペーストで使う
"""

__all__ = ["Clipboard", "CLIPBOARD"]


class Clipboard(object):
    def __init__(self):
        self.values = {}    # {インフルエンスのフルパス: 値}
        self.names = {}     # {フルパス: 表示名} (ログ用)
        self.source = ""    # 何をコピーしたか (「頂点 3 個の平均」など)

    def store(self, values, names, source):
        self.values = dict(values)
        self.names = dict((key, names.get(key, key)) for key in values)
        self.source = source

    def isEmpty(self):
        return not self.values

    def count(self):
        return len(self.values)

    def describe(self):
        """「joint1 0.600, joint2 0.400」(値の大きい順)。"""
        return ", ".join("{} {:.3f}".format(self.names.get(key, key), value)
                         for key, value in sorted(self.values.items(), key=lambda item: -item[1]))


CLIPBOARD = Clipboard()
