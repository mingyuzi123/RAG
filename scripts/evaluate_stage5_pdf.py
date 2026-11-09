"""Run the frozen Stage 5 PDF cases through an isolated local HTTP server."""

from argparse import ArgumentParser
from base64 import b64encode
from hashlib import sha256
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import mkdtemp
from threading import Thread
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.local_sources import ensure_local_scenario
from raglab.web import create_handler
from scripts.run_with_deepseek import load_local_env, require_key


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec_bytes = (ROOT / "reports/STAGE5C_PDF_CASES.json").read_bytes()
    spec = json.loads(spec_bytes)
    pdf = args.pdf.read_bytes()
    if sha256(pdf).hexdigest() != spec["sha256"]:
        parser.error("PDF SHA256 differs from the frozen source")
    if args.output.exists():
        parser.error("output already exists")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        load_local_env()
    require_key()
    cached_hf = ROOT / ".venv/hf"
    if (cached_hf / "hub").is_dir():
        os.environ.setdefault("HF_HOME", str(cached_hf))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    root = Path(mkdtemp(prefix="stage5c-", dir=logs))
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(root, ensure_local_scenario(root)))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(path: str, payload: dict) -> dict:
        request = Request(f"{base}{path}?scenario=local-docs", json.dumps(payload).encode("utf-8"),
                          {"Content-Type": "application/json"})
        with urlopen(request, timeout=120) as response:
            return json.load(response)

    try:
        imported = post("/api/import", {"filename": "NIST.SP.1300.pdf", "pdf_base64": b64encode(pdf).decode("ascii")})
        if imported["vector_error"] or not imported["status"]["vector_ready"]:
            raise RuntimeError(f"PDF vector index unavailable: {imported['vector_error']}")
        with urlopen(f"{base}/api/config?scenario=local-docs", timeout=10) as response:
            document = json.load(response)["documents"][0]
        with urlopen(base + document["url"], timeout=10) as response:
            if response.headers.get_content_type() != "application/pdf" or response.read() != pdf:
                raise ValueError("source endpoint did not return the imported PDF")
        result = {"source": spec["source"], "pdf_sha256": spec["sha256"],
                  "case_sha256": sha256(spec_bytes).hexdigest(), "settings": spec["settings"],
                  "trace_log": (root / "logs/requests.jsonl").relative_to(ROOT).as_posix(),
                  "import": imported, "source_bytes_verified": True, "rows": []}
        for case in spec["cases"]:
            started = perf_counter()
            try:
                trace = post("/api/ask", {"question": case["question"], **spec["settings"]})["trace"]
                selected = [{key: item[key] for key in ("id", "page_number", "start_line", "end_line", "source_url")}
                            for item in trace["selected_chunks"]]
                row = {"id": case["id"], "request_id": trace["request_id"],
                       "candidate_pages": [item["page_number"] for item in trace["candidates"]],
                       "selected": selected, **trace["result"], "generation_ms": trace["generation_ms"]}
            except HTTPError as exc:
                row = {"id": case["id"], "http_status": exc.code, **json.load(exc)}
            row["request_ms"] = round((perf_counter() - started) * 1000, 2)
            result["rows"].append(row)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(case["id"], row.get("request_id"), row.get("http_status", 200), flush=True)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()
