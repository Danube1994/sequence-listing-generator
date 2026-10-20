"""
氨基酸符号定义配置：氨基酸紧凑记法解析器（模块0b）里全部符号的含义
持久化配置，跟核苷酸的 symbol_legend.py 是同一个用途、同一套持久化
机制（同目录 JSON 文件、启动时加载、GUI 表单编辑），但配置表的形状
不一样，源于氨基酸记法本身的语法跟核苷酸不是一回事：

    Xaa-Xaa-...-Xaa（连字符连接的三字母代码/自定义缩写链，可选末尾
    跟一个后缀符号，某个残基后面可以跟一个圆括号，里面是另一串连字
    符连接的"接头/偶联片段"名称）

配置分三类，对应记法语法里三种不同角色：

1. residue_abbreviations（非标准残基缩写表，可以有任意多条，界面上
   对应可以一直加行的那张表）：主链里出现、又不在 Annex I 表3标准
   20种氨基酸符号里的三字母缩写，比如 Aib -> 2-Aminoisobutyric acid。
   每条缩写要存两个信息，不是一个：
     - note：完整修饰名称，渲染时落 MOD_RES 的 /note。
     - bare_letter：裸序列（INSDSeq_sequence）里这个缩写对应写成
       什么字母。业务规则（已跟用户确认）：除甲基化、磷酸化这类"侧链
       化学骨架基本不变、只加个小基团"的修饰保留母核字母（例如
       mAla -> A、pSer -> S）外，其余一律用 'X'（例如 Aib、Cpa、Iva、
       mPal -> X），不能从化学结构直接算出来，必须逐条人工确认。

2. terminal_suffix（末端后缀符号，只有一条，界面给一组独立输入框）：
   跟在主链最后一个残基后面的后缀符号（默认 'NH2'，表示 C 端酰胺
   化），渲染时落 MOD_RES，location 固定是最后一个残基的位置，note
   文本按 terminal_suffix_note_template 生成，模板必须包含 "{name}"
   占位符，运行时替换成最后一个残基的英文全称（例如 Ser 结尾时
   "{name}" -> "Serine"，模板默认 "Amidated {name}" 得到
   "Amidated Serine"）。后缀语法本身（后缀跟在主链末尾）不可配置，
   可配置的只是符号本身和说明文字模板。

3. 圆括号子语法里用到的两张表，各自可以有任意多条：
     - greek_letter_words：希腊字母 -> 对应英文单词，比如
       'γ' -> 'gamma'。圆括号内容里紧跟在下一个片段名前面、中间没有
       分隔符的希腊字母（比如 "γGlu"）渲染时替换成"英文单词+空格"
       （得到 "gamma Glu"），这是 sequence 软件能识别的写法。
     - conjugate_fragments：圆括号内容里允许出现的、本身不是氨基酸
       的接头/偶联片段名称列表，比如 'AEEA'、'Eic'、'PEG-2'。圆括号
       内容按连字符切分后，每个片段要么是 Annex I 表3 的标准三字母
       代码，要么在这张表里，否则解析时报错（可能是新片段，需要先
       加进来；也可能是原始记法本身的录入错误，比如多打了一个连
       字符）。

4. bridges（桥连接定义表，可以有任意多条，界面上对应可以一直加行
   的那张表）：一个残基后面可以跟多个圆括号，其中和某一行"起点写法"
   完全一致的括号是桥的起点（比如 "Cys(-CH2-)" 里的 "-CH2-"），和
   "终点写法"一致的括号是桥的终点（比如 "Cys(-)" 里的 "-"）。每行一
   种桥，四个字段：
     - opener：起点括号里的写法，比如 "-CH2-"。桥两端之间用的基团
       （亚甲基、亚乙基……）靠起点写法区分：不同基团各占一行。
     - closer：终点括号里的写法，比如 "-"。
     - key：落到 XML 的特征键，只能是 CROSSLNK 或 DISULFID（两者的
       location 都是 "x..y"，标准 7.9/7.10）。
     - note：说明文字模板，可以包含 "{aa1}"/"{aa2}"，分别替换成起点
       残基和终点残基的三字母代码，比如默认模板得到
       "thioacetal bridge via a CH2 group (Cys-Cys)"。
   配对规则：从左到右扫描，每个终点配它前面最早还没配对、终点写法
   一致的起点；对不上的一律报错，不猜。

三类配置共用同一个"缩写/符号"命名空间的规则不完全等同于核苷酸版：
residue_abbreviations 和 terminal_suffix_symbol 不能跟 Annex I 表3
的标准三字母代码重名，也不能互相重名——否则解析时无法区分该按哪种
角色处理。conjugate_fragments 只在圆括号子语法里生效，跟主链的
residue_abbreviations 不共享命名空间，允许重名。

配置以 JSON 文件持久化，路径在 exe/脚本所在目录下的
aa_symbol_legend.json，程序启动时自动加载，找不到或损坏就退回内置
默认值（对应 SRP260114 真实项目材料反推确认的 Aib/Cpa/mAla/Iva/
mPal/pSer 六条缩写、NH2 后缀、以及希腊字母 α/β/γ 三条）。
"""

import json
import os
import string
import sys

MAX_ENTRIES = 50            # 三张可加行的表共用同一个行数上限
MIN_BLANK_SLOTS = 10         # residue_abbreviations 表界面至少留够这么多空白行
GREEK_MIN_BLANK_SLOTS = 2    # greek_letter_words 表界面至少留够这么多空白行
FRAGMENT_MIN_BLANK_SLOTS = 3  # conjugate_fragments 表界面至少留够这么多空白行
BRIDGE_MIN_BLANK_SLOTS = 2    # bridges 表界面至少留够这么多空白行
BRIDGE_KEYS = ("CROSSLNK", "DISULFID")
BRIDGE_NOTE_PLACEHOLDERS = {"aa1", "aa2"}

DEFAULT_RESIDUE_ABBREVIATIONS = {
    "Aib": {"note": "2-Aminoisobutyric acid", "bare_letter": "X"},
    "Cpa": {"note": "Chlorophenylalanine", "bare_letter": "X"},
    "mAla": {"note": "N-Methylalanine", "bare_letter": "A"},
    "Iva": {"note": "Isovaline", "bare_letter": "X"},
    "mPal": {"note": "3-(4-Pyridyl)-alanine", "bare_letter": "X"},
    "pSer": {"note": "Phosphoserine", "bare_letter": "S"},
}
DEFAULT_TERMINAL_SUFFIX_SYMBOL = "NH2"
DEFAULT_TERMINAL_SUFFIX_NOTE_TEMPLATE = "Amidated {name}"
DEFAULT_GREEK_LETTER_WORDS = {
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
}
DEFAULT_CONJUGATE_FRAGMENTS = ["AEEA", "Eic", "PEG-2"]
DEFAULT_BRIDGES = [
    {
        "opener": "-CH2-",
        "closer": "-",
        "key": "CROSSLNK",
        "note": "thioacetal bridge via a CH2 group ({aa1}-{aa2})",
    },
]


def default_config():
    return {
        "bridges": [dict(b) for b in DEFAULT_BRIDGES],
        "residue_abbreviations": {k: dict(v) for k, v in DEFAULT_RESIDUE_ABBREVIATIONS.items()},
        "terminal_suffix_symbol": DEFAULT_TERMINAL_SUFFIX_SYMBOL,
        "terminal_suffix_note_template": DEFAULT_TERMINAL_SUFFIX_NOTE_TEMPLATE,
        "greek_letter_words": dict(DEFAULT_GREEK_LETTER_WORDS),
        "conjugate_fragments": list(DEFAULT_CONJUGATE_FRAGMENTS),
    }


def _config_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_config_dir(), "aa_symbol_legend.json")


class LegendError(Exception):
    pass


def _standard_three_letter_codes():
    from annex_i_data import AMINO_ACID_SYMBOLS
    return {code for code, _definition in AMINO_ACID_SYMBOLS.values()}


def _standard_single_letters():
    from annex_i_data import AMINO_ACID_SYMBOLS
    return set(AMINO_ACID_SYMBOLS.keys())


def validate_config(config):
    """
    config: dict，形如 default_config() 的结构。校验通过原样返回，
    不合法抛 LegendError。
    """
    abbreviations = config.get("residue_abbreviations", {})
    suffix_symbol = config.get("terminal_suffix_symbol", "")
    suffix_template = config.get("terminal_suffix_note_template", "")
    greek_words = config.get("greek_letter_words", {})
    fragments = config.get("conjugate_fragments", [])

    if len(abbreviations) > MAX_ENTRIES:
        raise LegendError(f"残基修饰缩写最多允许 {MAX_ENTRIES} 条，当前有 {len(abbreviations)} 条")

    standard_codes = _standard_three_letter_codes()
    standard_letters = _standard_single_letters()

    for abbr, entry in abbreviations.items():
        if not abbr:
            raise LegendError("残基修饰缩写不能为空")
        if not isinstance(entry, dict):
            raise LegendError(f"缩写 {abbr!r} 的配置格式不对")
        note = entry.get("note", "")
        bare_letter = entry.get("bare_letter", "")
        if not note:
            raise LegendError(f"缩写 {abbr!r} 缺少完整修饰名称（note）")
        if not bare_letter:
            raise LegendError(f"缩写 {abbr!r} 缺少裸序列字母")
        if bare_letter != "X" and bare_letter not in standard_letters:
            raise LegendError(
                f"缩写 {abbr!r} 的裸序列字母 {bare_letter!r} 不合法——"
                "只能是 'X'，或者 Annex I 表3 里的标准单字母符号"
            )
        if abbr in standard_codes:
            raise LegendError(f"残基修饰缩写 {abbr!r} 跟 Annex I 表3 的标准三字母代码重名了")

    if not suffix_symbol:
        raise LegendError("末端后缀符号不能为空")
    if suffix_symbol in standard_codes:
        raise LegendError(f"末端后缀符号 {suffix_symbol!r} 跟 Annex I 表3 的标准三字母代码重名了")
    if suffix_symbol in abbreviations:
        raise LegendError(f"末端后缀符号 {suffix_symbol!r} 跟残基修饰缩写表里的 {suffix_symbol!r} 重名了")
    if not suffix_template:
        raise LegendError("末端后缀说明文字模板不能为空")
    if "{name}" not in suffix_template:
        raise LegendError("末端后缀说明文字模板必须包含 {name} 占位符，用来代入最后一个残基的英文全称")

    for g, word in greek_words.items():
        if not g:
            raise LegendError("希腊字母不能为空")
        if not word:
            raise LegendError(f"希腊字母 {g!r} 缺少对应的英文单词")

    seen = set()
    for frag in fragments:
        if not frag:
            raise LegendError("接头/偶联片段名称不能为空")
        if frag in seen:
            raise LegendError(f"接头/偶联片段名称 {frag!r} 重复了")
        seen.add(frag)

    bridges = config.get("bridges", [])
    if len(bridges) > MAX_ENTRIES:
        raise LegendError(f"桥连接定义最多允许 {MAX_ENTRIES} 条，当前有 {len(bridges)} 条")

    openers = {}
    for b in bridges:
        if not isinstance(b, dict):
            raise LegendError("桥连接定义的配置格式不对")
        opener, closer = b.get("opener", ""), b.get("closer", "")
        key, note = b.get("key", ""), b.get("note", "")
        if not opener:
            raise LegendError("桥连接的起点写法不能为空")
        if not closer:
            raise LegendError(f"桥连接 {opener!r} 缺少终点写法")
        if opener == closer:
            raise LegendError(f"桥连接的起点写法和终点写法不能相同（都是 {opener!r}）")
        if key not in BRIDGE_KEYS:
            raise LegendError(
                f"桥连接 {opener!r} 的特征键 {key!r} 不合法，只能是 {' 或 '.join(BRIDGE_KEYS)}"
            )
        if not note:
            raise LegendError(f"桥连接 {opener!r} 缺少 note 模板")
        try:
            fields = {name for _lit, name, _spec, _conv in string.Formatter().parse(note) if name}
        except ValueError:
            raise LegendError(f"桥连接 {opener!r} 的 note 模板里花括号不匹配")
        bad = fields - BRIDGE_NOTE_PLACEHOLDERS
        if bad:
            raise LegendError(
                f"桥连接 {opener!r} 的 note 模板里有不认识的占位符 {sorted(bad)}，"
                "只支持 {aa1}、{aa2}"
            )
        if opener in openers:
            raise LegendError(f"桥连接起点写法 {opener!r} 重复定义了")
        openers[opener] = b

    for b in bridges:
        if b["closer"] in openers:
            raise LegendError(
                f"桥连接的终点写法 {b['closer']!r} 跟另一条桥连接的起点写法重名了，"
                "解析时无法区分"
            )

    return config


def load_config():
    """读取持久化配置；文件不存在、损坏或结构不全时用默认值补齐，不报错中断程序。"""
    cfg = default_config()
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if isinstance(data.get("residue_abbreviations"), dict):
                    cleaned = {}
                    for abbr, entry in data["residue_abbreviations"].items():
                        if not abbr or not isinstance(entry, dict):
                            continue
                        note = entry.get("note")
                        bare_letter = entry.get("bare_letter")
                        if note and bare_letter:
                            cleaned[str(abbr)] = {
                                "note": str(note),
                                "bare_letter": str(bare_letter).strip().upper(),
                            }
                    if cleaned:
                        cfg["residue_abbreviations"] = cleaned
                for key in ("terminal_suffix_symbol", "terminal_suffix_note_template"):
                    if data.get(key):
                        cfg[key] = str(data[key])
                if isinstance(data.get("greek_letter_words"), dict):
                    cleaned = {
                        str(k): str(v) for k, v in data["greek_letter_words"].items() if k and v
                    }
                    if cleaned:
                        cfg["greek_letter_words"] = cleaned
                if isinstance(data.get("conjugate_fragments"), list):
                    cleaned = [str(f) for f in data["conjugate_fragments"] if f]
                    if cleaned:
                        cfg["conjugate_fragments"] = cleaned
                # 旧版本保存的配置文件没有 bridges 这个键，保持默认；键存在
                # （哪怕是空列表）说明是用户保存过的，按用户保存的为准。
                if isinstance(data.get("bridges"), list):
                    cfg["bridges"] = [
                        {
                            "opener": str(b.get("opener", "")),
                            "closer": str(b.get("closer", "")),
                            "key": str(b.get("key", "")),
                            "note": str(b.get("note", "")),
                        }
                        for b in data["bridges"] if isinstance(b, dict)
                    ]
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(config):
    validate_config(config)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2, sort_keys=True)
