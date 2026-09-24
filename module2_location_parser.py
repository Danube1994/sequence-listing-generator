"""
模块2：修饰信息字符串解析模块（location 语法解析器）

输入：模块1产出的 SequenceRecord.modification_text，形如
    misc_feature 1 /note="2'-O-methoxy modification (2'-OMe)";misc_feature 1^2 /note="Phosphorothioate internucleotide linkage";...
或者一条 feature 里带多个 qualifier（比如 modified_base 的 mod_base+note
组合，官方 Annex I 第17段 Example 2 就是这么写的），中间用空格隔开、
不用分号：
    modified_base 1 /mod_base="OTHER" /note="2'-O-methoxy modification (2'-OMe)";

解析分两步：
1. 先扫描出每条 feature 的"起点"：<key> <location> 后面紧跟一个
   /qualname="——这个位置标志着一条新 feature 的开始。一条 feature 的
   范围是从它的起点到下一条 feature 的起点（或字符串末尾）为止，中间
   允许出现一个或多个 /qualname="value"，彼此之间只能用空白分隔，不需要
   分号（分号是不同 feature 之间的分隔符，不是同一 feature 内部
   qualifier 之间的分隔符）。
2. 在每条 feature 的范围内，再扫描出全部 /qualname="value" 对，逐一
   校验完整覆盖（不允许中间夹杂无法识别的残留字符），一个 qualifier
   对应一条 ParsedFeature——下游模块3/5会按 (key, location) 把同一条
   modified_base feature 的多个 qualifier 重新聚合回一个 XML 节点。

不做"先按分号切分、再逐条匹配"的两步处理——分号既是 feature 之间的
分隔符，也可能是错位数据本身的第一个字符，两步法会在后一种情况下切错
位置，参见 序列信息-3.xlsx 那次分号错位的真实案例。

location 语法方面，经过 序列信息-1.xlsx ~ -4.xlsx 四轮迭代确认，这个
项目已经定型为只有两种原子形式（详见对话记录）：
    - 单点：x                    例：1
    - 相邻位间连接：x^(x+1)       例：1^2

不再支持（也不应该悄悄兼容）区间 x..y、逗号并列、边界符 <x/>x、
以及 join()/order()/complement() —— 这些是这个项目已经明确放弃的旧写法，
一旦解析器又遇到，说明数据格式发生了回退或异常，必须报错而不是静默处理。
"""

import re
from dataclasses import dataclass


class LocationParseError(Exception):
    def __init__(self, row_name, message, context=""):
        self.row_name = row_name
        self.message = message
        self.context = context
        super().__init__(f"[Name={row_name!r}] {message} | 相关片段: {context!r}")


@dataclass
class LocationDescriptor:
    kind: str            # 'point' or 'bond'
    position: int = None       # kind == 'point' 时有效
    bond_from: int = None      # kind == 'bond' 时有效
    bond_to: int = None        # kind == 'bond' 时有效
    raw: str = ""

    def min_pos(self):
        return self.position if self.kind == "point" else self.bond_from

    def max_pos(self):
        return self.position if self.kind == "point" else self.bond_to


@dataclass
class ParsedFeature:
    key: str
    location: LocationDescriptor
    qualifier_name: str
    qualifier_value: str
    raw_entry: str
    clause_id: int = -1  # 同一条原始 clause 产出的多个 qualifier 共享同一个 clause_id，
                          # 用于区分"同一个 feature 内部的多个 qualifier"和
                          # "同一位置的多条互相独立的 feature"（下游模块3靠这个分组）


# 一条 feature 的起点：<key> <location> 后面紧跟一个 /qualname="
_FEATURE_START_RE = re.compile(r'(?P<key>[^\s;]+)\s+(?P<loc>[^\s;]+)\s*(?=/\w+=")')

# 一条 feature 内部的单个 qualifier：/qualname="value"
# value 用非贪婪匹配：本项目数据里 value 从不包含字面双引号，所以遇到的
# 第一个 " 就是真正的收尾。
_QUALIFIER_RE = re.compile(r'/(?P<qname>\w+)="(?P<qval>.*?)"', re.DOTALL)


def _parse_location(raw, row_name, context):
    if raw.isdigit():
        return LocationDescriptor(kind="point", position=int(raw), raw=raw)

    if "^" in raw:
        parts = raw.split("^")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise LocationParseError(row_name, f"位间连接符格式不合法: {raw!r}", context)
        a, b = int(parts[0]), int(parts[1])
        if b != a + 1:
            raise LocationParseError(
                row_name, f"位间连接符两端必须相邻 (x, x+1)，实际是 {raw!r}", context
            )
        return LocationDescriptor(kind="bond", bond_from=a, bond_to=b, raw=raw)

    # 已知但本项目明确放弃的旧写法：单独报错说明，不当成语法错误笼统处理
    if raw.startswith(("join(", "order(", "complement(")):
        raise LocationParseError(
            row_name,
            f"出现了本项目已放弃的 location operator 写法: {raw!r}，"
            "请确认是否为新情况，不应静默兼容",
            context,
        )
    if any(sym in raw for sym in ("<", ">", "..", ",")):
        raise LocationParseError(
            row_name,
            f"出现了本项目已放弃的 location 语法（区间/并列/边界符）: {raw!r}，"
            "请确认是否为新情况，不应静默兼容",
            context,
        )

    raise LocationParseError(row_name, f"无法识别的 location 语法: {raw!r}", context)


def _parse_qualifiers(span, row_name, context):
    """
    在一条 feature 的范围内扫描出全部 /qualname="value"，校验完整覆盖
    （不允许中间夹杂无法识别的残留字符，只允许空白）。
    """
    matches = list(_QUALIFIER_RE.finditer(span))
    if not matches:
        raise LocationParseError(row_name, "feature 里没有找到任何 qualifier", context)

    pos = 0
    qualifiers = []
    for qm in matches:
        gap = span[pos:qm.start()]
        if not re.fullmatch(r"\s*", gap):
            raise LocationParseError(
                row_name, f"qualifier 之间存在无法识别的内容: {gap!r}", context
            )

        qual_value = qm.group("qval")
        if qual_value.startswith(";") or qual_value.endswith(";"):
            raise LocationParseError(
                row_name,
                f"qualifier 值首尾出现多余分号（疑似分隔符错位）: {qual_value!r}",
                context,
            )
        qualifiers.append((qm.group("qname"), qual_value))
        pos = qm.end()

    trailing = span[pos:]
    if not re.fullmatch(r"\s*", trailing):
        raise LocationParseError(
            row_name, f"feature 末尾存在无法识别的内容: {trailing!r}", context
        )

    return qualifiers


def parse_modification_text(text, row_name):
    """
    返回 List[ParsedFeature]。text 为空/None 视为"该序列没有额外修饰"，返回空列表。
    一条 feature 内部可以有一个或多个 qualifier（比如 mod_base+note 组合），
    每个 qualifier 各自产出一条 ParsedFeature，key/location 相同，方便下游
    模块按 (key, location) 重新聚合。解析失败时抛出 LocationParseError，
    不静默跳过、不猜测——包括扫描不到任何 feature、feature 之间/qualifier
    之间存在无法识别的残留字符、qualifier 值首尾出现多余分号（分隔符错位的
    典型症状）等情况。
    """
    if text is None:
        return []
    text = text.strip()
    if not text:
        return []
    text = text.rstrip(";").strip()

    starts = list(_FEATURE_START_RE.finditer(text))
    if not starts:
        raise LocationParseError(row_name, "未能从修饰信息中解析出任何 feature", text)
    if starts[0].start() != 0:
        raise LocationParseError(
            row_name, f"字符串开头存在无法识别的内容: {text[:starts[0].start()]!r}", text
        )

    features = []
    for i, m in enumerate(starts):
        quals_start = m.end()
        quals_end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        span = text[quals_start:quals_end]

        if i + 1 < len(starts):
            sep_match = re.search(r";\s*$", span)
            if not sep_match:
                raise LocationParseError(
                    row_name, "两条 feature 之间缺少分号分隔", span
                )
            span = span[:sep_match.start()]

        location = _parse_location(m.group("loc"), row_name, m.group(0))
        qualifiers = _parse_qualifiers(span, row_name, m.group(0) + span)

        for qname, qvalue in qualifiers:
            features.append(ParsedFeature(
                key=m.group("key"),
                location=location,
                qualifier_name=qname,
                qualifier_value=qvalue,
                raw_entry=m.group(0) + span,
                clause_id=i,
            ))

    return features


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from module1_input_cleaning import load_sequence_table

    path = sys.argv[1] if len(sys.argv) > 1 else "序列信息-4.xlsx"
    records, errors = load_sequence_table(path)

    total_features = 0
    parse_errors = []
    for r in records:
        try:
            features = parse_modification_text(r.modification_text, r.name)
        except LocationParseError as e:
            parse_errors.append(e)
            continue
        total_features += len(features)
        print(f"Name={r.name}\tfeature数={len(features)}\t"
              f"locations={[f.location.raw for f in features]}")

    print()
    print(f"共解析 {len(records)} 行，成功 {len(records) - len(parse_errors)} 行，"
          f"失败 {len(parse_errors)} 行，累计 feature {total_features} 条")
    if parse_errors:
        print("=== 解析错误 ===")
        for e in parse_errors:
            print(" -", e)
