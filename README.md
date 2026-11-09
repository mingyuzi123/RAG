# 可复用技术文档 RAG

一个以技术文档问答为首个场景的 RAG 学习与工程项目。核心目标是让资料源、检索策略和呈现配置可替换，并通过固定问题集和请求追踪验证效果。

**第一次来这里？**从 [《从零上手并学会这个 RAG 项目》](docs/从零上手并学会这个RAG项目.md)开始：先跑免费检索，再沿真实代码和页面学习每个环节，最后完成四个可核对的练习。

## 快速演示

**Windows 直接双击根目录的 [start.cmd](start.cmd)**。需要 Python 3.11 或更新版本。脚本会复用或创建项目的 `.venv`，缺少 PDF 依赖时会安装。看到终端打印地址后打开 [演示页面](http://127.0.0.1:8789/)，保持窗口打开。结束时按 `Ctrl+C`，若 CMD 询问是否终止批处理，输入 `Y`。

| 在 PowerShell 中运行 | 用途 |
| --- | --- |
| `.\start.cmd` | 免费 PDF 演示，点击 L02 的「运行单路检索」 |
| `.\start.cmd --live` | 同一份演示 PDF，启用本机 `.env` 的 DeepSeek |
| `.\start.cmd --check` | 免费 HTTP 自检，结束后退出 |
| `.\start_lab.cmd` | 完整实验室，使用已有场景与本地知识库，端口 8765 |
| `.\start_lab.cmd --live` | 完整实验室，启用 DeepSeek |

完整实验室可以直接双击 [start_lab.cmd](start_lab.cmd)。从全新仓库启动时，先按[上手指南](docs/从零上手并学会这个RAG项目.md)下载官方资料并建立索引。PDF 演示自带独立建库流程，首次需要联网。Linux 或 macOS 可用对应虚拟环境的 Python 执行下面相同的脚本。手动启动的 Windows 命令为

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-pdf-layout.txt
.\.venv\Scripts\python.exe scripts/run_demo.py
```

打开 [演示页面](http://127.0.0.1:8789/)，点击**运行单路检索**。展开第一条的**查看完整证据块**，再点页码链接，核对第 6 页同一行的 Rating 和 Priority。首次运行会下载并核对固定版本 PDF，随后使用本地 BM25。可用 `--pdf` 指定已有的原始文件。

带引用回答、无答案题与失败追踪的演示步骤在[演示指南](docs/DEMO.md)。

## 项目目录

| 要找的东西 | 位置 |
| --- | --- |
| 学习、面试、复盘 | [上手指南](docs/从零上手并学会这个RAG项目.md) · [面试问答](docs/RAG_面试问答.md) · [回顾路线](docs/PROJECT_回顾路线.md) |
| 核心链路和页面 | `raglab/`、`web/`，[设计文档](DESIGN.md) |
| 场景配置、示例和评测 | `scenarios/`、`examples/`、[实验报告](reports/README.md) |
| 工具与自动回归 | `scripts/`、`tests/`、[GitHub Actions](.github/workflows/regression.yml) |
| 本机资料、索引、缓存、请求记录和配置 | `data/`、`indexes/`、`.venv/`、`logs/`、`.env`，均由 Git 忽略 |

## 当前进度

两份独立 PDF 已用 20 道运行前冻结的题验收。默认 E5 路径中，16 道可回答题有 5 道答全，4 道无答案题均拒答。Landsat 的结构化表格模式修复两题、退步两题，继续作为可选项。[逐题报告和复现命令](reports/V1_ACCEPTANCE.md)

本地无密钥回归通过 31 项，覆盖 PDF 导入、检索、页码引用和失败请求追踪。GitHub Actions 首次运行的 Ubuntu 和 Windows 任务均通过。[运行记录](https://github.com/mingyuzi123/RAG/actions/runs/42555279765)

PDF 读序和表格对照已完成。结构化抽取在另一份公开 PDF 上使可回答题从 0/6 提升到 3/6，提升集中在表格题。原布局抽取作为默认，表格模式按场景选择。[6B 逐题验收](reports/STAGE6B_PDF_LAYOUT.md)

第 5 阶段已完成场景配置统一、干净环境运行、故障恢复和真实 PDF 验收。`python -m raglab doctor` 检查资料和索引状态，失败请求可按请求 ID 定位环节。真实 PDF 的可回答题 3/6 答全，无答案题 2/2 拒答。[复现、逐题结果与演示路线](reports/STAGE5_DELIVERY.md)

**最新组合检查：**固定同一批 10 题，v3 自动查询配合现有条件父块/邻块规则，完整且有证据支持的回答由 6/10 到 7/10，新增 P06；实际上下文只在 P06 变化，预算未增加。该组合继续作为可选实验，详见[完整回答组合报告](reports/QUERY_CONTEXT_COMBINED_AUDIT.md)。

**本轮查询改写复测：**v3 提示词在固定 10 题中使标注证据齐进前 3 从 v1 的 7/10 到 8/10；增益来自已参与规则分析的 C14，最初留出的 4 题没有净增；C01 已参与 v3 调整，不能再作为其独立留出题。C01 暴露过“删掉所有比较词”的退步，P01 仍有排名下降。逐题数据和边界见[查询改写 v3 报告](reports/QUERY_REWRITE_V3.md)。

**四个阶段的基础版已搭好，接下来集中回顾学习。**骨架提供固定版本资料获取与切块、SQLite FTS5/BM25、跨语言 E5、RRF 混合检索、带出处 DeepSeek 问答、请求追踪、逐题检索评测和人工答案核验。CrewAI 与 Pydantic 两套官方技术文档通过独立场景包运行；页面显示各自题集、评测和请求记录。页面英文检索词留空时可用 DeepSeek 自动生成并查看、修改；6 题初测中前 3 证据覆盖低于人工词，故仍需扩大验证。自动拆题和多样性选块只保留为实验入口或离线对照。架构见 [DESIGN.md](DESIGN.md)，项目及学习状态见 [PROGRESS.md](PROGRESS.md)，验收见[第 3 阶段](docs/STAGE3_阶段验收与学习路线.md)和[第 4 阶段报告](reports/STAGE4_第二场景与答案质量.md)，之后按[回顾路线](docs/PROJECT_回顾路线.md)学习。

首个场景包使用固定版本的 CrewAI 官方技术文档，覆盖 Agents、Tasks、Tools、Crews 和 Flows。

## CrewAI 场景资料与评测集

[场景清单](scenarios/crewai/manifest.json)固定了 CrewAI 官方仓库的提交和文档版本；[19 道评测题](scenarios/crewai/eval/questions.jsonl)标注了预期证据章节，包含事实、比较、操作、排错和无答案问题。原始文档下载到被 Git 忽略的 `data/`，不会复制到本仓库。

```powershell
python scripts/fetch_crewai_docs.py
python scripts/validate_crewai_eval.py
```

验证脚本检查上游提交号、问题结构和证据章节是否真实存在。17 道可回答题已有检索证据覆盖分数，见[实验报告](reports/README.md)；其余 2 道无答案题用于拒答抽样。

## 运行最小问答链路

使用 Python 3.11 或更新版本。运行上面的资料下载命令后，在仓库根目录执行：

```powershell
python -m raglab index
python -m raglab search "hierarchical process manager agent" --strategy bm25 --top-k 3
```

索引存于 `indexes/`，按场景、文档提交、文件清单和切块参数区分版本；检索结果显示块 ID、标题路径、原文行号和出处。当前英文 FTS5 基线不能可靠处理中文问题，因此问答时明确提供英文检索词：

```powershell
$env:DEEPSEEK_API_KEY = "在本机设置你的密钥"
python -m raglab ask "CrewAI 层级流程需要什么配置？" --strategy bm25 --search-query "hierarchical process manager_llm manager_agent" --top-k 5 --context-k 3
```

密钥只从环境变量读取。可选环境变量 `DEEPSEEK_MODEL` 默认是 `deepseek-flash`。每次问答的候选块、实际送入模型的块、回答、引用编号、耗时与 token 用量保存在被 Git 忽略的 `logs/requests.jsonl`。`citation_numbers_valid` 仅检查引用编号是否指向提供过的块，**不能证明回答真的得到证据支持**。

### 用本地 `.env` 调用 DeepSeek

在仓库根目录的 `.env` 文件中，只填写 `DEEPSEEK_API_KEY=` 后面的密钥；此文件已被 Git 忽略，不要把密钥发到聊天中。然后运行：

```powershell
.\.venv\Scripts\python.exe scripts/run_with_deepseek.py --check
.\.venv\Scripts\python.exe scripts/run_with_deepseek.py
```

`--check` 会用一条测试证据发起一次真实 API 请求，显示回答和 token 用量，因此会消耗少量额度。第二条命令启动本地页面，在页面上即可测试真实的检索与生成。已有 `DEEPSEEK_API_KEY` 环境变量时，它优先于 `.env` 中的值。首次从头运行项目，还需按上文下载文档并建立索引。

本机未配置密钥时，可执行不收费的解析、检索和模拟 API 单元测试：

```powershell
python -m unittest discover -s tests -v
```

切块以标题和段落为界，目标大小为 1800 字符。为保留完整代码块，少数块会超过目标大小；后续会在评测中检验这一取舍对上下文预算和召回的影响。

## 跨语言向量与混合检索

向量检索在本机运行固定版本的 `multilingual-e5-small`，首次运行会下载模型；模型本身和向量索引不提交到 Git。Windows PowerShell 复现命令：

```powershell
python -m pip install -r requirements-vector.txt
python -m raglab vector-index
python -m raglab search "层级流程需要什么管理者配置？" --strategy vector --top-k 3
python -m raglab search "层级流程需要什么管理者配置？" --strategy hybrid --search-query "hierarchical process manager configuration" --top-k 3
```

[E5 模型卡](https://huggingface.co/intfloat/multilingual-e5-small)说明对问题加 `query:` 前缀、对文档加 `passage:` 前缀；本项目将向量归一化后按点积排序。混合检索对 BM25 与向量各取前 20，再用倒数排名融合（RRF）排序。固定历史评测继续使用人工英文词以保持可比性；页面的英文词留空时会调用 DeepSeek 生成可编辑查询，并在请求记录中保存来源、提示词版本和用量。该调用消耗 API 额度，断网时可手填英文词或只用 E5。6 题对照见[自动查询小样本报告](reports/AUTO_QUERY_PILOT.md)。

```powershell
python scripts/evaluate_retrieval.py --strategy bm25 --output reports/crewai-bm25.json
python scripts/evaluate_retrieval.py --strategy vector --query-language zh --output reports/crewai-vector-zh.json
python scripts/evaluate_retrieval.py --strategy vector --query-language en --output reports/crewai-vector-en.json
python scripts/evaluate_retrieval.py --strategy hybrid --query-language zh --output reports/crewai-hybrid-zh.json
```

[实测结果与局限](reports/README.md)记录了 17 道可回答题的逐题证据命中。评测只检查标注章节是否出现在候选与最终上下文中，不代表生成答案正确。

比较题还可以显式拆成 2–4 个检索子问题，让 E5 分别检索，再轮流选取各路候选并去重。例如 C04：

```powershell
python -m raglab search "Agent 和 Task 的 tools 范围有什么区别？" --strategy decomposed --subquery "Agent 的 tools 参数定义了哪些可用工具？" --subquery "Task 的 tools 参数如何限制该任务可用的工具？" --top-k 10
python scripts/evaluate_decomposed.py
```

这是一种**人工拆分的可选策略**，便于先验证多意图检索是否有用；不能把人工子问题的成绩当作自动查询改写的成绩。页面中选择“多查询覆盖”即可编辑子问题和查看每块来自哪一路。6 道比较题的同题对照见[实验报告](reports/README.md)。

页面还提供“DeepSeek 自动拆题”按钮：它只生成可编辑的两条子问题，不会自动发起检索或问答，每次点击会消耗 API 额度。固定提示词后在 6 道新比较题上的结果为 **1/6** 题将全部标注证据送入前 3，低于中文原题 E5 的 2/6 和混合检索的 3/6；因此自动拆题只保留为实验入口，详见[未见题对照](reports/README.md)。

当前还可离线复现“固定候选后如何挑选上下文”的多样性实验：从原混合检索 Top 10 中选最多 3 块，用 E5 块间相似度惩罚内容重复，并将正文总字符数限制在原前 3 块以内。它在原 17 题中只改善 C10（12/17→13/17），在另 6 道比较题中没有提升（3/6→3/6），因此暂不接入默认问答和页面策略。复现命令与一次真实回答对照见[实验 6](reports/README.md)。

新增可在页面选择的“条件合并＋目标邻块（实验）”上下文规则：同一父块的多个定义子块命中时才合并；证据缺少相关查询词时，只补同文件、同章节或相邻章节的前一个块。它要求混合 RRF 和英文关键词，并记录每次扩展原因。固定 35 题的单次真实回答中，完整回答由 29 题升至 33 题；调规则时看过部分题目，因此仍需用全新题集复验。规则、逐题结果和面试讲法见[目标邻块实验](reports/TARGETED_WINDOW_EXPERIMENT.md)。

后续在运行前冻结的 10 道 Pydantic 新题上，两种策略均为 10/10，未出现增益或退步；这是原方案全对的天花板效应。逐题回答、成本和下一轮困难题设计见[新题复验](reports/FRESH_CONTEXT_V1.md)。

本地场景现支持可复制文字的 PDF（单篇不超过 8 MB、200 页）。用 `.\start_lab.cmd` 启动后，从页面“我的本地文档 → 添加或替换资料”上传。手动启动时可先用 `.\.venv\Scripts\python.exe -m pip install -r requirements-pdf.txt` 安装默认抽取依赖。每块限制在单页内，检索结果与回答出处的页码可跳转到原 PDF。整份 PDF 无可提取文字时拒绝导入并提示 OCR；个别文字不足的页会在资料管理中提示。目前按页、段落和长度切块，多份真实资料的表格、脚注和图注覆盖见[独立 PDF 验收](reports/V1_ACCEPTANCE.md)。扫描件仍需 OCR，详见[PDF 接入记录](docs/PDF_接入边界与验收.md)。

## 本地可视化界面

完成关键词建库后，用 `.\start_lab.cmd` 启动完整实验室。要使用 E5 或 RRF，再补建向量索引。也可以手动启动

```powershell
python -m raglab.web
```

浏览器打开 `http://127.0.0.1:8765/`。左侧“切换知识库”可在同一服务中切换 CrewAI、Pydantic 和“我的本地文档”；“资料管理”列出当前场景的文档、原文链接和本地资料状态。选择“我的本地文档”后，可从页面导入不超过 1 MB 的 Markdown/MDX 文件或不超过 8 MB 的文本型 PDF；同名文件须勾选替换。文档存于被 Git 忽略的 `data/local-docs/`，每次变更创建新的内容版本、BM25 与 E5 索引，旧文件和索引仍留在本机用于追溯。若本机 E5 模型不可用，导入仍保留 BM25 索引并在页面提示。固定的 CrewAI/Pydantic 官方资料不受上传影响。切换时题集、索引、评测和请求记录随场景切换。页面可选评测题，查看 BM25、E5、RRF 的排名和得分、标注证据、进入回答上下文的知识块、原文链接，以及最近的问答请求记录。“阶段评测”读取固定版本报告：红色表示候选前 10 未集齐标注证据，黄色表示候选齐了但上下文前 3 未齐，绿色表示前 3 已齐；点击题号回到检索实验。可修改问题、英文检索词、候选 Top K 和上下文 K，直接观察结果变化。在“请求记录”展开评测题问答，可对照实际上下文逐项评审答案要点、引用与拒答；评审保存在本机被忽略的 `logs/answer_reviews.jsonl`，最新结果显示在同一请求下。自定义问题目前没有预期要点，暂不提供这种结构化评审。界面只监听本机 `127.0.0.1`；`--scenario` 指定默认场景，页面仍可切换到其他场景。固定场景的展示信息和可选评测报告来自同目录的 `ui.json`。

没有 `DEEPSEEK_API_KEY` 时，检索实验仍能运行，问答按钮会禁用。要测试真实回答，可在**启动页面前**于同一个 PowerShell 窗口设置环境变量，或按上文使用 `scripts/run_with_deepseek.py` 从本地 `.env` 读取；不要把密钥填写到页面或聊天中。页面与命令行共用同一检索和请求追踪逻辑。

设计阶段讨论过的关键问题与面试表达整理在 [RAG 设计与评测问答](docs/RAG_面试问答.md)。

## 第二场景：Pydantic 文档

第二场景固定 [Pydantic 官方仓库 v2.13.2](https://github.com/pydantic/pydantic/tree/v2.13.2/docs/concepts)的 5 篇概念文档和完整 Git 提交，提供 10 道题及独立页面配置。原文与模型/索引仍留在本地被忽略的目录。首次运行：

```powershell
.\.venv\Scripts\python.exe scripts/fetch_scenario_docs.py --scenario scenarios/pydantic/manifest.json
.\.venv\Scripts\python.exe scripts/validate_scenario.py --scenario scenarios/pydantic/manifest.json
.\.venv\Scripts\python.exe -m raglab --scenario scenarios/pydantic/manifest.json index
.\.venv\Scripts\python.exe -m raglab --scenario scenarios/pydantic/manifest.json vector-index
.\start_lab.cmd
```

在 [本地实验室](http://127.0.0.1:8765/) 的「切换知识库」选择 Pydantic。如果实验室已经运行，直接在现有页面切换。要重算三路检索报告，使用 `scripts/evaluate_retrieval.py --scenario scenarios/pydantic/manifest.json --strategy bm25|vector|hybrid`，BM25 用英文查询，向量与混合用中文原题。固定题集的检索结果、10 次真实回答的人工核验和局限见[第 4 阶段报告](reports/STAGE4_第二场景与答案质量.md)。已复核一个关键反例：CrewAI C07 的前 3 块实际上有正确答案 `manager_llm` 或 `manager_agent`，旧章节标注没有收录这些替代证据；页面现显示标注复核提示，历史实验分数保持不变。

## 阶段交付

1. 设计与评测集。
2. 最小可运行的入库、检索和带出处问答链路。
3. 检索策略对比与错误分析。
4. 第二场景包与复用验证。

每个阶段提交对应的复现步骤和实际验证结果。项目开发中的重要 RAG 设计取舍也会记录在文档中。

### 文档同步约定

每次完成一个功能或实验阶段，提交前核对[入门与学习指南](docs/从零上手并学会这个RAG项目.md)、本 README、[项目与学习进度](PROGRESS.md)、[回顾路线](docs/PROJECT_回顾路线.md)和相关[面试问答](docs/RAG_面试问答.md)：命令能运行，功能状态与限制准确，新增案例能从入口找到。新实验另存报告并链接，保留历史报告的原始结果。文档和代码在同一阶段提交后同步到 GitHub。


2026-11-06 完整回答复测：固定同一批 10 题的 v1/v3 查询，真实调用 20 次并逐要点核对实际证据，完整且有支持的回答从 **5/10 到 6/10**，新增通过 C14，无通过题退步。P01/P06 仍缺关键证据，P04 旧回答的引用格式异常单独记录。见[答案与引用逐题核验](reports/QUERY_REWRITE_ANSWER_AUDIT.md)。
