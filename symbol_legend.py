"""
符号定义配置：紧凑记法解析器（模块0）里全部符号的含义现在都可配置，
不再有代码写死的部分。

配置分两类，对应紧凑记法语法里两种不同的角色：

1. residue_modifiers（残基修饰符号表，可以有任意多条，界面上对应
   可以一直加行的那张表）：紧跟在碱基字母后面、描述这个残基本身带
   什么修饰的符号，比如 m -> 2'-O-methoxy modification (2'-OMe)。
   渲染时落 modified_base + /mod_base + /note。

2. 三个结构性符号，各自只有一条，界面上各给一组独立的输入框：
   - ps_link：磷硫代酯键符号（默认 's'），描述跟下一个残基（或末尾
     接头）之间是什么连接方式。渲染时落 misc_feature，location 用
     "x^x+1" 的位间连接写法。
   - vp_prefix：开头前缀符号（默认 'VP'），描述1号残基带的端基修饰。
     渲染时落 modified_base，位置固定是1号残基。
   - linker_note_template：末端接头（方括号里的名称）说明文字模板，
     必须包含 "{name}" 占位符，运行时替换成方括号里实际写的名称。
     方括号语法本身（用方括号包裹接头名）不可配置，可配置的只是
     说明文字的模板。渲染时落 misc_feature。

这三个结构性符号的"符号本身"和"残基修饰符号表"共用同一个命名空间：
不能互相重名（比如 ps_link 定义成 'm'，就不能再在残基修饰符号表里
也定义一个 'm'），否则解析时无法区分该按哪种角色处理。

配置以 JSON 文件持久化，路径在 exe/脚本所在目录下的
symbol_legend.json，程序启动时自动加载，找不到或损坏就退回内置默认值
（对应现有真实数据：m、f、s、VP、以及项目里见过的接头说明文字模板）。
"""

import json
import os
import sys

MAX_ENTRIES = 50            # 残基修饰符号表的行数上限
MIN_BLANK_SLOTS = 10         # 界面至少要留够这么多空白行

DEFAULT_RESIDUE_MODIFIERS = {
    "m": "2'-O-methoxy modification (2'-OMe)",
    "f": "2'-fluoro modification (2'-F)",
}
DEFAULT_PS_LINK_SYMBOL = "s"
DEFAULT_PS_LINK_NOTE = "Phosphorothioate internucleotide linkage"
DEFAULT_VP_PREFIX_SYMBOL = "VP"
DEFAULT_VP_NOTE = "(E)-Vinylphosphonate ((E)-VP) modification"
DEFAULT_LINKER_NOTE_TEMPLATE = (
    "Linker ({name}) linked via Phosphorothioate internucleotide linkage at 3' terminus"
)


def default_config():
    return {
        "residue_modifiers": dict(DEFAULT_RESIDUE_MODIFIERS),
        "ps_link_symbol": DEFAULT_PS_LINK_SYMBOL,
        "ps_link_note": DEFAULT_PS_LINK_NOTE,
        "vp_prefix_symbol": DEFAULT_VP_PREFIX_SYMBOL,
        "vp_note": DEFAULT_VP_NOTE,
        "linker_note_template": DEFAULT_LINKER_NOTE_TEMPLATE,
    }


def _config_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_config_dir(), "symbol_legend.json")


class LegendError(Exception):
    pass


def validate_config(config):
    """
    config: dict，形如 default_config() 的结构。校验通过原样返回，
    不合法抛 LegendError。
    """
    residue_modifiers = config.get("residue_modifiers", {})
    ps_symbol = config.get("ps_link_symbol", "")
    ps_note = config.get("ps_link_note", "")
    vp_symbol = config.get("vp_prefix_symbol", "")
    vp_note = config.get("vp_note", "")
    linker_template = config.get("linker_note_template", "")

    if len(residue_modifiers) > MAX_ENTRIES:
        raise LegendError(f"残基修饰符号最多允许 {MAX_ENTRIES} 条，当前有 {len(residue_modifiers)} 条")

    for symbol, meaning in residue_modifiers.items():
        if not symbol:
            raise LegendError("残基修饰符号不能为空")
        if not meaning:
            raise LegendError(f"符号 {symbol!r} 缺少对应的修饰说明")

    if not ps_symbol:
        raise LegendError("磷硫代酯键符号不能为空")
    if not ps_note:
        raise LegendError("磷硫代酯键符号缺少说明文字")
    if not vp_symbol:
        raise LegendError("端基前缀符号不能为空")
    if not vp_note:
        raise LegendError("端基前缀符号缺少说明文字")
    if not linker_template:
        raise LegendError("接头说明文字模板不能为空")
    if "{name}" not in linker_template:
        raise LegendError("接头说明文字模板必须包含 {name} 占位符，用来代入方括号里的接头名称")

    structural = {ps_symbol: "磷硫代酯键符号", vp_symbol: "端基前缀符号"}
    if ps_symbol == vp_symbol:
        raise LegendError(f"磷硫代酯键符号和端基前缀符号不能相同（都是 {ps_symbol!r}）")
    for symbol in residue_modifiers:
        if symbol in structural:
            raise LegendError(
                f"残基修饰符号 {symbol!r} 跟{structural[symbol]}重名了，两者不能相同"
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
                if isinstance(data.get("residue_modifiers"), dict):
                    cfg["residue_modifiers"] = {
                        str(k): str(v) for k, v in data["residue_modifiers"].items() if k and v
                    }
                for key in ("ps_link_symbol", "ps_link_note", "vp_prefix_symbol",
                            "vp_note", "linker_note_template"):
                    if data.get(key):
                        cfg[key] = str(data[key])
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(config):
    validate_config(config)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2, sort_keys=True)


# ---- 向后兼容的旧接口（只操作残基修饰符号表这一部分） ----

def load_legend():
    return load_config()["residue_modifiers"]
