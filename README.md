# ST.26 Sequence Listing Generator

把修饰核苷酸/氨基酸序列文件（Word 记法文档或 Excel 表格）自动转换成符合
[WIPO ST.26](https://www.wipo.int/standards/en/pdf/03-26-01.pdf) 标准的
专利序列表 XML，替代手工在 Excel 里逐条转写、再手动拼 XML 的流程。

带一个 Tkinter 桌面 GUI，也可以直接跑脚本或用 PyInstaller 打包成单文件
exe。

## 功能

- **自动识别输入格式**：Excel 支持"一行一条序列"和"合并单元格分块"两种
  排布；Word 文档会自动判断是核苷酸记法还是氨基酸记法，不需要手动选择。
- **两条独立的修饰序列流水线**：
  - **核苷酸**：紧凑记法（如 `UmsGmsAms...`，`m`/`f` 等残基修饰符号 +
    `s` 磷硫代酯键 + `VP` 端基前缀 + `[接头名]`）解析成
    `modified_base` / `misc_feature` 特征。
  - **氨基酸**：连字符记法（如 `Tyr-Aib-Glu-...-Lys(AEEA-AEEA-γGlu-Eic)-...-NH2`）
    解析成 `MOD_RES` 特征，支持圆括号接头/偶联支链、希腊字母转写、
    末端后缀（如 C 端酰胺化）。
- **符号定义完全可配置**：残基修饰符号、结构性符号（磷硫代酯键/端基
  前缀/接头模板，或氨基酸的末端后缀/希腊字母/接头片段名单）都能在
  GUI 里增删改，不需要改代码，配置持久化成本地 JSON 文件。
- **内嵌 Annex I 参照数据**：WIPO ST.26 Annex I 的核苷酸符号表、修饰
  核苷酸缩写表、氨基酸符号表、修饰氨基酸缩写表都写死在
  `annex_i_data.py` 里，不需要每次单独上传参照表。
- **校验优先、拒绝静默猜测**：位置语法、修饰名称映射、位置一致性等
  校验贯穿整条流水线，任何无法识别或有歧义的数据一律报错并汇总成
  Excel 校验报告，不会替你悄悄猜测或跳过。

## 依赖

```bash
pip install openpyxl python-docx
```

（`tkinter` 和 `xml.etree.ElementTree` 是 Python 标准库自带的。）

## 使用方法

直接运行 GUI：

```bash
python gui_app.py
```

或者用 PyInstaller 打包成单文件 Windows exe：

```bash
pyinstaller --onefile --windowed --name "ST26序列表生成工具" gui_app.py
```

也支持命令行自测模式（不打开 GUI，直接跑一遍指定文件）：

```bash
python gui_app.py --selftest 你的序列文件.xlsx
```

## 文件结构

| 文件 | 作用 |
|---|---|
| `gui_app.py` | GUI 主程序，两条流水线的统一入口 |
| `annex_i_data.py` | 内嵌 Annex I 表1-4 参照数据 |
| `symbol_legend.py` / `aa_symbol_legend.py` | 核苷酸/氨基酸符号定义的持久化配置 |
| `module0_compact_notation.py` | 核苷酸紧凑记法解析 |
| `module1_input_cleaning.py` ~ `module4_position_consistency.py` | 核苷酸输入清洗、location 解析、修饰名称校验、位置一致性校验 |
| `module5_xml_generation.py` / `module6_batch_driver.py` | 核苷酸 XML 生成、批量驱动 |
| `module7_validation_report.py` | 校验报告导出 |
| `adapter_merged_block_reader.py` | Excel 合并单元格分块格式适配器 |
| `module0b_aa_notation.py` | 氨基酸记法解析 |
| `module5b_aa_xml_generation.py` / `module6b_aa_batch_driver.py` | 氨基酸 XML 生成、批量驱动 |

## License

MIT，见 [LICENSE](LICENSE)。
