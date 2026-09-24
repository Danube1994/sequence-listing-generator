"""
模块3：修饰名称映射校验模块

输入模块2解析出的某一行 List[ParsedFeature]，按 key 分两条路径处理：

- key == "misc_feature"：不做受控词表拦截，原样放行。词表只作为
  "已知变体清单"用于日志/统计，不具备拦截效力（这些 note 文本已经由
  用户用其他工具确认过，不需要本模块再次确认）。

- key == "modified_base"：必须按 ST.26 正文第17段 + Annex I Section 2
  Table 2 校验 mod_base 的值：
    1. 值在 Table 2 的48个受控值（47个真实缩写 + 字面值 "OTHER"）之内
       且不是 "OTHER"                        -> 合规，原样保留
    2. 值 = "OTHER"，且同一位置有非空的 note  -> 合规，原样保留
       （note 里必须是完整未缩写名称，Table 2 对 OTHER 的备注就是
       "requires note qualifier"）
    3. 值 = "OTHER" 但缺 note，或值根本不在
       Table 2 里                             -> 不合规：
         - 如果同一位置有非空 note，可以判定这条 note 已经是完整
           描述，自动转换成 misc_feature（key 改掉，只保留 note）
         - 如果没有 note 可用，无法自动合成完整名称，直接报错，
           交给用户用其他工具处理，不强行猜

Table 2 的受控值直接用 annex_i_data.py 里内嵌的数据（来自用户提供的
Annex I.xlsx"LIST OF MODIFIED NUCLEOTIDES"那张表，逐字核对过跟
STANDARD ST.26.pdf 正文 Annex I Section 2 Table 2 一致），不需要每次
运行都重新上传/读取那份 xlsx。load_table2_controlled_values() 仍然保留，
只在需要拿一份新的 Annex I.xlsx 跟内嵌数据做核对时才用得到，不是正常
流程的必经步骤。
"""

from collections import defaultdict
from dataclasses import dataclass

import openpyxl

from annex_i_data import MODIFIED_NUCLEOTIDE_VALUES
from module2_location_parser import ParsedFeature


class ModifiedBaseError(Exception):
    def __init__(self, row_name, location_raw, message):
        self.row_name = row_name
        self.location_raw = location_raw
        self.message = message
        super().__init__(f"[Name={row_name!r}, location={location_raw!r}] {message}")


@dataclass
class ConversionNote:
    row_name: str
    location_raw: str
    message: str


def load_table2_controlled_values(annex_path, sheet_name="LIST OF MODIFIED NUCLEOTIDES"):
    """
    从外部 Annex I.xlsx 读取 Table 2 受控值——仅用于拿一份新文件跟
    annex_i_data.py 里内嵌的数据核对是否一致，正常流程不需要调用这个。
    """
    wb = openpyxl.load_workbook(annex_path, data_only=True)
    ws = wb[sheet_name]
    values = set()
    for row in ws.iter_rows(min_row=2):
        cell = row[0].value
        if cell is None:
            continue
        values.add(str(cell).strip())
    return values


def review_row_features(features, row_name, table2_values=MODIFIED_NUCLEOTIDE_VALUES):
    """
    输入模块2解析出的某一行 features，返回 (reviewed_features, notes)。
    reviewed_features 与输入同构（List[ParsedFeature]），可以直接交给
    模块4/5 继续处理。notes 记录被自动转换的条目，仅用于审计留痕，
    不代表出错。校验失败会抛 ModifiedBaseError，不静默跳过。
    """
    reviewed = []
    notes = []

    # 按 clause_id（同一条原始 clause）分组，不按 location 分组——
    # 同一个位置完全可以合法地出现多条互相独立、各自完整的 modified_base
    # （比如1号残基同时有端基VP修饰和2'-OMe糖环修饰，两条各自都自带
    # mod_base，不该被硬凑成一组要求"只能有一个 mod_base"）。
    groups = defaultdict(list)
    order = []
    for f in features:
        if f.key != "modified_base":
            reviewed.append(f)
            continue
        gkey = f.clause_id
        if gkey not in groups:
            order.append(gkey)
        groups[gkey].append(f)

    for gkey in order:
        group = groups[gkey]
        loc = group[0].location.raw
        mod_base_entries = [f for f in group if f.qualifier_name == "mod_base"]
        note_entries = [f for f in group if f.qualifier_name == "note"]

        if len(mod_base_entries) != 1:
            raise ModifiedBaseError(
                row_name, loc,
                f"该 modified_base 片段应恰好有一个 mod_base qualifier，实际有 {len(mod_base_entries)} 个",
            )
        mod_base_value = mod_base_entries[0].qualifier_value
        note_value = note_entries[0].qualifier_value.strip() if note_entries else ""

        if mod_base_value in table2_values:
            if mod_base_value == "OTHER" and not note_value:
                raise ModifiedBaseError(
                    row_name, loc,
                    "mod_base=OTHER 但缺少配套的 note（未缩写全称），不合规",
                )
            reviewed.extend(group)
            continue

        # 不在 Table 2 受控值范围内
        if note_value:
            converted = ParsedFeature(
                key="misc_feature",
                location=mod_base_entries[0].location,
                qualifier_name="note",
                qualifier_value=note_value,
                raw_entry=mod_base_entries[0].raw_entry,
                clause_id=mod_base_entries[0].clause_id,
            )
            reviewed.append(converted)
            notes.append(ConversionNote(
                row_name, loc,
                f"mod_base={mod_base_value!r} 不在 Annex I Table 2 受控值内，"
                f"已自动转换为 misc_feature，note 沿用原值 {note_value!r}",
            ))
        else:
            raise ModifiedBaseError(
                row_name, loc,
                f"mod_base={mod_base_value!r} 不在 Annex I Table 2 受控值内，"
                "且没有可用的 note 全称，无法自动转换，需要人工用其他工具处理",
            )

    return reviewed, notes


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from module1_input_cleaning import load_sequence_table
    from module2_location_parser import parse_modification_text, LocationParseError

    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "序列信息-5.xlsx"
    annex_path = sys.argv[2] if len(sys.argv) > 2 else None

    if annex_path:
        table2_values = load_table2_controlled_values(annex_path)
        print(f"使用外部 Annex I.xlsx: {annex_path}")
    else:
        table2_values = MODIFIED_NUCLEOTIDE_VALUES
        print("使用内嵌的 Annex I Table 2 数据")
    print(f"Table 2 受控值共 {len(table2_values)} 个（应为 48 = 47真实缩写 + OTHER）")
    print()

    records, load_errors = load_sequence_table(xlsx_path)

    total_notes = 0
    review_errors = []
    for r in records:
        try:
            features = parse_modification_text(r.modification_text, r.name)
        except LocationParseError as e:
            review_errors.append(e)
            continue
        try:
            reviewed, notes = review_row_features(features, r.name, table2_values)
        except ModifiedBaseError as e:
            review_errors.append(e)
            continue
        total_notes += len(notes)
        tag = "modified_base->misc_feature 转换" if notes else "无需转换"
        print(f"Name={r.name}\tfeature数={len(reviewed)}\t{tag}")
        for n in notes:
            print("   ", n.message)

    print()
    print(f"共处理 {len(records)} 行，累计自动转换 {total_notes} 条，出错 {len(review_errors)} 行")
    if review_errors:
        print("=== 错误 ===")
        for e in review_errors:
            print(" -", e)
