# 第 4 阶段：第二场景与答案质量验收

更新于 2026-10-23。第二场景选择 [Pydantic 官方仓库](https://github.com/pydantic/pydantic)的 v2.13.2，固定提交 `ca3ddd1149bd3b14273922a29da174804496a055`。从 `docs/concepts/` 选取 models、fields、validators、serialization、json_schema 五篇 Markdown；原文放在 Git 忽略的 `data/upstream/pydantic/`，仓库保存来源、版本、范围、题集和重建脚本。

## 复用验收

同一套 MD/MDX 解析、SQLite BM25、E5 向量、RRF 融合、DeepSeek 生成、引用记录和页面处理了第二套资料。新增的是 `scenarios/pydantic/` 的资料清单、页面配置和 10 道题；通用抓取与评测命令读取 `--scenario`，核心检索与生成逻辑没有加入 Pydantic 专属分支。原页面的默认示例、占位文字、学习提示和请求列表仍含 CrewAI 假设，本阶段把文字移入场景配置，并按场景过滤请求与人工评审。

重建顺序：运行 `scripts/fetch_scenario_docs.py --scenario scenarios/pydantic/manifest.json`，再运行 `scripts/validate_scenario.py`；随后用 `python -m raglab --scenario scenarios/pydantic/manifest.json index` 和 `vector-index` 建库。实际得到 **166 个知识块**。运行 `scripts/run_with_deepseek.py --scenario scenarios/pydantic/manifest.json --port 8768` 可打开第二场景。页面已验证显示 Pydantic 题集、三路报告及只属于该场景的请求和评审。两个场景按场景 ID 和资料提交生成不同索引路径。

## 同题检索对照

8 道可回答题参与章节覆盖分数；2 道无答案题只参与拒答抽样。三路都在相同资料提交、同一题集、候选前 10、上下文前 3 下测试。BM25 使用人工英文关键词，E5 使用中文原题，混合检索融合两路，因此输入条件不完全相同。

| 策略 | 标注章节全部进前 10 | 标注章节全部进前 3 |
| --- | ---: | ---: |
| BM25 英文关键词 | 8/8 | 7/8 |
| E5 中文问题 | 8/8 | 6/8 |
| 混合 RRF | 8/8 | 7/8 |

逐题结果见 [`pydantic-bm25.json`](pydantic-bm25.json)、[`pydantic-vector-zh.json`](pydantic-vector-zh.json)、[`pydantic-hybrid-zh.json`](pydantic-hybrid-zh.json)。题目由项目作者按 5 篇文档编写，样本小且受选题影响，不能推断其他技术文档的总体准确率。章节命中只是一种粗代理，同一章节内的不同块可能携带不同事实。

## 真实答案与引用核验

在本机已配置的 DeepSeek API 上，固定混合检索、候选前 10、上下文前 3，对 10 道题各调用一次，接口报告合计 16,439 tokens。每题人工对照预期要点、实际送入的块和引用；审核标签、备注与请求 ID 见 [`pydantic-answer-audit.json`](pydantic-answer-audit.json)，完整回答和证据保存在本机被忽略的 `logs/requests.jsonl`，页面“请求记录”能重新查看和修改评审。

| 题型 | 人工判通过 | 未通过 | 主要发现 |
| --- | ---: | ---: | --- |
| 8 道可回答题 | 6 | 2 | P01、P06 缺少一个预期要点，模型没有补造 |
| 2 道无答案题 | 2 | 0 | 均没有编造具体 S3 bucket 或发布时间 |

P01、P06 的标注章节都进入了前 3，但具体块没有涵盖问题要求的全部事实。**章节命中可以高估可回答性。**P07 的前 3 没集齐标注的两个章节，却从另一个进入上下文的 `Model methods and properties` 块答全且有依据。**章节命中也会低估可回答性。**这两个方向都要求回到原文句子和实际答案核验，不能只看 7/8。

上表是一次调用、单人复核的小样本，不是稳定正确率。P10 虽合理拒答，但附了描述所给摘录主题的引用，略显冗余，值得第二人复核。合理拒答没有引用时，`citation_numbers_valid` 会是 false；它只检验编号格式，不能代替人工判断。用 `scripts/summarize_answer_audit.py --scenario scenarios/pydantic/manifest.json --audit reports/pydantic-answer-audit.json --verify-local` 可复核人工标签与本机请求的一致性。其他机器没有这些日志时，去掉 `--verify-local` 仍可重算标签汇总，但不能独立核验原始回答。重跑问答可使用 `scripts/run_answer_sample.py --scenario scenarios/pydantic/manifest.json`；模型输出和请求 ID 可能变化，需要重新评审。

## CrewAI C07：回答正确，旧标注漏了替代证据

用户问层级流程还需什么管理者信息。原题只把 `Processes > Process Implementations` 标为证据，该块在混合检索第 6 位，所以旧报表显示“候选已找到，前 3 未命中”。实际前 3 的 `Assigning Processes to a Crew`、`Hierarchical Process` 和 JSONC 示例已说明需要 `manager_llm` 或 `manager_agent`。真实 DeepSeek 回答正确给出二选一，引用也与片段一致；该请求已在 CrewAI 页面人工核验为通过。

历史报告保留原标注与分数，以免修改标签后把新成绩误称为检索改进。两个场景的评测页增加了标注复核提示。正式扩大题集时，应把“同一答案的替代来源”标成可接受证据组，并逐要点标注原文范围，避免章节级假阴性或假阳性。

## 后续增强依据

本阶段证明骨架能切换第二套文档并跑通真实问答，仍留下几个可测问题：长代码块可能超过目标字符数；中文到英文检索仍依赖固定 E5，混合检索要手工英文关键词；上下文按排名取前 3，缺少针对答案要点的选块与重排；评测题数少、人工审核只有一人。PDF 解析仍是未来资料适配器，尚未实现。
## 学习复测：P01 章节命中与多查询失败（2026-11-03）

页面以 P01、混合 RRF、候选 Top 10、上下文 K=3 真实问答：前 3 中 `Basic model usage` 命中预设章节，但实际进入上下文的是 `models.md` L105–148，只包含默认值被使用和字符串 `'123'` 转整数 `123`；明确说明无默认值字段必填的 L79–80 没进入。模型仍答出这一正确事实，却仅凭 L105–148 的“有默认值可省略”作“因此无默认值必填”的推断，所给证据不足以支持该断言。另两块关于默认值验证的补充有出处，但不是问题所需的缺失要点。这是答案事实正确、证据支撑不足的例子。

只将 BM25 英文查询改成 `Pydantic BaseModel field without default required` 后，RRF 前 3 转向默认值、字段总览和模型方法，没有补入 L79–80。当前 BM25 把查询词以 OR 连接，宽泛词可召回大量相关但不能回答整题的块。再将问题人工拆成“字段是否必填”和“`'123'` 转换结果”两条中文 E5 子问题，轮流覆盖的前 10 也没有 L79–80 或 L105–108：第一路将 `Field aliases` 排第 1，第二路将 JSON Schema 实现块排第 1。此处属于候选召回失败；轮流选块无法修正每路内部的错误排名。两次改写均为看过 P01 后的诊断尝试，不计入正式策略成绩。

随后用原题与原英文查询将 RRF 诊断范围扩到 Top 30，L79–80 所在的 `models.md` L53–104 块排第 24；原 Top 10 列表没有该块。原排名第一的是同章节相邻的 L105–148。故原始 P01 在关键句层面的缺口首先是候选召回，章节级 Context Hit@3 的绿色状态掩盖了这一点。Top 30 使用更大的融合候选池，这个第 24 名仅供定位，不能直接当作原 Top 10 配置的后续排名。
