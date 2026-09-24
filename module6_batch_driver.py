"""
模块6：批量驱动模块

把模块1-5串起来跑完一整批数据，并把每条序列生成的 <SequenceData>
打包进一个良构的 <ST26SequenceListing> 根元素里，产出一份可以整体
导入 WIPO Sequence 软件的单一 XML 文件。

根元素结构按 Annex II 的 DTD 原文（核对过 PDF 里 <!ELEMENT ST26SequenceListing ...>
的实际定义，不是只看正文的人话描述）实现：

    <!ELEMENT ST26SequenceListing (
        (ApplicantFileReference | (ApplicationIdentification, ApplicantFileReference?)),
        EarliestPriorityApplicationIdentification?,
        (ApplicantName, ApplicantNameLatin?)?,
        (InventorName, InventorNameLatin?)?,
        InventionTitle+,
        SequenceTotalQuantity,
        SequenceData+
    )>

关键点：开头这个 `(ApplicantFileReference | (ApplicationIdentification, ...))`
选择组整体没有被 `?` 包裹——也就是说 ApplicantFileReference 和
ApplicationIdentification 虽然正文人话描述成"看申请阶段决定填哪个"，
但 DTD 语法层面**至少必须出现一个，不能两个都不写**，早期版本的模块6
忽略了这条，两个都没生成，导致根元素从第一个子元素开始就跟 DTD 期望
的结构对不上，WIPO Sequence 的校验器会因为这个开局错位、把后面几乎
每个元素都连带判定为不合规（表现为错误数接近文件总行数的连锁报错）。

分三类处理：

1. 技术性、跟具体这份申请的实际内容无关，脚本可以放心自动生成的：
   - XML 声明 + DOCTYPE（标准原文固定写法，第39段(a)(b)）
   - dtdVersion="V1_3"（DTD版本号，不是申请信息）
   - productionDate（脚本运行当天日期，ST.2格式 CCYY-MM-DD）
   - softwareName / softwareVersion / fileName（描述生成文件的软件，可选）
   - SequenceTotalQuantity（= 序列条数，自动统计，不需要人工填）

2. DTD 语法层面必须至少出现、但内容是真实申请信息、脚本不该替你编造的：
   - ApplicantFileReference：放在根元素最前面，满足上面那条强制的选择组，
     内容留空占位。等确认这份申请是否已经拿到申请号后，你可以在软件里
     直接填这里的值，或者整个换成 ApplicationIdentification（含
     IPOfficeCode / ApplicationNumberText / FilingDate）。
   - InventionTitle：DTD 要求至少一个（InventionTitle+），这里生成
     languageCode="en" 的空内容占位元素，实际标题文字必须你自己补上。

3. DTD 里其实是可选的（外层整体包了一层 `?`，注释也写明"ApplicantName
   和 InventorName 在这份 DTD 里是可选的，为了方便不同编码方案之间转换"），
   但保留占位方便你在软件里一眼看到待填字段：
   - ApplicantName（languageCode="en"，空内容占位）

   完全不生成、等你按实际情况在软件里添加的：
   - ApplicationIdentification（如果已有申请号，用这个替换掉
     ApplicantFileReference）
   - EarliestPriorityApplicationIdentification（是否要求优先权）
   - InventorName / InventorNameLatin（本身就是可选项，不强行补空）
"""

import datetime
import os
import xml.etree.ElementTree as ET

from annex_i_data import MODIFIED_NUCLEOTIDE_VALUES
from module1_input_cleaning import load_sequence_table
from module2_location_parser import parse_modification_text, LocationParseError
from module3_mod_base_review import (
    review_row_features, ModifiedBaseError, load_table2_controlled_values,
)
from module4_position_consistency import validate_row, PositionConsistencyError
from module5_xml_generation import build_sequence_data, escape_apostrophes

DTD_VERSION = "V1_3"
XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'
DOCTYPE_LINE = (
    '<!DOCTYPE ST26SequenceListing PUBLIC "-//WIPO//DTD Sequence Listing 1.3//EN" '
    '"ST26SequenceListing_V1_3.dtd">'
)


class BatchProcessingError(Exception):
    """汇总一批数据里所有出错的行，不在第一条出错就中断整批。"""
    def __init__(self, row_errors):
        self.row_errors = row_errors
        detail = "\n".join(str(e) for e in row_errors)
        super().__init__(f"共 {len(row_errors)} 行处理失败:\n{detail}")


def process_records(records, table2_values):
    """
    跑完模块2->3->4，返回 (成功的 (record, features) 列表, 错误列表)。
    不在第一条出错就中断，收集所有错误一起报。
    """
    ok = []
    errors = []
    for r in records:
        try:
            features = parse_modification_text(r.modification_text, r.name)
            reviewed, _notes = review_row_features(features, r.name, table2_values)
            validate_row(reviewed, r.name, r.length)
        except (LocationParseError, ModifiedBaseError, PositionConsistencyError) as e:
            errors.append(e)
            continue
        ok.append((r, reviewed))
    return ok, errors


def build_sequence_listing(sequence_data_elements, file_name="sequence_listing.xml",
                            software_name="module6_batch_driver", software_version="0.1"):
    """
    sequence_data_elements: 已经生成好的 <SequenceData> ET.Element 列表
    （模块5的 build_sequence_data，或氨基酸版模块5b的 build_aa_sequence_data
    产出的元素），本函数只管拼根元素、不关心这些元素是核苷酸还是氨基酸
    序列生成的——根元素这一级的 DTD 结构跟 moltype 无关，两条流水线
    共用同一份根元素组装逻辑，不重复实现一遍。
    """
    root = ET.Element("ST26SequenceListing", {
        "dtdVersion": DTD_VERSION,
        "fileName": os.path.basename(file_name),
        "softwareName": software_name,
        "softwareVersion": software_version,
        "productionDate": datetime.date.today().isoformat(),
    })

    # DTD 强制要求：((ApplicantFileReference | (ApplicationIdentification,
    # ApplicantFileReference?)), ...) 这一组必须至少出现一个，不能整体省略。
    # 目前不知道这份申请是否已经拿到申请号，先用 ApplicantFileReference 占位
    # （留空），等确认阶段后你在 WIPO Sequence 里补内容，或者整个换成
    # ApplicationIdentification（含 IPOfficeCode/ApplicationNumberText/FilingDate）。
    applicant_file_reference = ET.SubElement(root, "ApplicantFileReference")
    applicant_file_reference.text = ""

    # ApplicantName 在 DTD 里其实是可选的（整体包了一层 ?），这里仍然保留占位，
    # 方便你在软件里直接看到待填字段，不是 DTD 强制要求。
    applicant_name = ET.SubElement(root, "ApplicantName", languageCode="en")
    applicant_name.text = ""  # 占位，需要在 WIPO Sequence 里补上真实申请人名称
    invention_title = ET.SubElement(root, "InventionTitle", languageCode="en")
    invention_title.text = ""  # 占位，需要在 WIPO Sequence 里补上真实发明名称

    ET.SubElement(root, "SequenceTotalQuantity").text = str(len(sequence_data_elements))

    for sequence_data in sequence_data_elements:
        root.append(sequence_data)

    return root


def write_sequence_listing_file(path, xlsx_path, annex_path=None, **kwargs):
    """annex_path 缺省时使用内嵌的 Annex I Table 2 数据。"""
    table2_values = (
        load_table2_controlled_values(annex_path) if annex_path else MODIFIED_NUCLEOTIDE_VALUES
    )
    records, load_errors = load_sequence_table(xlsx_path)
    ok_records, proc_errors = process_records(records, table2_values)

    all_errors = list(load_errors) + list(proc_errors)
    if all_errors:
        raise BatchProcessingError(all_errors)

    sequence_data_elements = [build_sequence_data(record, features) for record, features in ok_records]
    root = build_sequence_listing(sequence_data_elements, **kwargs)
    ET.indent(root)
    body = escape_apostrophes(ET.tostring(root, encoding="unicode"))

    with open(path, "w", encoding="utf-8") as f:
        f.write(XML_DECLARATION + "\n")
        f.write(DOCTYPE_LINE + "\n")
        f.write(body)
        f.write("\n")

    return len(ok_records)


if __name__ == "__main__":
    import sys

    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "序列信息-5.xlsx"
    annex_path = sys.argv[2] if len(sys.argv) > 2 else None  # 缺省用内嵌数据
    out_path = sys.argv[3] if len(sys.argv) > 3 else "sequence_listing.xml"

    try:
        n = write_sequence_listing_file(
            out_path, xlsx_path, annex_path, file_name=out_path,
        )
    except BatchProcessingError as e:
        print(f"批处理失败，{len(e.row_errors)} 行出错，未生成文件：")
        for err in e.row_errors:
            print(" -", err)
        sys.exit(1)

    print(f"已生成 {out_path}，包含 {n} 条 SequenceData")

    # 良构性自检：整份文件重新解析一遍
    with open(out_path, encoding="utf-8") as f:
        content = f.read()
    body_only = content.split("\n", 2)[2]  # 跳过 XML声明 + DOCTYPE 两行，ET不认识DOCTYPE
    ET.fromstring(body_only)
    print("良构性自检通过")
