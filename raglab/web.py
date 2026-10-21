"""Local-only learning UI, backed by the same workflow as the CLI."""

from argparse import ArgumentParser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
import json
import traceback

from .service import answer, compare, recent_traces, retrieve, status
from .store import index_path, load_manifest
from .vector import load_model


ROOT = Path(__file__).resolve().parents[1]
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/styles.css": ("styles.css", "text/css; charset=utf-8")}


def create_handler(root: Path, manifest_path: Path):
    manifest = load_manifest(manifest_path)
    db_path = index_path(root, manifest, 1800)
    ui_path = manifest_path.parent / "ui.json"
    ui = json.loads(ui_path.read_text(encoding="utf-8")) if ui_path.is_file() else {"title": manifest["id"]}
    eval_dir = manifest_path.parent / "eval"
    questions_path = eval_dir / "questions.jsonl"
    query_path = eval_dir / "queries_en.json"
    questions = ([json.loads(line) for line in questions_path.read_text(encoding="utf-8").splitlines()]
                 if questions_path.is_file() else [])
    english = json.loads(query_path.read_text(encoding="utf-8")) if query_path.is_file() else {}
    examples = [{"id": item["id"], "question": item["question"],
                 "english_query": english.get(item["id"], ""),
                 "answerability": item.get("answerability"), "evidence": item.get("evidence", [])}
                for item in questions]
    model_cache = {"model": None}

    class Handler(BaseHTTPRequestHandler):
        def _headers(self, code: int, content_type: str, size: int):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; object-src 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()

        def _json(self, code: int, value):
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self._headers(code, "application/json; charset=utf-8", len(body))
            self.wfile.write(body)

        def _allowed_host(self) -> bool:
            host = self.headers.get("Host", "").split(":", 1)[0].lower()
            origin = self.headers.get("Origin")
            return host in ("127.0.0.1", "localhost") and (not origin or
                    urlparse(origin).netloc == self.headers.get("Host"))

        def _model(self):
            if model_cache["model"] is None:
                model_cache["model"] = load_model()
            return model_cache["model"]

        def do_GET(self):
            if not self._allowed_host():
                self._json(403, {"error": "Local access only"})
                return
            path = urlparse(self.path).path
            if path in ASSETS:
                name, mime = ASSETS[path]
                body = (root / "web" / name).read_bytes()
                self._headers(200, mime, len(body))
                self.wfile.write(body)
            elif path == "/api/config":
                self._json(200, {"ui": ui, "examples": examples, "status": status(root, manifest)})
            elif path == "/api/traces":
                self._json(200, {"traces": recent_traces(root)})
            else:
                self._json(404, {"error": "Not found"})

        def do_POST(self):
            if not self._allowed_host():
                self._json(403, {"error": "Local access only"})
                return
            path = urlparse(self.path).path
            if path not in ("/api/search", "/api/compare", "/api/ask"):
                self._json(404, {"error": "Not found"})
                return
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._json(415, {"error": "Expected application/json"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 32768:
                    raise ValueError("Request body must be between 1 and 32768 bytes")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object")
                question = str(data.get("question", "")).strip()
                english_query = str(data.get("english_query", "")).strip() or None
                top_k = int(data.get("top_k", 10))
                strategy = str(data.get("strategy", "vector"))
                if path == "/api/ask" and not status(root, manifest)["deepseek_key_set"]:
                    raise RuntimeError("Set DEEPSEEK_API_KEY before starting the web server")
                model = self._model() if strategy in ("vector", "hybrid") or path == "/api/compare" else None
                if path == "/api/search":
                    result = {"strategy": strategy, "candidates": retrieve(
                        db_path, question, strategy, english_query, top_k, model)}
                elif path == "/api/compare":
                    result = {"strategies": compare(db_path, question, english_query or "", top_k, model)}
                else:
                    context_k = int(data.get("context_k", 3))
                    trace = answer(root, manifest, db_path, question, strategy, english_query,
                                   top_k, context_k, model)
                    result = {"trace": trace}
                self._json(200, result)
            except (ValueError, FileNotFoundError, RuntimeError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
            except Exception:
                traceback.print_exc()
                self._json(500, {"error": "Server error; see terminal for details"})

    return Handler


def main():
    cli = ArgumentParser(description="Local RAG learning UI")
    cli.add_argument("--port", type=int, default=8765)
    cli.add_argument("--scenario", type=Path, default=ROOT / "scenarios" / "crewai" / "manifest.json")
    args = cli.parse_args()
    if not 1024 <= args.port <= 65535:
        cli.error("port must be between 1024 and 65535")
    server = HTTPServer(("127.0.0.1", args.port), create_handler(ROOT, args.scenario))
    print(f"RAG Lab local UI: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
