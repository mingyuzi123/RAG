# 可复用技术文档 RAG

一个以技术文档问答为首个场景的 RAG 学习与工程项目。核心目标是让资料源、检索策略和呈现配置可替换，并通过固定问题集和请求追踪验证效果。

## 当前进度

**策略与界面阶段。**已提供固定文档的 MDX 切块（包括表格按行分组）、SQLite FTS5/BM25、跨语言 E5 向量检索、混合检索、比较题多查询覆盖、按证据章节计算的检索评测、本地可视化界面，以及 DeepSeek 带出处问答命令。混合检索仍需手工提供英文关键词；多查询策略目前需人工提供子问题。答案与引用的人工核验入口已接入请求记录，当前只有少量真实抽样，尚无完整答案质量分数。多样性选块完成离线实验，跨组未见收益，未设为默认策略。架构与范围见 [DESIGN.md](DESIGN.md)，项目和学习状态见 [PROGRESS.md](PROGRESS.md)。

首个场景包计划使用固定版本的 CrewAI 官方技术文档，覆盖 Agents、Tasks、Tools、Crews 和 Flows。

## CrewAI 场景资料与评测集

[场景清单](scenarios/crewai/manifest.json)固定了 CrewAI 官方仓库的提交和文档版本；[19 道评测题](scenarios/crewai/eval/questions.jsonl)标注了预期证据章节，包含事实、比较、操作、排错和无答案问题。原始文档下载到被 Git 忽略的 `data/`，不会复制到本仓库。

```powershell
python scripts/fetch_crewai_docs.py
python scripts/validate_crewai_eval.py
```

验证脚本检查上游提交号、问题结构和证据章节是否真实存在。目前这些题用于建立评测基线，尚未产生 RAG 分数。

## 运行最小问答链路

使用 Python 3.11 或更新版本。运行上面的资料下载命令后，在仓库根目录执行：

```powershell
python -m raglab index
python -m raglab search "hierarchical process manager agent" --top-k 3
```

索引存于 `indexes/`，按场景、文档提交、文件清单和切块参数区分版本；检索结果显示块 ID、标题路径、原文行号和出处。当前英文 FTS5 基线不能可靠处理中文问题，因此问答时明确提供英文检索词：

```powershell
$env:DEEPSEEK_API_KEY = "在本机设置你的密钥"
python -m raglab ask "CrewAI 层级流程需要什么配置？" --search-query "hierarchical process manager_llm manager_agent" --top-k 5 --context-k 3
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

[E5 模型卡](https://huggingface.co/intfloat/multilingual-e5-small)说明对问题加 `query:` 前缀、对文档加 `passage:` 前缀；本项目将向量归一化后按点积排序。混合检索对 BM25 与向量各取前 20，再用倒数排名融合（RRF）排序；其英文检索词目前由人填写，避免把查询翻译质量混进检索策略实验。

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

## 本地可视化界面

完成关键词和向量建库后，启动本地页面：

```powershell
python -m raglab.web
```

浏览器打开 `http://127.0.0.1:8765/`。页面可选 19 道评测题，查看 BM25、E5、RRF 的排名和得分、标注证据、进入回答上下文的知识块、原文链接，以及最近的问答请求记录。可修改问题、英文检索词、候选 Top K 和上下文 K，直接观察结果变化。在“请求记录”展开评测题问答，可对照实际上下文逐项评审答案要点、引用与拒答；评审保存在本机被忽略的 `logs/answer_reviews.jsonl`，最新结果显示在同一请求下。自定义问题目前没有预期要点，暂不提供这种结构化评审。界面只监听本机 `127.0.0.1`；更换场景时传入 `--scenario` 路径，场景标题和展示信息来自同目录的 `ui.json`。

没有 `DEEPSEEK_API_KEY` 时，检索实验仍能运行，问答按钮会禁用。要测试真实回答，可在**启动页面前**于同一个 PowerShell 窗口设置环境变量，或按上文使用 `scripts/run_with_deepseek.py` 从本地 `.env` 读取；不要把密钥填写到页面或聊天中。页面与命令行共用同一检索和请求追踪逻辑。

设计阶段讨论过的关键问题与面试表达整理在 [RAG 设计与评测问答](docs/RAG_面试问答.md)。

## 阶段交付

1. 设计与评测集。
2. 最小可运行的入库、检索和带出处问答链路。
3. 检索策略对比与错误分析。
4. 第二场景包与复用验证。

每个阶段提交对应的复现步骤和实际验证结果。项目开发中的重要 RAG 设计取舍也会记录在文档中。
