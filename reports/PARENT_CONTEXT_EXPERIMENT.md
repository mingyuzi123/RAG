# 小块检索、父块回答：LangChain 思路对照实验

日期：2026-11-04。用户所说的“邻近词优化规则”，在 LangChain 官方文档中更接近 [ParentDocumentRetriever](https://reference.langchain.com/python/langchain-classic/retrievers/parent_document_retriever/ParentDocumentRetriever)：用较小的子块定位，再取回其较大的父文档供回答。这里复现该**机制**，并未导入 LangChain 包或替换现有 BM25＋E5＋RRF 检索器。它也不是“相邻词加分”算法。

## 对照设计

- 固定 Pydantic/CrewAI 资料版本、中文题集、英文查询、Top 10 候选、RRF 和上下文 K=3。
- 子块使用上一轮的 `definition_items` 独立索引；按子块原文路径、标题链、行号映射到默认索引中的原始块（父块），按子块排名取去重后的前三个父块。
- 基线为默认索引直接检索的前三块。另跑“每题不超过基线字符预算”的选择；在当前题集上，它与前三个父块完全相同。
- 章节覆盖只作粗指标。Pydantic P01/P06 另用预先标注的答案要点行号检查；C13 核对两侧原文及真实回答。不能将 P06 设计样例当作未见题收益。

## 离线结果

| 场景 | 基线→父块：全部标注章节进入上下文 | 上下文总字符数（全题集） |
| --- | --- | --- |
| Pydantic | 7/8→7/8 | 39,193→38,868 |
| CrewAI | 12/17→12/17 | 74,381→73,732 |

分母只含可回答题。全部 29 题中，没有一题的父块前三项超过原上下文字符预算；这只是本次数据上的观测，不能保证其它语料也如此。逐题结果见[Pydantic](pydantic-parent-context.json)、[CrewAI](crewai-parent-context.json)。

P06：新索引先检索到 `after` 子块 L46–48 和 `before` 子块 L160–166，再映射到 `validators.md` L29–52、L160–203，两个答案要点都进入前三个父块；原基线缺 `after`。P01 的必填字段 L79–80 仍未进入上下文，说明父块回填不能修复所有召回缺口。

C13：上一轮定义项版把“Use Unstructured State Management when”标题单独送入上下文而漏答。父块回填使前三块恢复为原基线的 `flows.mdx` L393–407、L297–341、L500–506，第一块同时保留结构化和非结构化的适用条件。CrewAI 另外五题的父块前三项变化：C01、C02、C09、C15 只是原有证据换序；C04 仍缺工具范围的目标证据；C16 第三块变成与题目无关的文件保存说明，前两块保持 `@tool` 等相关证据。C04、C16 仍有选择风险，章节总分无法发现它们。

## 真实回答复核

使用相同生成函数，分别对 P06、C13 的父块前三项调用一次 DeepSeek；原文和用量见[回答记录](parent-context-answers.json)。P06 正确回答 `before` 在内部解析/校验前、`after` 在后，并分别引用对应父块；输入 1,145 tokens。C13 回答了结构化和非结构化两侧适用条件，引用同一完整父块；输入 837 tokens。此前定义项子块直接回答 P06 输入 586 tokens，C13 输入 355 tokens 且漏答非结构化一侧。父块回填修复了这两个已知案例的证据完整性，但 P06 输入成本约翻倍；单次调用不能代表稳定正确率。

## 判断与复现

该机制在 P06 保留了子块定位能力，在 C13 避免了把列表标题当作完整解释；**比直接把定义项子块交给模型更稳妥**。相对默认基线，目前只证明 P06 这个设计案例得到改善，章节级总分未变，而且 C04/C16 的上下文仍有风险。暂不设为默认策略。若进一步推进，应对未参与设计的题目补充答案要点级标注与配对回答，测量真实延迟和 token 分布，再决定父块粒度及预算策略。

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_parent_context.py
.\.venv\Scripts\python.exe scripts\audit_parent_answers.py
```

第一条只读取已有本地索引和报告；第二条调用本地 `.env` 配置的 DeepSeek API，会产生用量。
