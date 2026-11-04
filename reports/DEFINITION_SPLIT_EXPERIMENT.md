# 结构化定义项切块实验

实验日期：2026-11-04。P06 是设计案例：`validators.md` 中 `after` 的定义在 L46，`before` 在 L160，二者隔着多段代码示例，同章节邻近一块的策略无法同时覆盖。实验版把 Markdown 中“列表项 + 加粗术语 + 冒号解释”单独切成块，保留原标题路径、来源版本和行号。默认解析与索引不变；实验版使用独立的 BM25/E5 索引。

## 固定对照

资料版本、题目、人工英文查询、E5 模型、RRF、候选 Top 10 和上下文前 3 固定。Pydantic 10 题中 8 题可回答、2 题无答案；CrewAI 19 题中 17 题可回答、2 题无答案。无答案题不计章节覆盖分数，但保留候选供核对。Pydantic 从 166 块变为 180 块，CrewAI 从 267 块变为 285 块。

| 场景与策略 | 全部标注章节进前 10：旧→新 | 全部标注章节进前 3：旧→新 | 前 3 内容变化的题 |
| --- | --- | --- | --- |
| Pydantic BM25 | 8/8→8/8 | 7/8→7/8 | P04、P06、P08 |
| Pydantic E5 | 8/8→8/8 | 6/8→6/8 | P06 |
| Pydantic RRF | 8/8→8/8 | 7/8→7/8 | P06 |
| CrewAI RRF | 15/17→15/17 | 12/17→12/17 | C01、C02、C04、C08、C09、C13、C15、C16、C19 |

这些章节级总分没有显示 P06 的句子级变化，也不能证明其他题的答案质量不变。[Pydantic 逐题对照](pydantic-definition-comparison.json)保存了前 3 原文范围和 P01/P06 的要点范围；三路新[BM25](pydantic-definition-bm25.json)、[E5](pydantic-definition-vector.json)、[RRF](pydantic-definition-hybrid.json)报告与 [CrewAI RRF](crewai-definition-hybrid.json)报告保存全部候选 ID。

## 句子级与真实问答

- P06 旧 RRF 前 10 没有 `after` L46 的定义，前 3 只有 `before` L160；新 RRF 把 L46–48 排第 1、L160–166 排第 2，两处均进入回答上下文。一次[真实 DeepSeek 回答](pydantic-definition-p06-answer.json)正确解释 before 在内部解析/校验前、after 在内部校验后，分别引用 `[2]` 与 `[1]`，输入 586、总计 837 tokens。该回答只验证一次，不能据此估计稳定正确率。
- P06 新 E5 虽把 `after` 送进前 3，却把 `before` 挤出前 3；只有结合 BM25 的新 RRF 在这一题同时覆盖两侧。新 BM25 仍只有 `before` 在前 3。
- P01 的无默认值必填句 L79–80 在新旧三路中都没进入前 10；本规则不解决 P01。前一轮的邻块实验与本实验针对不同故障，不能把两题收益相加当作同一个已上线方案。

## 结论与限制

结构化定义项切块在 P06 产生了可解释的改善，并保持现有章节级总分；但 CrewAI 9 题的前 3 内容变化尚未逐条审查，存在答案退步风险。P06 参与了规则设计，不能作为未见题收益。暂不设置为默认解析器。下一步应先人工核对变化题中被替换块是否含独特证据，再选未参与设计的新题做答案质量复验；若要继续优化 P01，需另立候选扩展或更精细的证据选择实验。

## 复现

```powershell
.\.venv\Scripts\python.exe scripts\build_definition_index.py --scenario scenarios\pydantic\manifest.json
.\.venv\Scripts\python.exe scripts\build_definition_index.py --scenario scenarios\crewai\manifest.json
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py --scenario scenarios\pydantic\manifest.json --strategy hybrid --definition-items --output reports\pydantic-definition-hybrid.json
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py --scenario scenarios\crewai\manifest.json --strategy hybrid --definition-items --output reports\crewai-definition-hybrid.json
.\.venv\Scripts\python.exe scripts\compare_definition_experiment.py
.\.venv\Scripts\python.exe scripts\run_definition_answer_sample.py
```

构建 E5 索引和评测向量/混合检索需要本地模型。最后一条会使用本机 `.env` 的 DeepSeek Key 并产生 API 用量；其余命令不调用付费大模型。
