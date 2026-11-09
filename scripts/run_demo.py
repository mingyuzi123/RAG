"""Launch an isolated, pinned PDF demo or verify it with real local HTTP requests."""

from argparse import ArgumentParser
from base64 import b64encode
from hashlib import sha256
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import mkdtemp
from threading import Thread
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.local_sources import MAX_PDF_BYTES, ensure_local_scenario, import_document
from raglab.store import build_index
from raglab.web import create_handler
from scripts.run_with_deepseek import load_local_env, require_key


QUERIES = {"L02": "PR.PS-01 Rating Priority", "L08": "PR.PS-01 designated parties review change requests name"}


def read_pdf(spec: dict, local: Path | None, cache: Path) -> bytes:
    if local is not None or cache.is_file():
        with (local or cache).open("rb") as source:
            pdf = source.read(MAX_PDF_BYTES + 1)
    else:
        request = Request(spec["source"], headers={"User-Agent": "RAG-Lab/1.0 (NIST PDF demo)",
                                                   "Accept": "application/pdf"})
        try:
            with urlopen(request, timeout=45) as source:
                pdf = source.read(MAX_PDF_BYTES + 1)
        except URLError as exc:
            raise RuntimeError(f"下载 NIST SP 1301 失败（{exc.reason}）。可先下载原始 PDF，再用 --pdf 指定文件。") from exc
    if sha256(pdf).hexdigest() != spec["sha256"]:
        raise ValueError("演示 PDF 哈希不匹配，请用 --pdf 指向原始 NIST SP 1301 文件。")
    if local is None and not cache.is_file():
        temporary = cache.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_bytes(pdf)
        temporary.replace(cache)
    return pdf


def prepare_demo(root: Path, pdf: bytes, spec: dict) -> tuple[Path, int]:
    manifest_path = ensure_local_scenario(root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(name="NIST PDF 演示", language="en", pdf_extraction="ordered_tables",
                    retrieval={"strategy": "bm25", "top_k": 5, "context_k": 1, "auto_rewrite": False})
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    manifest = import_document(root, "NIST.SP.1301.pdf", None, pdf_base64=b64encode(pdf).decode("ascii"))
    _, chunks = build_index(root, manifest)

    ui = {"title": "NIST PDF · 证据演示", "badge": "DEMO · 真实 PDF",
          "subtitle": "选择 L02 看表格引用，选择 L08 看证据不足时的回答。",
          "default_example": "L02", "accent": "#287caa",
          "learning_points": ["免费 BM25 检索与原 PDF 页码", "按请求 ID 查看失败环节"]}
    (manifest_path.parent / "ui.json").write_text(json.dumps(ui, ensure_ascii=False), encoding="utf-8")
    evaluation = manifest_path.parent / "eval"
    evaluation.mkdir()
    examples = [{"id": case["id"], "question": case["question"], "expected_points": case["points"],
                 "answerability": "answerable" if case["points"] else "unanswerable",
                 "evidence": [{"path": manifest["files"][0], "heading": f"第 {page} 页"} for page in case["pages"]]}
                for case in spec["cases"] if case["id"] in QUERIES]
    (evaluation / "questions.jsonl").write_text("".join(json.dumps(example, ensure_ascii=False) + "\n" for example in examples), encoding="utf-8")
    (evaluation / "queries_en.json").write_text(json.dumps(QUERIES), encoding="utf-8")
    return manifest_path, chunks


def check_demo(base: str, pdf: bytes, live: bool) -> dict:
    def get(path: str):
        with urlopen(base + path, timeout=15) as response:
            return json.load(response)

    def post(path: str, data: dict):
        req = Request(base + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
        with urlopen(req, timeout=90) as response:
            return json.load(response)

    with urlopen(base, timeout=15) as response:
        if 'id="search-btn"' not in response.read().decode():
            raise RuntimeError("演示页面未加载")
    config = get("/api/config")
    if not config["status"]["keyword_ready"] or config["status"]["deepseek_key_set"] != live:
        raise RuntimeError("演示索引或生成开关状态不正确")
    examples = {example["id"]: example for example in config["examples"]}
    requests = {key: {"question": examples[key]["question"], "english_query": query}
                for key, query in QUERIES.items()}
    first = post("/api/search", requests["L02"])["candidates"][0]
    if first["page_number"] != 6 or not all(term in first["text"] for term in ("Rating: 3 out of 5", "Priority: High")):
        raise RuntimeError("L02 首条证据缺少第 6 页的评分或优先级")
    with urlopen(base + first["source_url"].split("#", 1)[0], timeout=15) as response:
        if response.headers.get_content_type() != "application/pdf" or response.read() != pdf:
            raise RuntimeError("引用无法读取已固定的 PDF 原文")
    try:
        post("/api/search", {**requests["L02"], "top_k": 1, "context_k": 2})
    except HTTPError as exc:
        if exc.code != 400:
            raise
        failure_id = json.load(exc)["request_id"]
    else:
        raise RuntimeError("非法上下文参数未被拦截")
    if not any(row["request_id"] == failure_id and row["failure_stage"] == "input" for row in get("/api/traces")["traces"]):
        raise RuntimeError("请求记录中找不到输入失败")
    result = {"first_evidence": first["source_url"], "keyword_ready": config["status"]["keyword_ready"],
              "vector_ready": config["status"]["vector_ready"], "key_enabled": config["status"]["deepseek_key_set"],
              "failure_request_id": failure_id, "failure_stage": "input"}
    if live:
        result["live_answers"] = {}
        for key, request in requests.items():
            trace = post("/api/ask", request)["trace"]
            result["live_answers"][key] = {"request_id": trace["request_id"], **trace["result"]}
    return result


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, help="Use a local copy of the pinned NIST SP 1301 PDF")
    parser.add_argument("--port", type=int, default=8789)
    parser.add_argument("--live", action="store_true", help="Enable DeepSeek answers using the environment or .env")
    parser.add_argument("--check", action="store_true", help="Verify retrieval, source bytes and failure trace, then exit")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    try:
        if args.live:
            if not os.environ.get("DEEPSEEK_API_KEY"):
                load_local_env()
            require_key()
        else:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        spec = json.loads((ROOT / "reports/STAGE6B_PDF_CASES.json").read_text(encoding="utf-8"))
        logs = ROOT / "logs"
        logs.mkdir(exist_ok=True)
        pdf = read_pdf(spec, args.pdf, logs / "demo-NIST.SP.1301.pdf")
        root = Path(mkdtemp(prefix="resume-demo-", dir=logs))
        manifest, chunks = prepare_demo(root, pdf, spec)
        with ThreadingHTTPServer(("127.0.0.1", 0 if args.check else args.port),
                                 create_handler(root, manifest, assets_root=ROOT / "web")) as server:
            base = f"http://127.0.0.1:{server.server_port}"
            print(f"{base}/ · {chunks} 个块 · {'可生成回答' if args.live else '免费检索'} · {root}", flush=True)
            if args.check:
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    result = check_demo(base, pdf, args.live)
                    (root / "check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                finally:
                    server.shutdown()
                    worker.join(timeout=5)
            else:
                server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"演示启动或检查失败：{exc}\n")


if __name__ == "__main__":
    main()
