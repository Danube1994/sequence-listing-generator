"""
模块7：校验/报错定位模块

把模块1-4在整批数据处理过程中抛出的所有错误汇总起来，统一格式后
导出成一份 Excel 报告（而不是只在终端打印一堆文字），方便直接对照
着源 Excel 逐行修改，不用重跑好几次脚本才能把问题看全。

各模块的异常字段本来不统一（分开设计留下的历史原因）：
    InputCleaningError       (模块1) -> row_name, message
    LocationParseError       (模块2) -> row_name, message, context
    ModifiedBaseError        (模块3) -> row_name, location_raw, message
    PositionConsistencyError (模块4) -> row_name, message, context
这里统一归一化成 ValidationIssue(row_name, stage, message, context)。

模块1就失败的行不会再进入模块2-4（没有清洗后的序列可用），但依然会
被计入报告，不会因为提前出局就从报告里消失。同一行只要某一步出错就
不继续往下跑（比如模块2解析失败了，模块3/4自然拿不到东西校验），
但不同行之间互不影响，一行出错不会打断其它行的处理。
"""

from dataclasses import dataclass

import openpyxl
from openpyxl.styles import Font, PatternFill

from annex_i_data import MODIFIED_NUCLEOTIDE_VALUES
from module1_input_cleaning import load_sequence_table
from module2_location_parser import parse_modification_text, LocationParseError
from module3_mod_base_review import (
    review_row_features, ModifiedBaseError, load_table2_controlled_values,
)
from module4_position_consistency import validate_row, PositionConsistencyError


@dataclass
class ValidationIssue:
    row_name: str
    stage: str
    message: str
    context: str = ""


def normalize_issue(exc, stage):
    row_name = getattr(exc, "row_name", "?")
    message = getattr(exc, "message", str(exc))
    context = getattr(exc, "context", None)
    if context is None:
        context = getattr(exc, "location_raw", "")
    return ValidationIssue(
        row_name=str(row_name), stage=stage, message=message, context=str(context)
    )


def run_full_validation(xlsx_path, annex_path=None):
    """
    跑完模块1->2->3->4，返回 (ok_records, issues)。
    ok_records: List[Tuple[SequenceRecord, List[ParsedFeature]]]，全部校验通过的行。
    issues: List[ValidationIssue]，按数据原始顺序汇总的所有问题。

    annex_path 缺省时使用内嵌的 Annex I Table 2 数据；只有需要拿一份
    新的 Annex I.xlsx 跟内嵌数据核对是否一致时，才传这个参数。
    """
    table2_values = (
        load_table2_controlled_values(annex_path) if annex_path else MODIFIED_NUCLEOTIDE_VALUES
    )
    records, load_errors = load_sequence_table(xlsx_path)

    issues = [normalize_issue(e, "模块1 输入清洗") for e in load_errors]
    ok_records = []

    for r in records:
        try:
            features = parse_modification_text(r.modification_text, r.name)
        except LocationParseError as e:
            issues.append(normalize_issue(e, "模块2 location解析"))
            continue
        try:
            reviewed, _notes = review_row_features(features, r.name, table2_values)
        except ModifiedBaseError as e:
            issues.append(normalize_issue(e, "模块3 修饰名称映射"))
            continue
        try:
            validate_row(reviewed, r.name, r.length)
        except PositionConsistencyError as e:
            issues.append(normalize_issue(e, "模块4 位置一致性"))
            continue
        ok_records.append((r, reviewed))

    return ok_records, issues


def write_report(issues, path):
    """把 issues 写成一份 Excel 报告：Name / 出错阶段 / 错误信息 / 相关片段"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "校验报告"

    headers = ["Name", "出错阶段", "错误信息", "相关片段"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDDDDD")

    for issue in issues:
        ws.append([issue.row_name, issue.stage, issue.message, issue.context])

    widths = {"A": 10, "B": 20, "C": 70, "D": 70}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"

    wb.save(path)


if __name__ == "__main__":
    import sys

    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "序列信息-5.xlsx"
    annex_path = sys.argv[2] if len(sys.argv) > 2 else None  # 缺省用内嵌数据
    report_path = sys.argv[3] if len(sys.argv) > 3 else "校验报告.xlsx"

    ok_records, issues = run_full_validation(xlsx_path, annex_path)

    print(f"通过 {len(ok_records)} 行，出错 {len(issues)} 条")
    for issue in issues:
        print(f" - [{issue.stage}] Name={issue.row_name}: {issue.message}")

    if issues:
        write_report(issues, report_path)
        print(f"已生成校验报告: {report_path}")
    else:
        print("没有问题，未生成报告文件")
