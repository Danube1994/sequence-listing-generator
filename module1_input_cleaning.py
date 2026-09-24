"""
模块1：Excel 输入清洗模块

读取"Name / Sequence / 修饰信息"三列的 Excel（如 序列信息-4.xlsx），
对 Sequence 做符合 WIPO ST.26 Annex I 的规范化：

- 去除首尾空白
- 全部转小写（ST.26 正文第13段：Only lower case letters must be used）
- U/u 一律转成 t（ST.26 正文第14段：符号 't' 在 DNA 中代表胸腺嘧啶，
  在 RNA 中代表尿嘧啶；Annex I Table 1 里没有 'u' 这个符号，
  RNA/DNA 的区分交给 INSDSeq_moltype，不体现在序列字符本身）
- 校验清洗后的字符全部落在 Annex I Section 1 Table 1 定义的符号集合内

moltype（RNA/DNA）通过清洗前的原始序列里是否出现 U/u 来判定：
出现 U（不出现 T）判为 RNA，出现 T（不出现 U）判为 DNA，
两者都出现或都不出现视为异常，报错交人工确认。
"""

from dataclasses import dataclass
import openpyxl

from annex_i_data import NUCLEOTIDE_SYMBOLS

# Annex I, Section 1, Table 1: List of nucleotide symbols（全部小写）
VALID_NUCLEOTIDE_SYMBOLS = NUCLEOTIDE_SYMBOLS


class InputCleaningError(Exception):
    def __init__(self, row_name, message):
        self.row_name = row_name
        self.message = message
        super().__init__(f"[Name={row_name!r}] {message}")


@dataclass
class SequenceRecord:
    name: str
    raw_sequence: str          # Excel 原始值，未做任何处理，用于报错回溯
    sequence: str              # 清洗后序列：strip + 小写 + U/u -> t
    moltype: str               # 'RNA' 或 'DNA'，据清洗前是否出现 U/u 判定
    modification_text: str     # 原始"修饰信息"列文本，原样传给模块2
    length: int


def _clean_sequence(raw, row_name) -> tuple[str, str]:
    if raw is None:
        raise InputCleaningError(row_name, "Sequence 为空")

    stripped = str(raw).strip()
    if not stripped:
        raise InputCleaningError(row_name, "Sequence 去除首尾空白后为空")

    lowered = stripped.lower()
    has_u = "u" in lowered
    has_t = "t" in lowered
    if has_u and has_t:
        raise InputCleaningError(
            row_name, f"序列中同时出现 T 和 U，无法判定分子类型（DNA/RNA）: {raw!r}"
        )
    moltype = "RNA" if has_u else "DNA"

    cleaned = lowered.replace("u", "t")

    invalid_chars = sorted(set(cleaned) - VALID_NUCLEOTIDE_SYMBOLS)
    if invalid_chars:
        raise InputCleaningError(
            row_name,
            f"序列包含 Annex I Table 1 未定义的字符 {invalid_chars}: {raw!r}",
        )

    return cleaned, moltype


def _normalize_name(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def load_sequence_table(path, sheet_name=None):
    """
    返回 (records, errors)：
    - records: List[SequenceRecord]，清洗成功的行
    - errors: List[InputCleaningError]，清洗失败的行（不中断整体流程，
      交由调用方决定是否继续 / 汇总报给用户）
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet_name] if sheet_name else wb[wb.sheetnames[0]]

    records = []
    errors = []
    seen_names = {}

    for row in ws.iter_rows(min_row=2):
        name_cell, seq_cell = row[0], row[1]
        mod_cell = row[2] if len(row) > 2 else None

        if name_cell.value is None and seq_cell.value is None:
            continue  # 空行跳过

        raw_name = name_cell.value
        row_name = _normalize_name(raw_name) if raw_name is not None else f"<行{name_cell.row}>"

        try:
            if raw_name is None:
                raise InputCleaningError(row_name, "Name 为空")
            cleaned_seq, moltype = _clean_sequence(seq_cell.value, row_name)
        except InputCleaningError as e:
            errors.append(e)
            continue

        if row_name in seen_names:
            errors.append(InputCleaningError(
                row_name,
                f"Name 重复，与第 {seen_names[row_name]} 行冲突",
            ))
            continue
        seen_names[row_name] = name_cell.row

        records.append(SequenceRecord(
            name=row_name,
            raw_sequence=seq_cell.value,
            sequence=cleaned_seq,
            moltype=moltype,
            modification_text=(mod_cell.value if mod_cell is not None else "") or "",
            length=len(cleaned_seq),
        ))

    return records, errors


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "序列信息-4.xlsx"
    records, errors = load_sequence_table(path)

    print(f"成功读取 {len(records)} 条，失败 {len(errors)} 条")
    print()
    for r in records:
        print(f"Name={r.name}\tmoltype={r.moltype}\tlength={r.length}\tsequence={r.sequence}")
    if errors:
        print()
        print("=== 错误 ===")
        for e in errors:
            print(" -", e)
