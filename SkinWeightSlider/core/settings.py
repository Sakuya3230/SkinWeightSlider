# -*- coding: utf-8 -*-
"""
設定の定義表と、設定の値を持つ Settings (Maya に依存しない。UVPathCut と同じ形)。

    settings = Settings(storage)          # storage は load() / save(dict) を持つもの (無ければ保存しない)
    settings.value("mode")                # "scale"
    settings.set("mode", "add")           # 正規化して変え、保存して、リスナーに知らせる
    settings.set("mode", "1")             # 選択肢は番号 (文字列でも) でもよい -> "add"

設定を足すときは DEFINITIONS に 1 行足す。正規化・保存・コンテキストのコマンドのフラグ
(tool/command.py)・ツール設定のウィンドウ (core/tool_ui_text.py) は、この表から作る。

種類 (Setting.kind):
    BOOL    真偽値 (True / False、1 / 0、"true" / "false" などの文字列)
    CHOICE  選択肢の名前のどれか。番号 (0, 1, ...) や数字の文字列も受け付ける
    INT     整数。範囲の外は端に寄せる
    FLOAT   小数。範囲の外は端に寄せる
    COLOR   色 (r, g, b)。0〜1 の 3 つの数 (リスト・"r g b" の文字列)。フラグは -setColor "キー r g b"
            (コンテキストのコマンドの問い合わせは数を 1 つしか返せないため)
    OFFSET  画面のずれ (x, y) の整数 2 つ。パネルをつまみで動かした量。フラグもウィンドウの欄も作らない
"""

__all__ = ["BOOL", "CHOICE", "INT", "FLOAT", "COLOR", "OFFSET", "Setting", "SettingsError",
           "DEFINITIONS", "definition", "normalize", "normalize_all", "defaults", "Settings",
           "HOST_WINDOW", "HOST_VIEW"]

from .modes import MODE_LABELS, MODES
from .model import SORTS
from .names import NAME_STYLES
from .placement import PANEL_MIN_SIZE, PLACEMENT_LABELS, PLACEMENTS
from .smooth import SMOOTH_METHODS

BOOL = "bool"
CHOICE = "choice"
INT = "int"
FLOAT = "float"
COLOR = "color"
OFFSET = "offset"

HOST_WINDOW = "window"   # 枠なしの小さなウィンドウ (半透明にできる)
HOST_VIEW = "view"       # ビューの描画面の子 (不透明)


class SettingsError(ValueError):
    """設定の値が直せない (知らないキー・選択肢に無い名前など)。"""


class Setting(object):
    """設定の 1 項目の定義。"""

    def __init__(self, key, kind, default, short_flag, label, choices=(), choice_labels=(),
                 minimum=None, maximum=None, description="", section="", check_label="",
                 precision=3, field_only=False):
        self.key = key                  # 設定の名前 (フラグの長い名前・保存のキー)
        self.kind = kind
        self.default = default
        self.short_flag = short_flag    # コンテキストのコマンドの短いフラグ (COLOR・OFFSET は None)
        self.label = label              # 表示名 (ツール設定のウィンドウ)
        self.choices = tuple(choices)   # CHOICE の選択肢の名前 (問い合わせはこの番号を返す)
        self.choice_labels = tuple(choice_labels) or self.choices
        self.minimum = minimum          # INT / FLOAT の範囲
        self.maximum = maximum
        self.description = description  # ツールチップ
        self.section = section          # ツール設定のウィンドウの欄 (空ならウィンドウに出さない)
        self.check_label = check_label  # BOOL のチェックボックスの横の文字
        self.precision = precision      # FLOAT の欄の小数の桁数
        self.field_only = field_only    # FLOAT をスライダーでなく数の欄だけにする (範囲が広いもの)

    @property
    def long_flag(self):
        return "-" + self.key

    def __repr__(self):
        return "Setting({!r}, {!r}, default={!r})".format(self.key, self.kind, self.default)


DEFINITIONS = (
    # -- 操作 --
    Setting("mode", CHOICE, MODES[0], "-m", "モード", choices=MODES,
            choice_labels=tuple(MODE_LABELS[m] for m in MODES),
            description="割合: 全頂点に同じ倍率 / 加算: 同じ量 / 絶対: 同じ値 / "
                        "移動: 相手のインフルエンスとのあいだだけ (パネルの上で 1 / 2 / 3 / 4 キー)",
            section="操作"),
    Setting("stepCtrl", FLOAT, 0.01, "-sc", "Ctrl の刻み", minimum=0.001, maximum=1.0,
            description="Ctrl を押しながらドラッグしたときの刻み", section="操作"),
    Setting("stepShift", FLOAT, 0.1, "-ss", "Shift の刻み", minimum=0.001, maximum=1.0,
            description="Shift を押しながらドラッグしたときの刻み", section="操作"),
    # -- パネル --
    Setting("host", CHOICE, HOST_WINDOW, "-hs", "パネルの出し方", choices=(HOST_WINDOW, HOST_VIEW),
            choice_labels=("ウィンドウ (半透明)", "ビューの中 (不透明)"),
            description="ウィンドウ: ビューの上に重ねた枠なしの小さなウィンドウ (背景を透かせる) / "
                        "ビューの中: ビューの描画面の子 (不透明。下を Qt が描き直さないため)",
            section="パネル"),
    Setting("placement", CHOICE, "topRight", "-pl", "置き場所", choices=PLACEMENTS,
            choice_labels=PLACEMENT_LABELS,
            description="ビューの 9 か所。左上のつまみで動かしたずれは、右上のボタンで戻す",
            section="パネル"),
    Setting("opacity", INT, 210, "-op", "背景の不透明度", minimum=40, maximum=255,
            description="パネルの背景の不透明度 (ウィンドウのときだけ。文字は透けない)", section="パネル"),
    Setting("panelWidth", INT, 380, "-pnw", "パネルの幅", minimum=PANEL_MIN_SIZE[0], maximum=1600,
            description="パネルの幅 (ピクセル)。パネルの左右の端・角のドラッグでも変わる。"
                        "行が入りきらない幅にはならない", section="パネル"),
    Setting("panelHeight", INT, 300, "-pnh", "パネルの高さ", minimum=PANEL_MIN_SIZE[1], maximum=1600,
            description="パネルの高さ (ピクセル)。上下の端・角のドラッグでも変わる。"
                        "入りきらない行はスクロールする (ホイール)", section="パネル"),
    Setting("decimals", INT, 3, "-dc", "数値の小数の桁数", minimum=2, maximum=6,
            description="パネルの数値の桁数 (数値の欄の最初の値も)", section="パネル"),
    Setting("sort", CHOICE, SORTS[0], "-so", "並び順", choices=SORTS,
            choice_labels=("番号順", "平均の大きい順", "名前順"),
            description="行の並び (並べ直すのは選択を変えたとき・並び順を変えたときだけ)", section="パネル"),
    Setting("influenceColor", BOOL, True, "-ic", "色",
            description="スキンのペイントのインフルエンスの一覧と同じ色の四角を出す", section="パネル",
            check_label="インフルエンスの色を表示"),
    # -- 名前 --
    Setting("nameStyle", CHOICE, NAME_STYLES[0], "-ns", "名前の出し方", choices=NAME_STYLES,
            choice_labels=("名前のみ", "一意の名前"),
            description="名前のみ: ノードの名前だけ / 一意の名前: 同じ名前があるものだけ親の名前を足す",
            section="名前"),
    Setting("namespace", BOOL, True, "-nsp", "名前空間",
            description="省くと区別できないものは、オフでも名前空間を残す", section="名前",
            check_label="名前空間を表示"),
    Setting("elideFront", BOOL, True, "-ef", "長い名前",
            description="欄に入らない名前は前を省いて末尾 (ジョイントの名前) を残す (オフなら末尾を省く)",
            section="名前", check_label="前を省く (末尾を残す)"),
    # -- ジョイントの表示 (ビューに描く) --
    Setting("hoverName", BOOL, True, "-hn", "ジョイント",
            description="行に乗せている・ドラッグしているインフルエンスへ、選んだ頂点の重心から線を引き、"
                        "ジョイントの位置に名前を出す", section="ジョイントの表示",
            check_label="乗せた行のジョイントへ線と名前を出す"),
    Setting("labelSize", INT, 14, "-ls", "文字の大きさ", minimum=8, maximum=48,
            description="ジョイントの名前の文字の大きさ (ピクセル)", section="ジョイントの表示"),
    Setting("labelBackground", BOOL, True, "-lb", "名前の背景",
            description="ジョイントの名前に背景の箱を付ける", section="ジョイントの表示",
            check_label="名前に背景を付ける"),
    Setting("lineColor", COLOR, (1.00, 0.35, 0.85), None, "線の色",
            description="ジョイントへの線と、ジョイントの位置の四角", section="ジョイントの表示"),
    Setting("labelColor", COLOR, (0.95, 0.95, 0.95), None, "名前の色",
            description="ジョイントの名前の文字", section="ジョイントの表示"),
    Setting("labelBackgroundColor", COLOR, (0.12, 0.12, 0.12), None, "背景の色",
            description="ジョイントの名前の背景 (少し透ける)", section="ジョイントの表示"),
    Setting("weightDisplay", BOOL, True, "-wd", "ウェイトの色",
            description="行に乗せている・ドラッグしているインフルエンスのウェイトを、選んだ頂点 (ソフト選択の"
                        "範囲も) の点の色で出す (0 は灰色、小さいほど青、大きいほど赤)",
            section="ジョイントの表示", check_label="乗せた行のウェイトを頂点の色で出す"),
    Setting("weightPointSize", INT, 7, "-wps", "点の大きさ", minimum=2, maximum=20,
            description="ウェイトの色の点の大きさ (ピクセル)", section="ジョイントの表示"),
    Setting("weightBackfaces", BOOL, False, "-wbf", "裏側",
            description="カメラから見て裏を向いた頂点にも、ウェイトの色の点を出す (オフなら表の頂点だけ。"
                        "ほかの物の陰になった頂点は隠さない)", section="ジョイントの表示",
            check_label="裏を向いた頂点にも点を出す"),
    # -- 最大インフルエンス数 --
    Setting("maxInfluencesEnabled", BOOL, False, "-mie", "最大数",
            description="編集のあと・頂点を選んだときに、頂点ごとの 0 でないインフルエンスをこの数までに"
                        "する (skinCluster の maintainMaxInfluences ではなく、このツールの設定。"
                        "オフにすると、ツールを使っている間に削った分は元に戻る)",
            section="最大インフルエンス数", check_label="最大インフルエンス数を守る"),
    Setting("maxInfluences", INT, 6, "-mi", "数", minimum=1, maximum=12,
            description="頂点ごとの 0 でないインフルエンスの数", section="最大インフルエンス数"),
    # -- スムーズ --
    Setting("smoothStrength", FLOAT, 0.5, "-sms", "強さ", minimum=0.01, maximum=1.0, precision=2,
            description="1 回のスムーズで、隣の頂点の平均へ寄せる割合 (1 で平均そのもの)",
            section="スムーズ"),
    Setting("smoothMethod", CHOICE, SMOOTH_METHODS[0], "-smm", "方式", choices=SMOOTH_METHODS,
            choice_labels=("均等", "距離に応じて", "コタンジェント"),
            description="均等: どの隣も同じ重みで平均 / 距離に応じて: 近い隣ほど重く (1 / 距離) / "
                        "コタンジェント: 辺の向かいの角から決める重み (割り方の偏りに最も強い)。"
                        "距離・角はスキンで変形する前の形で測る", section="スムーズ"),
    Setting("smoothIterations", INT, 3, "-smi", "回数", minimum=1, maximum=20,
            description="スムーズをくり返す回数。多いほど遠くの頂点の値まで伝わり、広くなだらかになる "
                        "(パネルのスムーズのボタンの右クリックでも変えられる)", section="スムーズ"),
    # -- 刈り取り --
    Setting("pruneAuto", BOOL, True, "-pa", "自動",
            description="編集のたびに、しきい値より小さいウェイトを 0 にして残りへ配る",
            section="刈り取り", check_label="編集のたびに自動で刈り取る"),
    Setting("pruneThreshold", FLOAT, 0.001, "-pt", "しきい値", minimum=0.00001, maximum=0.1,
            precision=5, field_only=True,
            description="これより小さいウェイトを 0 にする", section="刈り取り"),
    # -- ウィンドウに出さないもの --
    Setting("panelOffset", OFFSET, (0, 0), None, "パネルのずれ",
            description="つまみで動かしたパネルの、置き場所からのずれ (ピクセル)"),
)

_BY_KEY = dict((setting.key, setting) for setting in DEFINITIONS)
_TRUE = ("1", "true", "on", "yes")
_FALSE = ("0", "false", "off", "no")


def definition(key):
    """キーの定義 (Setting)。知らないキーなら SettingsError。"""
    try:
        return _BY_KEY[key]
    except KeyError:
        raise SettingsError("知らない設定です: {}".format(key))


def _number(key, value, cast):
    if isinstance(value, bool):
        raise SettingsError("{} は数です: {!r}".format(key, value))
    try:
        return cast(float(value)) if cast is int else cast(value)
    except (TypeError, ValueError):
        raise SettingsError("{} は数です: {!r}".format(key, value))


def normalize(key, value):
    """値を、その設定の型・選択肢・範囲に直す。直せなければ SettingsError。"""
    setting = definition(key)
    kind = setting.kind
    if kind == BOOL:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        text = str(value).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise SettingsError("{} は真偽値です: {!r}".format(key, value))
    if kind == CHOICE:
        if value in setting.choices:
            return value
        text = str(value).strip()
        if text in setting.choices:
            return text
        if text.isdigit() and int(text) < len(setting.choices):
            return setting.choices[int(text)]   # 番号 (問い合わせが返すもの) でもよい
        raise SettingsError("{} は {} のどれか (または番号) です: {!r}".format(
            key, " / ".join(setting.choices), value))
    if kind in (INT, FLOAT):
        number = _number(key, value, int if kind == INT else float)
        if setting.minimum is not None:
            number = max(setting.minimum, number)
        if setting.maximum is not None:
            number = min(setting.maximum, number)
        return number
    if kind in (COLOR, OFFSET):
        count = 3 if kind == COLOR else 2
        if isinstance(value, str):
            value = value.replace(",", " ").split()
        try:
            items = list(value)
            if len(items) != count or any(isinstance(c, bool) for c in items):
                raise ValueError
            if kind == COLOR:
                return tuple(min(1.0, max(0.0, float(c))) for c in items)
            return tuple(int(round(float(c))) for c in items)
        except (TypeError, ValueError):
            raise SettingsError("{} は {} つの数です: {!r}".format(key, count, value))
    raise SettingsError("知らない種類です: {}".format(kind))


def defaults():
    """既定値の dict。"""
    return dict((setting.key, setting.default) for setting in DEFINITIONS)


def normalize_all(data):
    """保存していた dict を、使える値だけの dict にする (知らないキーは捨て、直せない値は既定値)。"""
    values = defaults()
    if not isinstance(data, dict):
        return values
    for key in values:
        if key in data:
            try:
                values[key] = normalize(key, data[key])
            except SettingsError:
                pass
    return values


class Settings(object):
    """設定の値。変えると保存し (storage があれば)、リスナーに知らせる。

    storage は load() -> dict か None と save(dict) を持つもの (Maya では scene/prefs.py の
    OptionVarStorage。テストでは辞書で代わりをする)。リスナーは listener(key, value) で、
    値が変わったときだけ呼ぶ。
    """

    def __init__(self, storage=None):
        self._storage = storage
        self._values = normalize_all(storage.load() if storage is not None else None)
        self._listeners = []

    def value(self, key):
        definition(key)
        return self._values[key]

    def values(self):
        return dict(self._values)

    def set(self, key, value):
        """値を正規化して変える。変わったら保存してリスナーに知らせる。直した値を返す。"""
        value = normalize(key, value)
        if self._values[key] != value:
            self._values[key] = value
            self._save()
            for listener in list(self._listeners):
                listener(key, value)
        return value

    def reset(self, keys=None):
        """すべて (keys を渡せばそれだけ) 既定値に戻す (変わった項目ごとにリスナーに知らせる)。"""
        for key, value in defaults().items():
            if keys is None or key in keys:
                self.set(key, value)

    def addListener(self, listener):
        if listener not in self._listeners:
            self._listeners.append(listener)

    def removeListener(self, listener):
        if listener in self._listeners:
            self._listeners.remove(listener)

    def choiceIndex(self, key):
        """CHOICE の今の値の番号 (コンテキストのコマンドの問い合わせが返すもの)。"""
        setting = definition(key)
        if setting.kind != CHOICE:
            raise SettingsError("{} は選択肢ではありません".format(key))
        return setting.choices.index(self._values[key])

    def _save(self):
        if self._storage is not None:
            self._storage.save(self.values())
