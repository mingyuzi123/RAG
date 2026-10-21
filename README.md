# 可复用技术文档 RAG

一个以技术文档问答为首个场景的 RAG 学习与工程项目。核心目标是让资料源、检索策略和呈现配置可替换，并通过固定问题集和请求追踪验证效果。

## 当前进度

**第二阶段开发中。**已提供固定文档的 MDX 切块、可追溯的 SQLite FTS5/BM25 检索基线和 DeepSeek 问答命令。中文问题目前需手工提供英文检索词；跨语言向量检索、自动评测及 Web 页面尚未接入。架构、范围和阶段交付见 [DESIGN.md](DESIGN.md)。

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

密钥只从环境变量读取，不要填写在仓库文件或聊天中。可选环境变量 `DEEPSEEK_MODEL` 默认是 `deepseek-flash`。每次问答的候选块、实际送入模型的块、回答、引用编号、耗时与 token 用量保存在被 Git 忽略的 `logs/requests.jsonl`。`citation_numbers_valid` 仅检查引用编号是否指向提供过的块，**不能证明回答真的得到证据支持**。

本机未配置密钥时，可执行不收费的解析、检索和模拟 API 单元测试：

```powershell
python -m unittest discover -s tests -v
```

切块以标题和段落为界，目标大小为 1800 字符。为保留完整代码块，少数块会超过目标大小；后续会在评测中检验这一取舍对上下文预算和召回的影响。

设计阶段讨论过的关键问题与面试表达整理在 [RAG 设计与评测问答](docs/RAG_面试问答.md)。

## 阶段交付

1. 设计与评测集。
2. 最小可运行的入库、检索和带出处问答链路。
3. 检索策略对比与错误分析。
4. 第二场景包与复用验证。

每个阶段提交对应的复现步骤和实际验证结果。项目开发中的重要 RAG 设计取舍也会记录在文档中。
