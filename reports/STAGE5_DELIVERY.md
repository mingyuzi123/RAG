# 第 5 阶段交付与验收

2026-11-09 完成 5B 独立运行和 5C 新资料验收。运行记录分别保存在 [5B 干净环境结果](STAGE5B_CLEAN_RUN.json) 和 [5C PDF 逐题结果](STAGE5C_PDF_RESULTS.json)。

## 5B 从干净目录运行

用独立代码目录、Python 3.13.9 新虚拟环境和重新下载的 CrewAI 固定提交执行。安装 `pypdf==6.21.4`，使用标准库 SQLite FTS5，不安装 E5 依赖。首次检索故意发生缺索引错误，定位到 `retrieval`。建立 267 块索引后，同一查询返回 3 个候选。

在新环境启动页面，导入一份只含验收规则的 Markdown，原文接口返回的字节与上传一致。用 BM25 检索，配置本机密钥后真实回答“最多重试 4 次”并引用该原文。回答的场景版本、证据块和请求 ID 均保存在结果中，本次回答用了 248 tokens。

| 触发条件 | 日志环节 | 恢复方式 |
| --- | --- | --- |
| 跳过索引构建 | `retrieval` | 执行 `python -m raglab index`，用同一查询重试 |
| 上下文数大于候选数 | `input` | 调整为 `1 ≤ context_k ≤ top_k` |
| 混合检索缺英文词，自动改写关闭 | `rewrite` | 填写英文词，或切换 E5 并建向量索引 |
| 没有密钥却请求回答 | `generation` | 在本机配置密钥并重启，或先运行免费检索 |

失败响应给出请求 ID，CLI 在错误消息末尾显示 ID。页面请求记录和 `logs/requests.jsonl` 使用 `failure_stage` 区分环节。生成阶段若已经保存完整证据记录，沿用该请求 ID。无密钥的故障验证在生成前发生，带引用回答使用了真实模型调用。

在新的仓库目录运行以下 PowerShell 命令即可复现 5B 的免费部分。`doctor` 的资料、索引、依赖、密钥字段可分别核对。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-pdf.txt
.\.venv\Scripts\python.exe scripts/fetch_scenario_docs.py --scenario scenarios/crewai/manifest.json
.\.venv\Scripts\python.exe -m raglab doctor
.\.venv\Scripts\python.exe -m raglab search 'hierarchical process manager agent' --strategy bm25
.\.venv\Scripts\python.exe -m raglab index
.\.venv\Scripts\python.exe -m raglab search 'hierarchical process manager agent' --strategy bm25 --top-k 3
.\.venv\Scripts\python.exe -m raglab.web --port 8769
```

用页面打开本地场景、导入 Markdown，再选 BM25 并填写英文词可验证资料和引用位置。生成回答时在本机 `.env` 填密钥，使用 `scripts/run_with_deepseek.py --port 8769` 启动。E5 使用 `requirements-vector.txt`，固定文档另运行 `python -m raglab vector-index`。

## 5C 冻结新题与真实 PDF

使用 9 页 [NIST SP 1300 原始 PDF](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1300.pdf)，冻结 PDF SHA256、8 道中文题、预期要点和页码后运行。检查了第 4、5 页原版面，双栏和表格在抽取文本中会交错。独立本地知识库导入得到 48 块，原文接口返回字节与官方文件一致，所有被引用的 PDF 来源链接均保留页码。[冻结题集](STAGE5C_PDF_CASES.json)

E5 使用中文原题，候选 10、上下文 3。按实际摘录和页码复核，**可回答题 3/6 全部要点有依据，无答案题 2/2 正确拒答**。8 次请求共 4908 tokens，含输入 3016、输出 1892，问答耗时中位数 2.84 秒。耗时在导入和建库完成后测量。

| 题号 | 主题 | 结果与证据 |
| --- | --- | --- |
| N01 | 六个职能 | 完整，第 2 页 |
| N02 | 资产表格的列 | 缺答。第 4 页标题和残段进入候选，关键表头未召回 |
| N03 | MFA 启用顺序 | 完整，第 5 页 |
| N04 | 备份与恢复检查 | 缺答。第 5、8 页有候选，两个关键段落都未召回 |
| N05 | 响应计划负责人和联系人字段 | 缺答。第 7 页相关片段入选，实际定义段未召回 |
| N06 | 当前与目标画像 | 完整，第 9 页 |
| N07 | 固定备份小时间隔 | 正确说明无法确定。引用的标题无法证明全文没有规定 |
| N08 | 模板的州警察号码 | 正确拒答。第 7 页原表为空，所引标题本身只支持当前摘录不足 |

三道缺答题都体现了页码命中与证据命中的差别。部分候选只有标题或版面残段，需要优先改善双栏与表格抽取，再用另外的冻结新题验证。此结果限定在这份文本 PDF、这组参数和单次生成。

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
Invoke-WebRequest 'https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1300.pdf' -OutFile logs/NIST.SP.1300.pdf
.\.venv\Scripts\python.exe -m pip install -r requirements-pdf.txt -r requirements-vector.txt
.\.venv\Scripts\python.exe scripts/evaluate_stage5_pdf.py logs/NIST.SP.1300.pdf --output logs/stage5c-reproduction.json
```

脚本在 `logs/` 下创建独立知识库，验证 PDF 哈希并保存实际请求记录。复跑使用新的输出路径，需要本机 DeepSeek 密钥并消耗 8 次回答额度。首次使用 E5 时需下载固定模型。结果 JSON 记录每题 ID、引用页、证据块、耗时、tokens 和请求 ID。

## 演示与简历

1. 用 `doctor` 展示资料版本和索引状态，执行一次免费 BM25 检索。展示候选块到原文的连接。
2. 在空本地场景导入同一份 PDF，选 E5，运行 N03 并打开第 5 页引用。再运行 N07，核对拒答与引用边界。
3. 打开 N02 的候选和第 4 页表格，说明为什么找到页面标题仍答不出字段。展示冻结题集和逐题结果。

简历表述可用「实现可替换资料与检索策略的本地 RAG 骨架，统一 Web、API、CLI 场景配置，支持文本 PDF 页码引用与分阶段请求追踪。在独立环境复现建库及引用问答，完成真实 PDF 的 8 题冻结评测，定位双栏表格和跨页证据的召回缺口。」[验收记录](STAGE5C_PDF_RESULTS.json)
