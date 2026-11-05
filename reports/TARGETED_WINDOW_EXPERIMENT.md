# 条件合并＋目标邻块：从局部修复到整题集净增

日期：2026-11-04。目标：针对 P01/P06/H01 等“原文有答案，但最终上下文缺一处”的故障，在不增加每题原始前三块字符预算的情况下，提升完整回答数。文档版本、问题、英文查询、Top 10、回答上下文 K=3 和 DeepSeek 生成函数固定。

## 规则来源与本项目改造

- [LangChain ParentDocumentRetriever](https://reference.langchain.com/python/langchain-classic/retrievers/parent_document_retriever/ParentDocumentRetriever)说明“小块检索、大块返回”的父子块机制。上一轮直接取父块使 P06 改善，但在整套题上只有 1 题净增。
- [LlamaIndex AutoMergingRetriever](https://developers.llamaindex.ai/python/framework/integrations/retrievers/auto_merging_retriever/)在足够多子节点命中同一父节点时合并。本项目仅在**同一父块至少两个子块进入 Top 10，且命中子块占该父块全部子块的比例大于 0.5**时合并；否则保留小块。这是借鉴机制的本地实现，并未导入 LlamaIndex。
- [LlamaIndex sentence window](https://developers.llamaindex.ai/python/examples/node_postprocessor/metadatareplacementdemo/)先用细粒度节点检索，再在生成前取周围上下文。本项目文档是 Markdown/MDX，窗口单位改为**原索引中的相邻块**，而不是句子。只检查同文件的前一个父块；同标题时要求它含有当前证据尚未覆盖的英文查询词，邻接的兄弟标题时要求标题含有尚未出现的查询词。每题最多补一个块，按来源顺序插在命中块后；总共最多 K=3，不能超过原前三块字符预算。英文关键词停用词集合、单次补块上限和前向窗口是本项目的实验规则，不是框架默认参数。

该设计把两类故障分开：P06/C13 是**块太碎**，用条件父块合并；P01/C10/H01 是**相邻解释未进入上下文**，用相关窗口补候选。C04 的 Agent/Task tools 分散在不同位置，邻块规则不能修复，仍需要多查询覆盖或更强的重排。最终答案保留每块的原路径、行号和引用编号。网页提供“条件合并＋目标邻块（实验）”选项，并在 trace 中记录原混合检索候选、定义子块候选、所选块及扩展原因。当前选项要求混合 RRF 和英文关键词；默认问答流程不变。

## 结果

离线章节级完整覆盖：Pydantic **7/8→8/8**，CrewAI **12/17→13/17**，此前 6 道 CrewAI 对比题 **3/6→4/6**。此指标只用于定位，不能代替回答质量。[Pydantic 逐题选块](pydantic-targeted-window.json)、[CrewAI 逐题选块](crewai-targeted-window.json)、[对比题选块](crewai-targeted-window-heldout.json)记录完整路径和行号。

真实回答按此前冻结的预设要点逐题判分。35 题（31 可回答、4 应拒答）中，未改变上下文的题沿用同一次回答；改变的题各调用一次 DeepSeek。原答案见[条件合并回答](auto-merge-answers.json)、[补邻块回答](targeted-window-answers.json)，[逐题判分](targeted-window-grades.json)保存来源与得失。

| 题集 | 原默认方案 | 本规则 | 净变化 |
| --- | ---: | ---: | ---: |
| Pydantic 可回答 | 6/8 | 8/8 | +2（P01、P06） |
| CrewAI 可回答 | 15/17 | 16/17 | +1（C10） |
| 6 道 CrewAI 对比题 | 4/6 | 5/6 | +1（H01） |
| 全部可回答 | **25/31** | **29/31** | **+4** |
| 4 道应拒答 | 4/4 | 4/4 | 0 |
| 全部 | **29/35** | **33/35** | **+4，未观察到完整题退步** |

P01 补入 `models.md` L53–104 后，同时覆盖“无默认值字段必填”和字符串转整数；C10 补入 `flows.mdx` L100–109 的 `@start` 入口定义；H01 补入 `processes.mdx` L49–54 的顺序任务上下文描述；P06 的 before/after 子块与父块组合仍完整。P07 也补入了相邻 Python mode 块，原本完整的答案保持完整。这是单次回答结果；引用编号有效不代表每条断言必然受支持，关键变化题已按原文复核。

当前不足：C04 仍未找齐 Agent/Task tools 两侧证据，H03 仍未说清 `output_pydantic` 的模型验证。字符预算相同不代表真实 token、索引构建时间或端到端延迟相同；需另行计量。最关键的是，H01 已在规则调整时被查看，**这 6 题不再是独立未见验收集**。本轮能证明现有固定题集的单次完整回答数上升，不能据此承诺未来问题也提高。故作为可在页面上选择的实验策略，暂不改默认。

## 面试时可说明

“我们先定位到两种不同的上下文故障：P06 是切块后定义分散，P01/H01 是正确的邻块未被选入。借鉴 ParentDocumentRetriever、AutoMergingRetriever 和 sentence window，我做了有条件的父块合并和查询词约束的单块窗口。每次扩展有原文行号、原因和预算记录。固定 35 题里完整回答从 29 提升到 33，未观察到退步；但调参时看过的题不能再叫独立测试，所以仍保留为实验策略，待新题复验。”

## 复现

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_auto_merge_context.py
.\.venv\Scripts\python.exe scripts\evaluate_targeted_window.py
.\.venv\Scripts\python.exe scripts\audit_auto_merge_answers.py
.\.venv\Scripts\python.exe scripts\audit_targeted_window_answers.py
.\.venv\Scripts\python.exe scripts\summarize_targeted_window.py
```

两条回答脚本使用 `.env` 的 DeepSeek API；已有结果会按题跳过，不重复计费。
