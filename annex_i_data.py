"""
内嵌的 Annex I 参照数据（来源：用户提供的 Annex I.xlsx，与
STANDARD ST.26.pdf 正文 Annex I Section 1 / Section 2 逐字核对过，
内容一致）。

嵌进代码里是为了让打包出来的 exe 不用每次都单独上传 Annex I 参照表——
这两张表是 ST.26 标准本身固定的受控词表，不是随每次任务变化的项目数据，
适合直接写死在脚本里。

嵌了流水线里实际用到的四张表：
    NUCLEOTIDE_SYMBOLS         Table 1，模块1校验 Sequence 字符集用
    MODIFIED_NUCLEOTIDE_VALUES Table 2，模块3校验 modified_base 的
                                mod_base 取值用
    AMINO_ACID_SYMBOLS         Table 3，氨基酸模块校验裸序列字符集、
                                做三字母代码<->单字母符号互译用
    MODIFIED_AMINO_ACID_VALUES Table 4，氨基酸模块的"已知变体清单"，
                                同 MODIFIED_NUCLEOTIDE_VALUES 一样只
                                留痕不拦截

AMINO_ACID_SYMBOLS 的三字母代码列 Annex I.xlsx 本身没有（xlsx 只有
Symbol/Definition 两列），取自同一份 STANDARD ST.26.pdf 附录里的
"Table B – Conventional Amino Acid Symbols, Three letter Codes, and
Definitions"，与 Annex I 正文 Section 3 的 Symbol/Definition 两列内容
逐字核对一致，只是多了一列三字母代码。
"""

# Annex I, Section 1, Table 1: List of nucleotide symbols（全部小写）
NUCLEOTIDE_SYMBOLS = frozenset("acgtmrwsykvhdbn")

# Annex I, Section 2, Table 2: List of modified nucleotides
# 47个真实缩写 + 字面值 "OTHER"（Table 2 里明文列出的合法值，requires note qualifier）
MODIFIED_NUCLEOTIDE_VALUES = frozenset({
    "ac4c", "chm5u", "cm", "cmnm5s2u", "cmnm5u", "dhu", "fm", "gal q", "gm",
    "i", "i6a", "m1a", "m1f", "m1g", "m1i", "m22g", "m2a", "m2g", "m3c",
    "m4c", "m5c", "m6a", "m7g", "mam5u", "mam5s2u", "man q", "mcm5s2u",
    "mcm5u", "mo5u", "ms2i6a", "ms2t6a", "mt6a", "mv", "o5u", "osyw", "p",
    "q", "s2c", "s2t", "s2u", "s4u", "m5u", "t6a", "tm", "um", "yw", "x",
    "OTHER",
})

assert len(NUCLEOTIDE_SYMBOLS) == 15
assert len(MODIFIED_NUCLEOTIDE_VALUES) == 48

# Annex I, Section 3, Table 3: List of amino acid symbols
# dict: 单字母符号 -> (三字母代码, 英文全称/定义)
AMINO_ACID_SYMBOLS = {
    "A": ("Ala", "Alanine"),
    "R": ("Arg", "Arginine"),
    "N": ("Asn", "Asparagine"),
    "D": ("Asp", "Aspartic acid (Aspartate)"),
    "C": ("Cys", "Cysteine"),
    "Q": ("Gln", "Glutamine"),
    "E": ("Glu", "Glutamic acid (Glutamate)"),
    "G": ("Gly", "Glycine"),
    "H": ("His", "Histidine"),
    "I": ("Ile", "Isoleucine"),
    "L": ("Leu", "Leucine"),
    "K": ("Lys", "Lysine"),
    "M": ("Met", "Methionine"),
    "F": ("Phe", "Phenylalanine"),
    "P": ("Pro", "Proline"),
    "O": ("Pyl", "Pyrrolysine"),
    "S": ("Ser", "Serine"),
    "U": ("Sec", "Selenocysteine"),
    "T": ("Thr", "Threonine"),
    "W": ("Trp", "Tryptophan"),
    "Y": ("Tyr", "Tyrosine"),
    "V": ("Val", "Valine"),
    "B": ("Asx", "Aspartic acid or Asparagine"),
    "Z": ("Glx", "Glutamine or Glutamic acid"),
    "J": ("Xle", "Leucine or Isoleucine"),
    "X": (
        "Xaa",
        'A or R or N or D or C or Q or E or G or H or I or L or K or M or F '
        'or P or O or S or U or T or W or Y or V; "unknown" or "other"',
    ),
}

# Annex I, Section 4, Table 4: List of modified amino acids
# dict: 缩写 -> 英文全称。只作为"已知变体清单"记录用，不阻塞流程
# （跟 MODIFIED_NUCLEOTIDE_VALUES 的定位一样，见 module3 的业务规则）。
MODIFIED_AMINO_ACID_VALUES = {
    "Aad": "2-Aminoadipic acid",
    "bAad": "3-Aminoadipic acid",
    "bAla": "beta-Alanine, beta-Aminoproprionic acid",
    "Abu": "2-Aminobutyric acid",
    "4Abu": "4-Aminobutyric acid, piperidinic acid",
    "Acp": "6-Aminocaproic acid",
    "Ahe": "2-Aminoheptanoic acid",
    "Aib": "2-Aminoisobutyric acid",
    "bAib": "3-Aminoisobutyric acid",
    "Apm": "2-Aminopimelic acid",
    "Dbu": "2,4-Diaminobutyric acid",
    "Des": "Desmosine",
    "Dpm": "2,2’-Diaminopimelic acid",
    "Dpr": "2,3-Diaminoproprionic acid",
    "EtGly": "N-Ethylglycine",
    "EtAsn": "N-Ethylasparagine",
    "Hyl": "Hydroxylysine",
    "aHyl": "allo-Hydroxylysine",
    "3Hyp": "3-Hydroxyproline",
    "4Hyp": "4-Hydroxyproline",
    "Ide": "Isodesmosine",
    "aIle": "allo-Isoleucine",
    "MeGly": "N-Methylglycine, sarcosine",
    "MeIle": "N-Methylisoleucine",
    "MeLys": "6-N-Methyllysine",
    "MeVal": "N-Methylvaline",
    "Nva": "Norvaline",
    "Nle": "Norleucine",
    "Orn": "Ornithine",
}

assert len(AMINO_ACID_SYMBOLS) == 26
assert len(MODIFIED_AMINO_ACID_VALUES) == 29
