"""No-key HTTP regression for import, retrieval, citation wiring and failure traces."""

from base64 import b64encode
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase, skipUnless
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import os

from raglab.local_sources import ensure_local_scenario
from raglab.web import create_handler
from test_pdf_source import HAS_PYPDF, sample_pdf


@skipUnless(HAS_PYPDF, "install requirements-pdf.txt")
class OfflineHttpTests(TestCase):
    def test_pdf_answer_citation_and_input_failure_over_http(self):
        pdf = sample_pdf("This page contains a catalog of mirror policy names.",
                         "The mirror failover policy allows at most seven retries per server.")
        with TemporaryDirectory() as directory, patch.dict(os.environ), \
             patch("raglab.web.load_model", side_effect=RuntimeError("offline BM25 fixture")):
            os.environ.pop("DEEPSEEK_API_KEY", None)
            root = Path(directory)
            with ThreadingHTTPServer(("127.0.0.1", 0), create_handler(root, ensure_local_scenario(root))) as server:
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                base = f"http://127.0.0.1:{server.server_port}"

                def post(path, data):
                    request = Request(base + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
                    with urlopen(request, timeout=10) as response:
                        return json.load(response)

                try:
                    imported = post("/api/import", {"filename": "policy.pdf", "pdf_base64": b64encode(pdf).decode()})
                    self.assertTrue(imported["status"]["keyword_ready"])
                    self.assertFalse(imported["status"]["deepseek_key_set"])
                    query = {"question": "每个服务器最多重试几次？", "english_query": "mirror failover retries server",
                             "strategy": "bm25", "top_k": 2, "context_k": 1}
                    found = post("/api/search", query)["candidates"][0]
                    self.assertEqual(found["page_number"], 2)
                    self.assertTrue(found["source_url"].endswith("#page=2"))
                    with urlopen(base + found["source_url"].split("#", 1)[0], timeout=10) as response:
                        self.assertEqual(response.headers.get_content_type(), "application/pdf")
                        self.assertEqual(response.read(), pdf)

                    with self.assertRaises(HTTPError) as failure:
                        post("/api/search", {**query, "top_k": 1, "context_k": 2})
                    self.assertEqual(failure.exception.code, 400)
                    with failure.exception as response:
                        request_id = json.load(response)["request_id"]
                    with urlopen(base + "/api/traces", timeout=10) as response:
                        trace = next(item for item in json.load(response)["traces"] if item["request_id"] == request_id)
                    self.assertEqual(trace["failure_stage"], "input")

                    response = {"choices": [{"message": {"content": "最多七次。[1]"}}], "usage": {}}
                    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fixture-only"}), \
                         patch("raglab.generation.call_chat", return_value=(response, "fixture")) as model:
                        asked = post("/api/ask", query)["trace"]
                    model.assert_called_once()
                    self.assertIn("page 2", model.call_args.args[0][1]["content"])
                    self.assertIn("at most seven retries", model.call_args.args[0][1]["content"])
                    self.assertTrue(asked["result"]["citation_numbers_valid"])
                    self.assertEqual(asked["result"]["sources"][0]["chunk_id"], found["id"])
                finally:
                    server.shutdown()
                    worker.join(timeout=5)
