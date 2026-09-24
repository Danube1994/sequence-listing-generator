"""
模块6b：氨基酸批量驱动模块

氨基酸这条流水线比核苷酸版简单：模块0b（紧凑记法解析）本身就是
"输入清洗 + 校验"一步到位——裸序列长度由解析出的残基数量决定，
position 是解析时按顺序赋的 1..N，不存在核苷酸那种"用户在 Excel 里
手填 location 字符串，需要单独校验跟裸序列长度是否一致"的问题，所以
不需要核苷酸模块1-4那一整条校验链的氨基酸版本，模块0b 解析成功即
代表校验通过。

根元素（<ST26SequenceListing> 那一级：dtdVersion、申请人信息占位、
productionDate 等）直接复用模块6的 build_sequence_listing——那部分
逻辑完全跟 moltype 无关，不重复实现。
"""

import xml.etree.ElementTree as ET

from module0b_aa_notation import records_from_aa_docx
from module5b_aa_xml_generation import build_aa_sequence_data
from module5_xml_generation import escape_apostrophes
from module6_batch_driver import build_sequence_listing, XML_DECLARATION, DOCTYPE_LINE


def build_aa_sequence_listing(decoded_list, file_name="sequence_listing.xml",
                               software_name="module6b_aa_batch_driver", software_version="0.1"):
    sequence_data_elements = [build_aa_sequence_data(d) for d in decoded_list]
    return build_sequence_listing(
        sequence_data_elements, file_name=file_name,
        software_name=software_name, software_version=software_version,
    )


def write_aa_sequence_listing_file(path, docx_path, config=None, **kwargs):
    """
    docx_path -> 写一份 XML 文件。返回 (成功条数, errors)。errors 非空
    时对应行没有被写进这份 XML（不是"全部出错就中止"，是"逐行各自
    成败，成功的照样打包"，行为跟模块0b 本身一致）。
    """
    decoded_list, errors = records_from_aa_docx(docx_path, config)

    root = build_aa_sequence_listing(decoded_list, **kwargs)
    ET.indent(root)
    body = escape_apostrophes(ET.tostring(root, encoding="unicode"))

    with open(path, "w", encoding="utf-8") as f:
        f.write(XML_DECLARATION + "\n")
        f.write(DOCTYPE_LINE + "\n")
        f.write(body)
        f.write("\n")

    return len(decoded_list), errors


if __name__ == "__main__":
    import sys

    docx_path = sys.argv[1] if len(sys.argv) > 1 else "SRP260114-序列信息.docx"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "sequence_listing_aa.xml"

    n, errors = write_aa_sequence_listing_file(out_path, docx_path, file_name=out_path)

    print(f"已生成 {out_path}，包含 {n} 条 SequenceData，{len(errors)} 行出错")
    for e in errors:
        print(" -", e)

    with open(out_path, encoding="utf-8") as f:
        content = f.read()
    body_only = content.split("\n", 2)[2]  # 跳过 XML声明 + DOCTYPE 两行，ET不认识DOCTYPE
    ET.fromstring(body_only)
    print("良构性自检通过")
