"""
模块4：位置一致性校验模块

输入：模块1产出的 SequenceRecord.length（清洗后的真实序列长度）+
      模块3复核之后的 List[ParsedFeature]（modified_base 已经按
      Annex I Table 2 处理完毕，key 只会是 misc_feature 或合规的
      modified_base）。

只做两件事，纯校验，不修改/不转换数据：
1. 越界检查：每个 location 的端点都必须落在 [1, length] 内
   （单点 x 本身，或 bond 的 bond_from/bond_to 两端）。
2. 完全重复检查：按 clause_id 把同一条原始 clause 的全部 qualifier
   聚合成一个"签名"（key + location + 全部 qualifier 键值对），两条
   不同 clause 的签名完全一样才算重复——不能只比较单个 qualifier，
   否则会把"同一位置两条独立的 modified_base"误判成重复（比如1号
   残基同时有端基VP修饰和2'-OMe糖环修饰，两条各自的 mod_base 都是
   "OTHER"，qualifier_name/value 单独看一样，但配套的 note 不同，
   是两条不同的 feature，不该被拦下来）。

另外顺带产出一份"位置覆盖度"报告（纯信息性，不是校验规则）：
哪些位置完全没有被任何单点 feature 提及。之前几轮讨论里约定过
"没被提到的位置 = 默认无特殊修饰"是隐含假设，这份报告只是让这个
假设在数据里变得可见、可审计，不代表这些位置有问题。
"""

from dataclasses import dataclass


class PositionConsistencyError(Exception):
    def __init__(self, row_name, message, context=""):
        self.row_name = row_name
        self.message = message
        self.context = context
        super().__init__(f"[Name={row_name!r}] {message} | {context!r}")


@dataclass
class PositionReport:
    row_name: str
    length: int
    covered_positions: set
    uncovered_positions: list


def validate_row(features, row_name, length):
    """
    校验通过返回 PositionReport；发现问题抛 PositionConsistencyError。
    """
    covered_positions = set()
    clauses = {}   # clause_id -> (key, location.raw, [(qname, qval), ...])
    clause_order = []

    for f in features:
        lo, hi = f.location.min_pos(), f.location.max_pos()
        if lo < 1 or hi > length:
            raise PositionConsistencyError(
                row_name,
                f"位置 {f.location.raw!r} 超出序列范围 [1, {length}]",
                f.raw_entry,
            )

        cid = f.clause_id
        if cid not in clauses:
            clauses[cid] = (f.key, f.location.raw, [])
            clause_order.append(cid)
        clauses[cid][2].append((f.qualifier_name, f.qualifier_value))

        if f.location.kind == "point":
            covered_positions.add(f.location.position)

    seen_signatures = set()
    for cid in clause_order:
        key, loc, quals = clauses[cid]
        signature = (key, loc, tuple(sorted(quals)))
        if signature in seen_signatures:
            raise PositionConsistencyError(
                row_name,
                f"出现完全重复的 feature：key={key!r}, location={loc!r}, qualifiers={quals!r}",
                "",
            )
        seen_signatures.add(signature)

    uncovered = sorted(set(range(1, length + 1)) - covered_positions)
    return PositionReport(
        row_name=row_name,
        length=length,
        covered_positions=covered_positions,
        uncovered_positions=uncovered,
    )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from module1_input_cleaning import load_sequence_table
    from module2_location_parser import parse_modification_text, LocationParseError
    from module3_mod_base_review import (
        review_row_features, ModifiedBaseError, load_table2_controlled_values,
    )

    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "序列信息-5.xlsx"
    annex_path = sys.argv[2] if len(sys.argv) > 2 else None  # 缺省用内嵌数据

    from annex_i_data import MODIFIED_NUCLEOTIDE_VALUES
    table2_values = (
        load_table2_controlled_values(annex_path) if annex_path else MODIFIED_NUCLEOTIDE_VALUES
    )
    records, load_errors = load_sequence_table(xlsx_path)

    errors = []
    for r in records:
        try:
            features = parse_modification_text(r.modification_text, r.name)
            reviewed, _notes = review_row_features(features, r.name, table2_values)
            report = validate_row(reviewed, r.name, r.length)
        except (LocationParseError, ModifiedBaseError, PositionConsistencyError) as e:
            errors.append(e)
            continue

        print(f"Name={r.name}\tlength={report.length}\t"
              f"覆盖位点数={len(report.covered_positions)}\t"
              f"未提及位点={report.uncovered_positions}")

    print()
    print(f"共处理 {len(records)} 行，出错 {len(errors)} 行")
    if errors:
        print("=== 错误 ===")
        for e in errors:
            print(" -", e)
