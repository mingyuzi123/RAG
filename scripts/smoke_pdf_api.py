"""End-to-end local HTTP and DeepSeek smoke test for PDF page citations."""

from base64 import b64encode
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
from urllib.request import Request, urlopen
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from raglab.local_sources import ensure_local_scenario  # noqa: E402
from raglab.web import create_handler  # noqa: E402
from scripts.run_with_deepseek import load_local_env, require_key  # noqa: E402
from test_pdf_source import sample_pdf  # noqa: E402


def main() -> None:
    load_local_env()
    require_key()
    pdf = sample_pdf(
        "The first page explains that apples are red and contains no retry policy.",
        "The second page states that each task may retry at most four times.")
    with TemporaryDirectory(dir=ROOT) as folder:
        root = Path(folder)
        manifest_path = ensure_local_scenario(root)
        with patch("raglab.web.load_model", return_value=object()), \
             patch("raglab.web.build_vectors", side_effect=RuntimeError("E5 skipped for smoke test")):
            server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(root, manifest_path))
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f"http://127.0.0.1:{server.server_port}"

            def post(path: str, data: dict) -> dict:
                request = Request(base + path, data=json.dumps(data).encode("utf-8"),
                                  headers={"Content-Type": "application/json", "Host": "127.0.0.1"})
                with urlopen(request, timeout=60) as response:
                    return json.load(response)

            try:
                imported = post("/api/import?scenario=local-docs", {
                    "filename": "smoke.pdf", "content": None,
                    "pdf_base64": b64encode(pdf).decode("ascii"), "replace": False})
                query = {"question": "每个任务最多重试几次？", "english_query": "task retry four times",
                         "strategy": "bm25", "top_k": 3, "context_k": 1}
                searched = post("/api/search?scenario=local-docs", query)
                top = searched["candidates"][0]
                assert top["page_number"] == 2, top
                source = base + top["source_url"].split("#", 1)[0]
                with urlopen(source, timeout=10) as response:
                    assert response.headers["Content-Type"] == "application/pdf"
                    assert response.read() == pdf
                answered = post("/api/ask?scenario=local-docs", query)["trace"]
                assert answered["result"]["citation_numbers_valid"]
                assert answered["result"]["sources"][0]["url"].endswith("#page=2")
                assert "四" in answered["result"]["answer"] or "4" in answered["result"]["answer"]
                report = {"imported_chunks": imported["chunks"], "sparse_pages": imported["sparse_pages"],
                          "top_page": top["page_number"], "source_content_type": "application/pdf",
                          "source_link": top["source_url"],
                          "answer": answered["result"]["answer"],
                          "answer_source_page": answered["selected_chunks"][0]["page_number"],
                          "citation_numbers_valid": answered["result"]["citation_numbers_valid"],
                          "usage": answered["result"]["usage"]}
                output = ROOT / "reports/PDF_SMOKE_TEST.json"
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print("PDF HTTP + DeepSeek page citation passed", output)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    main()
