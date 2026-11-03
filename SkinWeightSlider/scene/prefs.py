# -*- coding: utf-8 -*-
"""
設定を Maya の設定 (optionVar) に保存する (UVPathCut と同じ形)。

    settings = Settings(OptionVarStorage())   # 作ったときに読み、変えるたびに保存する

値は JSON の文字列 1 つにまとめ、既定値と同じ項目は書かない (既定値を変えたら、保存していない項目は
新しい既定値になる。旧版は全部を保存していたので、既定を変えても前の値が使われ続けた)。
"""
import json

import maya.cmds as cmds

from ..constants import OPTION_VAR
from ..core import settings as settings_module

__all__ = ["OptionVarStorage"]


class OptionVarStorage(object):
    def __init__(self, name=OPTION_VAR):
        self.name = name

    def load(self):
        """保存した dict。無い・読めなければ None。"""
        try:
            if not cmds.optionVar(exists=self.name):
                return None
            data = json.loads(cmds.optionVar(query=self.name))
        except (RuntimeError, ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    def save(self, values):
        defaults = settings_module.defaults()
        changed = dict((key, value) for key, value in values.items() if defaults.get(key) != value)
        if changed:
            cmds.optionVar(stringValue=(self.name, json.dumps(changed, sort_keys=True)))
        else:
            self.remove()

    def remove(self):
        if cmds.optionVar(exists=self.name):
            cmds.optionVar(remove=self.name)
