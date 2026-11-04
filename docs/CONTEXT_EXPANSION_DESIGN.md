# 邻近证据扩展：设计草案

状态：第一轮离线实验完成，尚未成为默认问答策略。动机来自 Pydantic P01：RRF 原前 3 的 `models.md` L105–148 回答了默认值和 `'123'` 转换，缺失的“无默认值字段必填”在同章节前一块 L53–104；诊断性 Top 30 中后者排第 24。扩上下文 K 到 10 无法解决原 Top 10 候选缺失。

## 借鉴与取舍

- [LlamaIndex 的 sentence window](https://developers.llamaindex.ai/python/examples/node_postprocessor/metadatareplacementdemo/)先检索小片段，生成前换入周围窗口。我们借鉴“检索与生成的粒度可不同”，但当前块常达 1800 字符，不能照搬其按句扩窗的窗口大小。
- [LangChain ParentDocumentRetriever](https://reference.langchain.com/python/langchain-classic/retrievers/parent_document_retriever/ParentDocumentRetriever)用小子块定位，再返回更大的父文档。我们先用同章节邻块近似父级上下文；整篇文档可能过长。
- [Anthropic Contextual Retrieval](https://www.anthropic.com/research/contextual-retrieval)同时讨论为块补上下文、融合与重排。这些步骤影响不同环节；本实验只改生成前的候选扩展与选择，不把其报告中的提升数字直接迁移到本题集。
- [RAGChecker](https://arxiv.org/abs/2408.08067)强调分别诊断检索与生成，避免只看粗粒度章节命中。

## 第一轮实验方案

1. 固定资料版本、题集、原始 RRF Top 10 与生成提示词。保留原候选排名和块 ID。
2. 从原前 3 块出发，在同一 `source_path`、同一 `heading_path` 中找紧邻的前后块。只收集候选，不直接送入模型；按原文行号定位并去重。邻块必须属于当前资料版本。
3. 对扩展后的候选在**相同字符预算**内选块，最多 3 个原始块；可以少于 3 个。第一轮规则按原命中排名遍历，每个命中块后紧跟它的同章节前、后邻块；若块放不下则跳过。这个顺序只是实验基线，尚未按问题相关度重排。不要一次同时改检索、扩展和重排。
4. 每个送入的块保留自己的来源文件、行号、ID 和引用编号。日志另外记录它是原检索命中还是由哪块扩展而来，以及被预算挤出的块。

## 验收口径

先补充**答案要点对应的原文范围**，例如 P01 的 `models.md` L79–80、L105–108。评估分三层：原候选 Top 10 是否有证据；扩展候选与最终上下文是否覆盖各要点；真实回答的每个断言是否受引用支持。另记输入 token、总用量、延迟和逐题退步。P01 是设计案例，不计入未见题收益；在 P06 及其他未参与参数选择的问题上复验。若只改善 P01 或引入更多无依据断言，不设为默认策略。

## 尚待验证的设计问题

“同章节且相关”只能缩小搜索范围，不能直接判断邻块提供了新证据。在线系统不能读取评测题的标准答案。第一轮先测扩展是否带来足够多的有效候选，以及预算如何挤出原块；再考虑加入可插拔的重排器，而不是为 P01 写固定阈值。未来接入 PDF 时，邻接关系还必须考虑页码、标题与表格边界。

## 第一轮结果与复现

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_neighbor_context.py
.\.venv\Scripts\python.exe scripts\run_neighbor_answer_sample.py
```

第一条命令只读取固定的 Pydantic 混合检索报告和索引，不调用 API；产生[逐题对照](../reports/pydantic-neighbor-context.json)。第二条使用本机 `.env` 的 DeepSeek Key 对 P01 新上下文调用一次，产生[回答记录](../reports/pydantic-neighbor-p01-answer.json)，会消耗 API 额度。标准答案的[原文范围标注](../scenarios/pydantic/eval/evidence_spans.json)只在选块后用于评估，不参与线上选择。

- P01：原上下文缺 L79–80；实验选入同章节前一块 L53–104，保留原首块 L105–148，共两块、3401 字符，未超过原三块的 3489 字符。两个标注原文范围都进入上下文。一次真实回答的三个要点均能由引用块支持；输入 1024 tokens，原单次回答输入 1010 tokens，未见输入成本下降。
- P06：原上下文已有 before 的 L160–203，after 的 L46 未被补入扩展候选。这说明“紧邻一个块”不足以跨过同章节的多段示例；不能用 P01 的成功概括为通用修复。
- 8 道可回答题的**章节级**全证据覆盖仍为 7/8；7 道题的选块顺序或内容变化，其中 P01、P05、P06、P07、P08、P09 有块替换。其余题尚无答案要点级原文标注或真实新回答复核，因此章节总分不变不代表没有退步。

结论：窗口扩展在 P01 找到了所缺的邻块，但尚不足以设为默认策略。下一步先核验被替换块是否含独特证据，补足 P06/P07 等题的句子级标签，再讨论选择规则和重排器；保持未参与规则设计的问题用于复验。
