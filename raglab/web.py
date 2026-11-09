"""Local-only learning UI, backed by the same workflow as the CLI."""

from argparse import ArgumentParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json
import traceback

from .decomposition import decompose_question
from .evaluation_view import load_dashboard
from .local_sources import SCENARIO_ID, ensure_local_scenario, import_document, local_manifest_path, local_source_file
from .review import latest_reviews, save_review
from .query_rewrite import rewrite_query
from .runtime import resolve_keyword_query, resolve_runtime
from .service import answer, compare, recent_traces, record_failure, retrieve, retrieve_targeted_window, status
from .store import build_index, index_path, load_manifest
from .vector import build_vectors, load_model


ROOT = Path(__file__).resolve().parents[1]
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/styles.css": ("styles.css", "text/css; charset=utf-8")}


def scenario_history(root: Path, scenario_id: str) -> dict:
    traces = [trace for trace in recent_traces(root, 1000)
              if trace.get("scenario") == scenario_id][:20]
    request_ids = {trace["request_id"] for trace in traces}
    reviews = {request_id: review for request_id, review in latest_reviews(root).items()
               if request_id in request_ids}
    return {"traces": traces, "reviews": reviews}


def scenario_context(root: Path, manifest_path: Path) -> dict:
    manifest = load_manifest(manifest_path)
    db_path = index_path(root, manifest, 1800)
    ui_path = manifest_path.parent / "ui.json"
    ui = json.loads(ui_path.read_text(encoding="utf-8")) if ui_path.is_file() else {"title": manifest["id"]}
    eval_dir = manifest_path.parent / "eval"
    questions_path = eval_dir / "questions.jsonl"
    query_path = eval_dir / "queries_en.json"
    subquery_path = eval_dir / "subqueries_zh.json"
    questions = ([json.loads(line) for line in questions_path.read_text(encoding="utf-8").splitlines()]
                 if questions_path.is_file() else [])
    english = json.loads(query_path.read_text(encoding="utf-8")) if query_path.is_file() else {}
    subquery_examples = json.loads(subquery_path.read_text(encoding="utf-8")) if subquery_path.is_file() else {}
    examples = [{"id": item["id"], "question": item["question"],
                 "english_query": english.get(item["id"], ""),
                 "subqueries": subquery_examples.get(item["id"], []),
                 "answerability": item.get("answerability"),
                 "expected_points": item.get("expected_points", []),
                 "evidence": item.get("evidence", [])}
                for item in questions]
    source_root = root / manifest["local_checkout"]
    documents = [{"path": path, "name": manifest.get("display_names", {}).get(path, Path(path).name),
        "url": manifest["source_url_template"].format(
        commit=manifest["upstream_commit"], path=path),
        "available": (source_root / path).is_file(),
        "sparse_pages": manifest.get("pdf_sparse_pages", {}).get(path, [])} for path in manifest["files"]]
    return {"manifest": manifest, "db_path": db_path, "ui": ui, "retrieval": resolve_runtime(manifest),
            "examples": examples, "documents": documents}


def create_handler(root: Path, manifest_path: Path):
    paths = [manifest_path, *(root / "scenarios").glob("*/manifest.json"),
             ensure_local_scenario(root)]
    contexts = {}
    for path in paths:
        context = scenario_context(root, path)
        contexts[context["manifest"]["id"]] = context
    default_id = load_manifest(manifest_path)["id"]
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

        def _context(self):
            query = parse_qs(urlparse(self.path).query)
            scenario_id = query.get("scenario", [default_id])[0]
            if scenario_id not in contexts:
                raise ValueError("Unknown scenario")
            return contexts[scenario_id]

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
            elif path == "/api/source":
                try:
                    if self._context()["manifest"]["id"] != SCENARIO_ID:
                        raise ValueError("Source is not a local scenario")
                    relative = parse_qs(urlparse(self.path).query).get("path", [""])[0]
                    body = local_source_file(root, relative).read_bytes()
                    mime = "application/pdf" if relative.endswith(".pdf") else "text/plain; charset=utf-8"
                    self._headers(200, mime, len(body))
                    self.wfile.write(body)
                except (ValueError, FileNotFoundError) as exc:
                    self._json(404, {"error": str(exc)})
            elif path == "/api/config":
                try:
                    context = self._context()
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                manifest = context["manifest"]
                scenarios = [{"id": item["manifest"]["id"], "name": item["manifest"]["name"],
                              "version": item["manifest"].get("docs_version", "")}
                             for item in contexts.values()]
                self._json(200, {"scenario_id": manifest["id"], "scenarios": scenarios,
                                 "documents": context["documents"], "ui": context["ui"],
                                 "retrieval": context["retrieval"],
                                 "examples": context["examples"], "status": status(root, manifest)})
            elif path == "/api/traces":
                try:
                    self._json(200, scenario_history(root, self._context()["manifest"]["id"]))
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
            elif path == "/api/evaluations":
                try:
                    context = self._context()
                    self._json(200, load_dashboard(root, context["manifest"], context["ui"]))
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
            else:
                self._json(404, {"error": "Not found"})

        def do_POST(self):
            if not self._allowed_host():
                self._json(403, {"error": "Local access only"})
                return
            path = urlparse(self.path).path
            if path not in ("/api/search", "/api/compare", "/api/ask", "/api/decompose", "/api/rewrite", "/api/review", "/api/import"):
                self._json(404, {"error": "Not found"})
                return
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._json(415, {"error": "Expected application/json"})
                return
            manifest, question, strategy, stage = None, "", "unknown", "input"
            try:
                context = self._context()
                manifest, db_path, examples = (context[key] for key in ("manifest", "db_path", "examples"))
                size = int(self.headers.get("Content-Length", "0"))
                limit = 12_000_000 if path == "/api/import" else 32768
                if not 0 < size <= limit:
                    raise ValueError("Request body exceeds allowed size")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object")
                if path == "/api/import":
                    if manifest["id"] != SCENARIO_ID:
                        raise ValueError("请先切换到『我的本地文档』场景")
                    updated = import_document(root, data.get("filename"), data.get("content"),
                                              data.get("replace") is True, data.get("pdf_base64"))
                    contexts[SCENARIO_ID] = scenario_context(root, local_manifest_path(root))
                    new_db, chunk_count = build_index(root, updated)
                    vector_error = None
                    try:
                        build_vectors(new_db, self._model())
                    except (RuntimeError, OSError, ValueError) as exc:
                        vector_error = str(exc)
                    active_path = next(path for path, name in updated["display_names"].items()
                                       if name == data.get("filename"))
                    self._json(200, {"scenario_id": SCENARIO_ID, "chunks": chunk_count,
                                     "status": status(root, updated), "vector_error": vector_error,
                                     "sparse_pages": updated.get("pdf_sparse_pages", {}).get(active_path, [])})
                    return
                if path == "/api/review":
                    review = save_review(root, manifest["id"], data.get("request_id"),
                                         recent_traces(root, 1000),
                                         examples, data.get("point_verdicts"),
                                         data.get("citation_verdict"), data.get("refusal_verdict"),
                                         data.get("note", ""))
                    self._json(200, {"review": review})
                    return
                question = data.get("question", "")
                if not isinstance(question, str) or not question.strip():
                    question = ""
                    raise ValueError("Question cannot be empty and must be a string")
                question = question.strip()
                if path == "/api/decompose":
                    stage = "rewrite"
                    if not status(root, manifest)["deepseek_key_set"]:
                        raise RuntimeError("Set DEEPSEEK_API_KEY before starting the web server")
                    self._json(200, decompose_question(question))
                    return
                if path == "/api/rewrite":
                    stage = "rewrite"
                    if not status(root, manifest)["deepseek_key_set"]:
                        raise RuntimeError("Set DEEPSEEK_API_KEY before rewriting a query")
                    self._json(200, rewrite_query(question))
                    return
                english_query = data.get("english_query")
                if english_query is not None and not isinstance(english_query, str):
                    raise ValueError("english_query must be a string")
                query_metadata = data.get("query_metadata")
                if query_metadata is not None and (not isinstance(query_metadata, dict)
                        or query_metadata.get("source") not in ("auto", "manual", "original_question")):
                    raise ValueError("Invalid query metadata")
                settings = resolve_runtime(
                    manifest, strategy="hybrid" if path == "/api/compare" else data.get("strategy"),
                    top_k=data.get("top_k"), context_k=data.get("context_k"),
                    context_policy="top_k" if path == "/api/compare" else data.get("context_policy"),
                    auto_rewrite=data.get("auto_rewrite"))
                top_k, context_k = settings["top_k"], settings["context_k"]
                strategy, context_policy = settings["strategy"], settings["context_policy"]
                subqueries = data.get("subqueries")
                if subqueries is not None and not isinstance(subqueries, list):
                    raise ValueError("subqueries must be a list")
                if path == "/api/ask" and not status(root, manifest)["deepseek_key_set"]:
                    stage = "generation"
                    raise RuntimeError("Set DEEPSEEK_API_KEY before starting the web server")
                stage = "rewrite"
                english_query, query_metadata = resolve_keyword_query(question, settings, english_query, query_metadata)
                stage = "retrieval"
                model = self._model() if strategy in ("vector", "hybrid", "decomposed") or path == "/api/compare" else None
                if path == "/api/search":
                    if context_policy == "targeted_window":
                        baseline, child, selected, window = retrieve_targeted_window(
                            root, manifest, db_path, question, english_query or "", top_k,
                            context_k, model)
                        result = {"strategy": "targeted_window", "candidates": selected,
                                  "baseline_candidates": baseline, "child_candidates": child,
                                  "window": window}
                    else:
                        result = {"strategy": strategy, "candidates": retrieve(
                            db_path, question, strategy, english_query, top_k, model, subqueries)}
                    result["selected_chunk_ids"] = [item["id"] for item in result["candidates"][:context_k]]
                elif path == "/api/compare":
                    result = {"strategies": compare(db_path, question, english_query or "", top_k, model)}
                else:
                    trace = answer(root, manifest, db_path, question, strategy, english_query,
                                   top_k, context_k, model, subqueries=subqueries,
                                   context_policy=context_policy, query_metadata=query_metadata)
                    result = {"trace": trace}
                self._json(200, {**result, "english_query": english_query, "query_metadata": query_metadata,
                                 "retrieval": settings})
            except (ValueError, FileNotFoundError, RuntimeError, json.JSONDecodeError) as exc:
                result = {"error": str(exc)}
                if manifest and path not in ("/api/import", "/api/review"):
                    result["request_id"] = record_failure(root, manifest, stage, question, strategy, exc)
                self._json(400, result)
            except Exception as exc:
                traceback.print_exc()
                result = {"error": "Server error; see terminal for details"}
                if manifest and path not in ("/api/import", "/api/review"):
                    result["request_id"] = record_failure(root, manifest, stage, question, strategy, exc)
                self._json(500, result)

    return Handler


def main():
    cli = ArgumentParser(description="Local RAG learning UI")
    cli.add_argument("--port", type=int, default=8765)
    cli.add_argument("--scenario", type=Path, default=ROOT / "scenarios" / "crewai" / "manifest.json")
    args = cli.parse_args()
    if not 1024 <= args.port <= 65535:
        cli.error("port must be between 1024 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), create_handler(ROOT, args.scenario))
    print(f"RAG Lab local UI: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
