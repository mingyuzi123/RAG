"""Small CLI for building, inspecting and querying a scenario index."""

from argparse import ArgumentParser, BooleanOptionalAction
from contextlib import closing
from importlib.util import find_spec
from pathlib import Path
import json
import sqlite3
import subprocess
import sys

from .runtime import resolve_keyword_query, resolve_runtime
from .service import CONTEXT_POLICIES, STRATEGIES, answer, record_failure, retrieve, retrieve_targeted_window, status
from .store import _check_source, build_index, index_path, load_manifest
from .vector import build_vectors


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = ROOT / "scenarios" / "crewai" / "manifest.json"


def parser() -> ArgumentParser:
    cli = ArgumentParser(prog="python -m raglab")
    cli.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    cli.add_argument("--max-chars", type=int, default=1800,
                     help="Maximum target characters per chunk; a single code block may exceed it")
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check local dependencies, pinned source, indexes and key presence")
    commands.add_parser("index", help="Build a versioned keyword index")
    commands.add_parser("vector-index", help="Build optional multilingual E5 embeddings")
    for name in ("search", "ask"):
        sub = commands.add_parser(name)
        sub.add_argument("question")
        sub.add_argument("--search-query", help="Explicit English query for the keyword baseline")
        sub.add_argument("--strategy", choices=STRATEGIES, help="Override the scenario's retrieval strategy")
        sub.add_argument("--subquery", action="append", help="Repeat 2-4 times for decomposed retrieval")
        sub.add_argument("--top-k", type=int)
        sub.add_argument("--context-k", type=int)
        sub.add_argument("--context-policy", choices=CONTEXT_POLICIES)
        sub.add_argument("--auto-rewrite", action=BooleanOptionalAction,
                         help="Allow automatic English keyword rewriting (uses DeepSeek API)")
        if name == "ask":
            sub.add_argument("--model", help="DeepSeek model ID (default: DEEPSEEK_MODEL or deepseek-flash)")
    return cli


def main() -> None:
    args = parser().parse_args()
    if args.max_chars < 200:
        raise SystemExit("--max-chars must be at least 200")
    manifest = load_manifest(args.scenario)
    db_path = index_path(ROOT, manifest, args.max_chars)
    if args.command == "doctor":
        try:
            source = _check_source(ROOT, manifest)
            missing = [item for item in manifest["files"] if not (source / item).is_file()]
            source_check = {"ready": bool(manifest["files"]) and not missing, "missing": missing}
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            source_check = {"ready": False, "error": str(exc)}
        with closing(sqlite3.connect(":memory:")) as db:
            try:
                db.execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
                fts5 = True
            except sqlite3.OperationalError:
                fts5 = False
        print(json.dumps({"python": sys.version.split()[0], "fts5": fts5, "source": source_check,
                          "pdf_dependency": find_spec("pypdf") is not None,
                          "vector_dependency": find_spec("sentence_transformers") is not None,
                          "retrieval": resolve_runtime(manifest), **status(ROOT, manifest, args.max_chars)},
                         ensure_ascii=False, indent=2))
        return
    if args.command == "index":
        db_path, count = build_index(ROOT, manifest, args.max_chars)
        print(json.dumps({"index": str(db_path), "scenario": manifest["id"],
                          "source_commit": manifest["upstream_commit"], "chunks": count}, ensure_ascii=False, indent=2))
        return
    if args.command == "vector-index":
        if not db_path.is_file():
            raise SystemExit("Index missing. First run: python -m raglab index")
        path, count = build_vectors(db_path)
        print(json.dumps({"index": str(path), "scenario": manifest["id"],
                          "chunks": count}, ensure_ascii=False, indent=2))
        return
    stage, strategy = "input", "unknown"
    try:
        settings = resolve_runtime(manifest, strategy=args.strategy, top_k=args.top_k,
                                   context_k=args.context_k, context_policy=args.context_policy,
                                   auto_rewrite=args.auto_rewrite)
        strategy, policy = settings["strategy"], settings["context_policy"]
        top_k, context_k = settings["top_k"], settings["context_k"]
        if not args.question.strip():
            raise ValueError("Question cannot be empty")
        stage = "retrieval"
        if not db_path.is_file():
            raise FileNotFoundError("Index missing. First run: python -m raglab index")
        stage = "rewrite"
        english_query, metadata = resolve_keyword_query(args.question, settings, args.search_query)
        stage = "retrieval"
        if args.command == "search":
            if policy == "targeted_window":
                _, _, candidates, _ = retrieve_targeted_window(ROOT, manifest, db_path, args.question,
                    english_query, top_k, context_k, max_chars=args.max_chars)
            else:
                candidates = retrieve(db_path, args.question, strategy, english_query,
                                      top_k, subqueries=args.subquery)
            result = {"query": args.question, "search_query": english_query or args.question,
                      "strategy": strategy, "retrieval": settings, "query_metadata": metadata,
                      "selected_chunk_ids": [item["id"] for item in candidates[:context_k]],
                      "candidates": [{**item, "text": item["text"][:350]} for item in candidates]}
        else:
            trace = answer(ROOT, manifest, db_path, args.question, strategy, english_query,
                           top_k, context_k, generation_model=args.model,
                           subqueries=args.subquery, context_policy=policy,
                           max_chars=args.max_chars, query_metadata=metadata)
            result = {"request_id": trace["request_id"], "retrieval": settings,
                      "query_metadata": metadata, **trace["result"]}
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        request_id = record_failure(ROOT, manifest, stage, args.question, strategy, exc)
        raise SystemExit(f"{exc} (request {request_id})") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
