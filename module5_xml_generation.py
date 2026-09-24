"""
模块5：XML 生成模块

输入：模块1的 SequenceRecord（length / moltype / sequence）+
      模块4校验通过的 List[ParsedFeature]。
输出：一条 <SequenceData sequenceIDNumber="..."> 元素，内含合规的
      <INSDSeq>（source feature 自动生成 + 所有修饰 feature + 序列本体）。

source feature 的两个 mandatory qualifier 按标准第83、84(a)段固定：
    organism  = "synthetic construct"        （非天然、人工合成序列）
    mol_type  = "other RNA" / "other DNA"    （随 moltype 变化）
INSDSeq_division 固定为 "PAT"（标准正文：与专利申请相关的序列必填此值）。

location 字符串直接复用 ParsedFeature.location.raw——这个项目的语法
已经定型为只有单点 x 和相邻位间 x^(x+1) 两种原子形式，不含 <、> 符号，
所以不需要处理标准第71段提到的 &lt;/&gt; 实体转义。

确认过不在本模块处理的范围：
    - <ST26SequenceListing> 根元素一级的属性（dtdVersion、申请人信息、
      产出日期等）：用户会把本模块导出的 XML 导回 WIPO Sequence 软件
      里去补这部分，不需要脚本生成，模块5只产出 <SequenceData> 这一级。
    - Name -> SEQ ID NO 的映射：已确认直接用 Name 本身即可，不需要
      重新编号。

多条 <SequenceData> 如何打包进一个可导入 WIPO Sequence 的文件（是否
需要外层包一层容器元素以保证多序列合在一起时仍是良构 XML）是模块6
批量驱动要解决的问题，不在模块5范围内——模块5只保证单条 SequenceData
本身合规、良构。
"""

import xml.etree.ElementTree as ET

ORGANISM_VALUE = "synthetic construct"
MOL_TYPE_BY_MOLTYPE = {"RNA": "other RNA", "DNA": "other DNA"}
DIVISION_VALUE = "PAT"


def _add_qualifier(quals_elem, name, value):
    q = ET.SubElement(quals_elem, "INSDQualifier")
    ET.SubElement(q, "INSDQualifier_name").text = name
    ET.SubElement(q, "INSDQualifier_value").text = value


def build_source_feature(length, moltype):
    if moltype not in MOL_TYPE_BY_MOLTYPE:
        raise ValueError(f"未知 moltype: {moltype!r}，只接受 'RNA' 或 'DNA'")

    feature = ET.Element("INSDFeature")
    ET.SubElement(feature, "INSDFeature_key").text = "source"
    ET.SubElement(feature, "INSDFeature_location").text = f"1..{length}"
    quals = ET.SubElement(feature, "INSDFeature_quals")
    _add_qualifier(quals, "organism", ORGANISM_VALUE)
    _add_qualifier(quals, "mol_type", MOL_TYPE_BY_MOLTYPE[moltype])
    return feature


def build_feature(parsed_feature):
    """单条 ParsedFeature -> 单个只带一个 qualifier 的 INSDFeature。"""
    return build_feature_group(
        parsed_feature.key, parsed_feature.location,
        [(parsed_feature.qualifier_name, parsed_feature.qualifier_value)],
    )


def build_feature_group(key, location, qualifiers):
    feature = ET.Element("INSDFeature")
    ET.SubElement(feature, "INSDFeature_key").text = key
    ET.SubElement(feature, "INSDFeature_location").text = location.raw
    quals = ET.SubElement(feature, "INSDFeature_quals")
    for qname, qvalue in qualifiers:
        _add_qualifier(quals, qname, qvalue)
    return feature


def _group_modified_base_features(features):
    """
    把同一条 clause 里的 modified_base qualifier（mod_base + 可选的 note）
    合并成一组，对应标准第17段 Example 2 的写法：一个 INSDFeature 里放两个
    INSDQualifier（mod_base、note），不能拆成两条独立 feature。

    按 clause_id 分组，不按 location 分组——同一个位置完全可以合法地
    出现多条互相独立、各自完整的 modified_base（比如1号残基同时有端基
    VP修饰和2'-OMe糖环修饰，两条各自都自带 mod_base，是两个独立的
    INSDFeature，不能因为位置相同就被硬并成一个 feature 塞两个
    mod_base——这正是模块3同名分组逻辑要避免的错误，模块5这里要用
    同一套分组依据，否则模块3放行的两条独立 feature 会在这一步被
    错误地重新合并回一起）。

    misc_feature 等其它 key 不做这个合并：同一位置堆叠多条互相独立的
    misc_feature 本身就是分开的 ParsedFeature，各自成一个 feature，
    不需要额外分组。

    返回 List[(key, location, [(qual_name, qual_value), ...])]，
    按原始出现顺序排列（同一组的后续条目在原位置追加 qualifier，
    不会把分组挪到列表末尾）。
    """
    groups = []
    index_by_key = {}
    for f in features:
        if f.key == "modified_base":
            gkey = ("modified_base", f.clause_id)
            if gkey not in index_by_key:
                index_by_key[gkey] = len(groups)
                groups.append((f.key, f.location, []))
            groups[index_by_key[gkey]][2].append((f.qualifier_name, f.qualifier_value))
        else:
            groups.append((f.key, f.location, [(f.qualifier_name, f.qualifier_value)]))
    return groups


def build_insdseq(record, features):
    insdseq = ET.Element("INSDSeq")
    ET.SubElement(insdseq, "INSDSeq_length").text = str(record.length)
    ET.SubElement(insdseq, "INSDSeq_moltype").text = record.moltype
    ET.SubElement(insdseq, "INSDSeq_division").text = DIVISION_VALUE

    feature_table = ET.SubElement(insdseq, "INSDSeq_feature-table")
    feature_table.append(build_source_feature(record.length, record.moltype))
    for key, location, qualifiers in _group_modified_base_features(features):
        feature_table.append(build_feature_group(key, location, qualifiers))

    ET.SubElement(insdseq, "INSDSeq_sequence").text = record.sequence
    return insdseq


def escape_apostrophes(xml_text):
    """
    ST.26 标准第41段要求：属性值/元素内容里的 ' 必须替换成预定义实体
    &apos;（连同 < > & " 一起，是标准明文允许使用的仅有5个实体）。
    ElementTree 的默认序列化只处理 & < > 以及属性值里的 "，唯独不处理
    '，所以这里需要在 ET.tostring() 之后再补一步。

    在已经序列化完的字符串上做全局替换是安全的：这份文件里所有属性
    都用双引号包裹、没有用到注释或 CDATA 段，' 不可能是 markup 本身
    的一部分，只会出现在文本内容或属性值里；同时 & < > " 在这一步
    之前已经被 ElementTree 正确转义过，不会因为这次替换又产生新的
    需要转义的字符。
    """
    return xml_text.replace("'", "&apos;")


def build_sequence_data(record, features, seq_id_number=None):
    """seq_id_number 缺省时直接用 record.name 作为 sequenceIDNumber（已确认二者一致）。"""
    sid = seq_id_number if seq_id_number is not None else record.name
    seqdata = ET.Element("SequenceData", sequenceIDNumber=str(sid))
    seqdata.append(build_insdseq(record, features))
    return seqdata


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from module1_input_cleaning import load_sequence_table
    from module2_location_parser import parse_modification_text, LocationParseError
    from module3_mod_base_review import (
        review_row_features, ModifiedBaseError, load_table2_controlled_values,
    )
    from module4_position_consistency import validate_row, PositionConsistencyError

    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "序列信息-5.xlsx"
    annex_path = sys.argv[2] if len(sys.argv) > 2 else None  # 缺省用内嵌数据

    from annex_i_data import MODIFIED_NUCLEOTIDE_VALUES
    table2_values = (
        load_table2_controlled_values(annex_path) if annex_path else MODIFIED_NUCLEOTIDE_VALUES
    )
    records, load_errors = load_sequence_table(xlsx_path)

    elements = []
    errors = []
    for r in records:
        try:
            features = parse_modification_text(r.modification_text, r.name)
            reviewed, _notes = review_row_features(features, r.name, table2_values)
            validate_row(reviewed, r.name, r.length)
        except (LocationParseError, ModifiedBaseError, PositionConsistencyError) as e:
            errors.append(e)
            continue

        seqdata = build_sequence_data(r, reviewed)
        elements.append(seqdata)

        # 良构性自检：转义 + 序列化后再解析回来，确保是合法 XML
        raw = escape_apostrophes(ET.tostring(seqdata, encoding="unicode"))
        ET.fromstring(raw)

    print(f"共处理 {len(records)} 行，生成 {len(elements)} 条 SequenceData，出错 {len(errors)} 行")
    if errors:
        print("=== 错误 ===")
        for e in errors:
            print(" -", e)

    if elements:
        print()
        print("=== 示例：第一条 SequenceData ===")
        ET.indent(elements[0])
        print(escape_apostrophes(ET.tostring(elements[0], encoding="unicode")))
