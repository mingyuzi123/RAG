# 6B PDF 读序与表格验证

2026-11-09。对照两份公开文本 PDF 的原页、抽取结果、实际上下文和回答。固定 E5、候选 Top 10、上下文 3 和 DeepSeek 回答提示词。SP 1300 沿用 5C 开发题，SP 1301 在运行前冻结 6 道可回答题与 2 道无答案题。两个文档来自同一机构和指南系列，属于换文档验证，覆盖的版面类型有限。[SP 1300](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1300.pdf) · [SP 1301](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1301.pdf) · [冻结题](STAGE6B_PDF_CASES.json)

## 抽取和索引

- `layout` 继续用 pypdf 的定宽布局文本。SP 1300 第 4、7 页左右栏按行交错，SP 1301 第 5 页表头保留了词，丢失了列组对应关系。[pypdf 文本抽取文档](https://pypdf.readthedocs.io/en/6.21.4/user/extract-text.html)
- `ordered` 用 pypdf 的普通文本抽取。检查 SP 1300 第 4、7 页时，左右栏正文顺序分开了。此模式的抽取文本空行更少，切块也随之变化，因此结果反映这一抽取模式的整体效果。
- `ordered_tables` 保留普通文本，并从有明确表头的有框表格补充带列名的证据。SP 1300 第 4 页六列表头成为单块，SP 1301 第 6 页通过单元格坐标把跨列标题映射到子列，保留示例行、字段与值的关系。空文本标成 `[empty]`，仍需对照原页判断是空白、合并单元格还是漏抽。边框装饰、无框表、扫描表和复杂合并行仍可能漏识别或误识别。[pdfplumber 0.11.8 文档](https://github.com/jsvine/pdfplumber/tree/v0.11.8)

两份 PDF 的原文接口都返回与原文件一致的字节。所有选中块的引用 URL 带真实页码，引用编号也与实际块 ID 对应。原 PDF 与抽取模式分别版本化，`pdf_extraction` 变化会为含 PDF 的场景生成新索引路径。

## 完整回答验收

每个模式单次运行，人工复核所有预期要点是否答全、实际引用是否提供证据。拒答题按是否避免猜测评分，部分拒答仍引用标题等上下文，不能据此证明全篇无答案。

| 文档 | 模式 | 块数 | 可回答题答全 | 无答案题拒答 | 总 tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| SP 1300 开发 | layout，5C 基线 | 48 | 3/6 | 2/2 | 4908 |
| SP 1300 开发 | ordered | 17 | 2/6 | 2/2 | 7092 |
| SP 1300 开发 | ordered_tables | 19 | 3/6 | 2/2 | 8209 |
| SP 1301 新题 | layout | 32 | 0/6 | 2/2 | 5768 |
| SP 1301 新题 | ordered_tables | 20 | 3/6 | 2/2 | 6526 |

旧文档中，普通文本抽取让 N01 的六职能列表掉出上下文。加入表格后，N02 资产清单四个列名从缺答变为第 4 页引用支持，N01 仍失败。N04 的备份检查、N05 的响应计划仍未答全。对应基线为 N01、N03、N06 通过，表格版为 N02、N03、N06 通过。[旧基线](STAGE5C_PDF_RESULTS.json) · [读序对照](STAGE6B_DEV_ORDERED.json) · [读序加表格](STAGE6B_DEV_TABLES.json)

| SP 1301 题号 | 原布局 | 读序加表格 |
| --- | --- | --- |
| L01 画像列组 | Practices 和 Priority 归错组 | 第 6 页引用正确区分两组 |
| L02 示例行评分与优先级 | 未取到示例行 | 第 6 页同一行支持 3/5 和 High |
| L03 示例政策版本与日期 | 未取到示例行 | 第 6 页 Practices 列支持 1.4 与 10/14/22 |
| L04 范围、L05 工具、L06 监控 | 缺正文证据 | 仍缺正文证据 |
| L07 普遍评分要求、L08 人员姓名 | 拒答 | 拒答 |

新文档的三道表格题均修复，其余三个正文问题仍缺证据。这轮新文档只比较完整方案和基线。旧文档的三组对照支持表格补充对 N02 的作用，尚无法把新文档的全部变化单独归因于表格模块。保留 `layout` 为默认，`ordered_tables` 用于有框表格的可选验证。后续可检查正文块的候选排序与截断。[新题基线](STAGE6B_HELDOUT_LAYOUT.json) · [新题表格版](STAGE6B_HELDOUT_TABLES.json)

## 复现与场景配置

使用 5C 报告的环境和本地 `.env`，加装可选布局依赖。把两个原始 PDF 保存到 `logs/`，以新输出路径执行。每次回答跑 8 题并使用 API 额度，原始请求及实际上下文在结果中的 `trace_log`。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-pdf-layout.txt
.\.venv\Scripts\python.exe scripts/evaluate_stage5_pdf.py logs/NIST.SP.1300.pdf --extraction ordered --output logs/sp1300-ordered.json
.\.venv\Scripts\python.exe scripts/evaluate_stage5_pdf.py logs/NIST.SP.1300.pdf --extraction ordered_tables --output logs/sp1300-tables.json
.\.venv\Scripts\python.exe scripts/evaluate_stage5_pdf.py logs/NIST.SP.1301.pdf --cases reports/STAGE6B_PDF_CASES.json --output logs/sp1301-layout.json
.\.venv\Scripts\python.exe scripts/evaluate_stage5_pdf.py logs/NIST.SP.1301.pdf --cases reports/STAGE6B_PDF_CASES.json --extraction ordered_tables --output logs/sp1301-tables.json
```

独立场景可在 manifest 设 `"pdf_extraction": "ordered_tables"`，再对该场景建关键词与向量索引。已在运行的页面需要重启来读取更新的 manifest。复习 L02 时，跟着引用打开第 6 页，沿 `PR.PS-01 → Current / Rating` 和 `PR.PS-01 → Target / Priority` 查原值，区分「表格里有这些词」与「表格里这些词属于同一行和正确列」。
