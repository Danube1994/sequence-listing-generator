"""
模块5b：氨基酸 XML 生成模块

输入：模块0b 的 DecodedAASequence（裸序列 + 逐残基的 MOD_RES /note
列表）。输出：一条 <SequenceData sequenceIDNumber="..."> 元素，内含
合规的 <INSDSeq>（source feature 自动生成 + 所有 MOD_RES feature +
序列本体）。

跟模块5（核苷酸版）的关键区别，都是从 SRP260114 真实材料 + 标准原文
反推确认过的：

- source feature 的 mol_type 固定 "protein"（标准第83、84(a)段的氨基
  酸版规则），organism 沿用同一个 "synthetic construct"。两个限定词
  的出现顺序是 mol_type 在前、organism 在后——核苷酸版是反过来的，
  两边都是照抄各自真实材料里的实际顺序，没有统一成同一种顺序。
- MOD_RES 的强制限定词只有一个 "note"（标准第30段、7.18节），没有
  核苷酸 modified_base 那种"/mod_base + 可选/note"两个限定词的组合，
  所以不需要模块5那套按 clause_id 合并多个限定词进一个 feature 的
  逻辑——DecodedAAResidue.notes 列表里的每一条 note，各自独立生成
  一个 INSDFeature，互不合并，即使同一位置有多条（比如末端残基自身
  带修饰、又叠加了末端酰胺化说明）也是两个独立的 MOD_RES。
- INSDSeq_moltype 固定 "AA"。
"""

import xml.etree.ElementTree as ET

from module5_xml_generation import ORGANISM_VALUE, DIVISION_VALUE

MOD_RES_KEY = "MOD_RES"
AA_MOL_TYPE = "protein"
AA_INSDSEQ_MOLTYPE = "AA"


def _add_qualifier(quals_elem, name, value):
    q = ET.SubElement(quals_elem, "INSDQualifier")
    ET.SubElement(q, "INSDQualifier_name").text = name
    ET.SubElement(q, "INSDQualifier_value").text = value


def build_aa_source_feature(length):
    feature = ET.Element("INSDFeature")
    ET.SubElement(feature, "INSDFeature_key").text = "source"
    ET.SubElement(feature, "INSDFeature_location").text = f"1..{length}"
    quals = ET.SubElement(feature, "INSDFeature_quals")
    _add_qualifier(quals, "mol_type", AA_MOL_TYPE)
    _add_qualifier(quals, "organism", ORGANISM_VALUE)
    return feature


def build_aa_mod_res_feature(position, note):
    feature = ET.Element("INSDFeature")
    ET.SubElement(feature, "INSDFeature_key").text = MOD_RES_KEY
    ET.SubElement(feature, "INSDFeature_location").text = str(position)
    quals = ET.SubElement(feature, "INSDFeature_quals")
    _add_qualifier(quals, "note", note)
    return feature


def build_aa_insdseq(decoded):
    """decoded: module0b_aa_notation.DecodedAASequence"""
    bare_sequence = decoded.bare_sequence

    insdseq = ET.Element("INSDSeq")
    ET.SubElement(insdseq, "INSDSeq_length").text = str(len(bare_sequence))
    ET.SubElement(insdseq, "INSDSeq_moltype").text = AA_INSDSEQ_MOLTYPE
    ET.SubElement(insdseq, "INSDSeq_division").text = DIVISION_VALUE

    feature_table = ET.SubElement(insdseq, "INSDSeq_feature-table")
    feature_table.append(build_aa_source_feature(len(bare_sequence)))
    for residue in decoded.residues:
        for note in residue.notes:
            feature_table.append(build_aa_mod_res_feature(residue.position, note))

    ET.SubElement(insdseq, "INSDSeq_sequence").text = bare_sequence
    return insdseq


def build_aa_sequence_data(decoded, seq_id_number=None):
    """seq_id_number 缺省时直接用 decoded.row_name 作为 sequenceIDNumber。"""
    sid = seq_id_number if seq_id_number is not None else decoded.row_name
    seqdata = ET.Element("SequenceData", sequenceIDNumber=str(sid))
    seqdata.append(build_aa_insdseq(decoded))
    return seqdata


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from module0b_aa_notation import records_from_aa_docx
    from module5_xml_generation import escape_apostrophes

    src = sys.argv[1] if len(sys.argv) > 1 else "SRP260114-序列信息.docx"

    decoded_list, errors = records_from_aa_docx(src)
    print(f"共 {len(decoded_list) + len(errors)} 行，成功 {len(decoded_list)} 行，出错 {len(errors)} 行")
    for e in errors:
        print(" -", e)

    if decoded_list:
        seqdata = build_aa_sequence_data(decoded_list[0])
        ET.indent(seqdata)
        raw = escape_apostrophes(ET.tostring(seqdata, encoding="unicode"))
        ET.fromstring(raw)  # 良构性自检
        print()
        print("=== 示例：第一条 SequenceData ===")
        print(raw)
