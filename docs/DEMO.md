# 本地 RAG 演示

Windows 双击根目录的 [start.cmd](../start.cmd)，或在 PowerShell 中运行 `.\start.cmd`。看到地址后打开页面，保留启动窗口。脚本首次下载公开的 NIST SP 1301，校验 SHA-256，并为每次演示在 `logs/resume-demo-*` 创建独立知识库和请求记录。已有原始文件时可运行 `.\start.cmd --pdf "文件路径"`。此路径使用 BM25 和结构化表格抽取，默认可免费运行。[原始 PDF](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1301.pdf)

## 现场演示顺序

1. 打开 [8789 页面](http://127.0.0.1:8789/)。默认选中 L02，英文关键词已填好。点击「运行单路检索」，展开首条候选的完整证据块，沿 `PR.PS-01` 核对 `Current Profile / Rating` 和 `Target Profile / Priority`，再打开第 6 页。绿色标记表示命中标注页，具体值还要在块内核查。
2. 在本机配置 `.env` 或 `DEEPSEEK_API_KEY` 后，在原窗口按 `Ctrl+C` 停止演示，再运行 `.\start.cmd --live`。生成 L02 回答，核对引用是否回到第 6 页。切到 L08，问示例里负责审批变更人员的真实姓名，查看回答是否承认摘录缺证据。每点一次生成会发起一次真实模型请求。
3. 保持页面运行，发送下面的错误请求。结果应为 HTTP 400。复制 `request_id`，在「请求记录」中找到 `failure_stage=input`，说明请求为何在检索前就被拦截。

```powershell
$body = @{ question = 'PR.PS-01 rating priority'; top_k = 1; context_k = 2 } | ConvertTo-Json
try {
    Invoke-RestMethod http://127.0.0.1:8789/api/search -Method Post -ContentType 'application/json' -Body $body
} catch {
    $_.ErrorDetails.Message
}
```

端口被占用时运行 `.\start.cmd --port 8790`，打开打印的地址。若要发送上面的错误请求，也要改成该端口。macOS 或 Linux 可按 [README](../README.md#快速演示) 手动启动，使用 `.venv/bin/python`。

## 自检与复盘

```powershell
.\start.cmd --check
```

自检使用临时端口，实际请求网页、检索接口、原文接口和失败记录，并把结果保存到该次运行目录的 `check.json`。加 `--live` 时会额外生成 L02、L08 两个真实答案，按结果里的请求 ID 可以查到原始证据。

2026-11-09 在 Windows 的全新 Python 3.13.9 虚拟环境中验证，从创建环境、使用本机 pip 缓存安装依赖、自动下载 PDF，到免费 HTTP 自检完成用时约 17 秒。首次联网及依赖下载耗时会随环境变化。用 `--pdf --live --check` 也完成了离线文件导入和两次真实问答，L02 引用第 6 页，L08 说明无法确定姓名，两次共 1137 tokens。[实际验收输出](../reports/RESUME_DEMO_CHECK.json)

这两个案例是已验证的展示题。复盘时，把 L02 的 PDF 表格行、实际候选块和回答引用对齐，再解释 L08 的上下文缺少什么信息。之后可以对照独立资料里的 R03 和 U05。[独立 PDF 冻结题验收](../reports/V1_ACCEPTANCE.md)
