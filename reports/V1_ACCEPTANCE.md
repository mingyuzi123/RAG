# 两份独立 PDF 的冻结题验收

2026-11-09。先固定原文件 SHA-256、题目、预期要点和页码，再跑真实问答。冻结提交为 `f3f731cb83f40cbff5c2cdc3c24943fe080c69e5`。两份资料来自不同发布方，均未用于之前的调参。RFC 9111 是 35 页的单栏协议规范，USGS Landsat 9 简报是 2 页的多栏资料，含图注与波段表。[RFC 9111 原文](https://www.rfc-editor.org/rfc/rfc9111.pdf) · [USGS 简报原文](https://pubs.usgs.gov/fs/2019/3008/fs20193008.pdf)

三次运行统一使用中文原问题、E5 候选前 10、直接取前 3 块和 DeepSeek `deepseek-flash`。仅在 Landsat 的第二轮切换为结构化表格抽取。每题每种配置只生成一次。人工逐条核对冻结要点、实际送入的块和回答引用，全部要点有证据才计为完整。无答案题单列，检查模型是否限定在提供的资料范围内，并避免编造具体值。

| 资料与抽取方式 | 块数 | 标注页齐全，前 10 → 前 3 | 完整且有引用支持 | 无答案题拒答 | 请求耗时中位数 | 总 tokens |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| RFC 9111，默认布局 | 533 | 8/8 → 5/8 | 1/8 | 2/2 | 5.01 s | 9546 |
| Landsat，默认布局 | 12 | 8/8 → 8/8 | 4/8 | 2/2 | 3.54 s | 10248 |
| Landsat，结构化表格 | 10 | 8/8 → 6/8 | 4/8 | 2/2 | 3.42 s | 16428 |

默认配置合计 **5/16 答全，4/4 拒答**。共 30 次 HTTP 请求成功，三轮都核对了下载文件与页面原文响应的字节。28 条有引用的回答所用编号均有效，所有上下文来源链接的块 ID 和 `#page=N` 与该编号对应。两条回答因上下文不足而无引用。编号有效只说明可定位，支持关系见逐题表。两份独立文档与单次生成适合暴露缺口，无法估计普遍准确率或稳定耗时。

## RFC 9111

| 题目 | 裁决 | 实际证据与缺口 |
| --- | --- | --- |
| R01 · Vary 匹配 | 部分 | 第 11 页引用支持通配符始终不匹配。同页关于两次均缺失的条件未进入前 10。 |
| R02 · Authorization 复用 | 部分 | 第 25 页支持 s-maxage 对过期复用的再验证要求。前 10 里第 10 页只有节标题，缺完整三项列表。 |
| R03 · 304 与完整响应 | 未答出 | 第 17 页排名第 1 的块只引出处理规则。两条实际规则同在该页排名第 4 的块。 |
| R04 · 新鲜期优先级 | 部分 | 第 25 页支持 s-maxage 优先；第 13 页未进前 3，缺后续优先级与日期差公式。 |
| R05 · Age 与驻留时间 | 部分 | 第 15 页支持驻留时间公式。定义所在第 19 页在候选里，未进前 3。 |
| R06 · only-if-cached 与断网 | 部分 | 第 22 页引用支持断网时不可绕过再验证。答案没给出出错处理，也缺 only-if-cached 的两种结果。 |
| R07 · URI 失效 | 完整 | 第 19 页支持目标 URI 必须失效，第 32 页附录支持不同源 URI 的限制，是冻结标注页以外的有效证据。 |
| R08 · 两种 no-cache | 部分 | 第 21 页支持请求指令。第 23 页进入上下文的块只有相关标题，缺无参数响应指令的要求。 |
| R09、R10 · 磁盘容量与月费 | 拒答 | 均明确资料摘录不足，无编造数值。所引局部摘录不能证明其他资料也没有答案。 |

## Landsat 9

| 题目 | 默认布局 | 结构化表格 |
| --- | --- | --- |
| U01 · 轨道参数 | 未答出。第 1 页命中，但轨道高度和倾角都未入上下文。 | 未答出。前三块均来自第 2 页。 |
| U02 · NASA 与 USGS 分工 | 未答出。第 1 页进入上下文，职责段落未入选。 | 完整。引用第 1 页正文，覆盖双方职责。 |
| U03 · 重访与错开天数 | 完整。第 1 页支持 16 天和 8 天。 | 完整。第 1 页支持同样两点。 |
| U04 · Band 8 | 未答出。第 2 页所选表格段未含 Band 8。 | 完整。第 2 页的 Band 8 行同时支持波长范围与空间分辨率。 |
| U05 · 热波段与脚注 | 完整。第 2 页表格和脚注分别支持波长范围及采集、重采样分辨率。 | 部分。两行入选，脚注在第 4 名，只答全两个波长范围。 |
| U06 · OLI 量化精度 | 完整。第 2 页正文支持 12 位到 14 位。 | 完整。第 2 页正文支持同样两点。 |
| U07 · 仪器寿命与耗材 | 完整。第 2 页正文覆盖 5 年与 10 年以上。 | 未答出。含设计寿命的正文掉到第 7 名或之后。 |
| U08 · 自然色图与分辨率 | 未答出。两页都命中，图注在第 6 名，前三块也未集齐表格值。 | 部分。引用支持三个波段都是 30 米，确认图中所用波段的图注在第 7 名。 |
| U09、U10 · 运营费用与关机日 | 两题均拒答。 | 两题均拒答。 |

结构化抽取让 U02 和 U04 从未答出变为完整，也让 U05 和 U07 从完整降级。保留原布局为默认，结构化表格作为可选项。验收可先看 R03 的同页不同块，再看 U05 的表格行与脚注，分别判断问题出在召回、上下文选择还是回答阶段。

## 复现

冻结题集为 [RFC 9111](V1_RFC9111_CASES.json) 和 [Landsat 9](V1_LANDSAT_CASES.json)。逐请求输出为 [RFC 默认布局](V1_RFC9111_RESULTS.json)、[Landsat 默认布局](V1_LANDSAT_LAYOUT.json) 和 [Landsat 表格模式](V1_LANDSAT_TABLES.json)，含请求 ID、候选页、实际所选块、生成文本、引用和用量。重新运行会在被 Git 忽略的目录生成完整候选与上下文记录。

在已按 [README](../README.md) 配置 E5 和本地 DeepSeek 密钥的环境里，从仓库根目录执行。评测脚本先校验 PDF 哈希，再建隔离索引。三条评测命令合计调用 DeepSeek 30 次。

```powershell
New-Item -ItemType Directory -Force logs/v1-acceptance | Out-Null
Invoke-WebRequest https://www.rfc-editor.org/rfc/rfc9111.pdf -OutFile logs/v1-acceptance/rfc9111.pdf
Invoke-WebRequest https://pubs.usgs.gov/fs/2019/3008/fs20193008.pdf -OutFile logs/v1-acceptance/fs20193008.pdf
.\.venv\Scripts\python.exe scripts/evaluate_stage5_pdf.py logs/v1-acceptance/rfc9111.pdf --cases reports/V1_RFC9111_CASES.json --output logs/v1-acceptance/rfc-layout.json
.\.venv\Scripts\python.exe scripts/evaluate_stage5_pdf.py logs/v1-acceptance/fs20193008.pdf --cases reports/V1_LANDSAT_CASES.json --output logs/v1-acceptance/landsat-layout.json
.\.venv\Scripts\python.exe scripts/evaluate_stage5_pdf.py logs/v1-acceptance/fs20193008.pdf --cases reports/V1_LANDSAT_CASES.json --extraction ordered_tables --output logs/v1-acceptance/landsat-tables.json
```

## 无密钥回归

[GitHub Actions 工作流](../.github/workflows/regression.yml) 配置在推送 main、打开或更新 PR、手动触发时运行，覆盖 Ubuntu / Python 3.11 与 Windows / Python 3.13。HTTP 集成测试在本机临时目录生成 PDF，真实走上传、BM25 检索、原文件与页码链接、参数错误和请求 ID 追踪。问答使用固定的模拟响应，并检查生成器收到的确实是第 2 页原文块，引用也绑定到该块。CI 回归用于验证接口和证据链。真实模型效果由上面的冻结题评测验证。

```powershell
python -m pip install -r requirements-pdf.txt
python -m unittest discover -s tests -v
```

Windows / Python 3.13 的独立环境已通过全部 31 项。GitHub Actions 首次运行的 Windows / Python 3.13 与 Ubuntu / Python 3.11 任务均通过。[远程验收记录](https://github.com/mingyuzi123/RAG/actions/runs/42555279765)
