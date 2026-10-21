# 可复用技术文档 RAG

一个以技术文档问答为首个场景的 RAG 学习与工程项目。核心目标是让资料源、检索策略和呈现配置可替换，并通过固定问题集和请求追踪验证效果。

## 当前进度

**设计阶段。**目前只有项目蓝图，尚未提供可运行的问答服务或实测指标。架构、范围、评测和阶段交付见 [DESIGN.md](DESIGN.md)。

首个场景包计划使用固定版本的 CrewAI 官方技术文档，覆盖 Agents、Tasks、Tools、Crews 和 Flows。

## CrewAI 场景资料与评测集

[场景清单](scenarios/crewai/manifest.json)固定了 CrewAI 官方仓库的提交和文档版本；[19 道评测题](scenarios/crewai/eval/questions.jsonl)标注了预期证据章节，包含事实、比较、操作、排错和无答案问题。原始文档下载到被 Git 忽略的 `data/`，不会复制到本仓库。

```powershell
python scripts/fetch_crewai_docs.py
python scripts/validate_crewai_eval.py
```

验证脚本检查上游提交号、问题结构和证据章节是否真实存在。目前这些题用于建立评测基线，尚未产生 RAG 分数。

设计阶段讨论过的关键问题与面试表达整理在 [RAG 设计与评测问答](docs/RAG_面试问答.md)。

## 阶段交付

1. 设计与评测集。
2. 最小可运行的入库、检索和带出处问答链路。
3. 检索策略对比与错误分析。
4. 第二场景包与复用验证。

每个阶段提交对应的复现步骤和实际验证结果。项目开发中的重要 RAG 设计取舍也会记录在文档中。
