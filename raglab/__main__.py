"""Small CLI for building, inspecting and querying a scenario index."""

from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import time

from .generation import generate_answer
from .hybrid import search_hybrid
from .store import build_index, index_path, load_manifest, search
from .vector import build_vectors, search_vectors


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = ROOT / "scenarios" / "crewai" / "manifest.json"


def parser() -> ArgumentParser:
    cli = ArgumentParser(prog="python -m raglab")
    cli.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    cli.add_argument("--max-chars", type=int, default=1800,
                     help="Maximum target characters per chunk; a single code block may exceed it")
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("index", help="Build a versioned keyword index")
    commands.add_parser("vector-index", help="Build optional multilingual E5 embeddings")
    for name in ("search", "ask"):
        sub = commands.add_parser(name)
        sub.add_argument("question")
        sub.add_argument("--search-query", help="Explicit English query for the keyword baseline")
        sub.add_argument("--strategy", choices=("bm25", "vector", "hybrid"), default="bm25")
        sub.add_argument("--top-k", type=int, default=5)
        if name == "ask":
            sub.add_argument("--context-k", type=int, default=3)
            sub.add_argument("--model", help="DeepSeek model ID (default: DEEPSEEK_MODEL or deepseek-flash)")
    return cli


def main() -> None:
    args = parser().parse_args()
    if args.max_chars < 200:
        raise SystemExit("--max-chars must be at least 200")
    if args.command in ("search", "ask") and args.top_k < 1:
        raise SystemExit("--top-k must be positive")
    if args.command == "ask" and not 1 <= args.context_k <= args.top_k:
        raise SystemExit("--context-k must be between 1 and --top-k")
    manifest = load_manifest(args.scenario)
    db_path = index_path(ROOT, manifest, args.max_chars)
    if args.command == "index":
        db_path, count = build_index(ROOT, manifest, args.max_chars)
        print(json.dumps({"index": str(db_path), "scenario": manifest["id"],
                          "source_commit": manifest["upstream_commit"], "chunks": count}, ensure_ascii=False, indent=2))
        return
    if not db_path.is_file():
        raise SystemExit("Index missing. First run: python -m raglab index")
    if args.command == "vector-index":
        path, count = build_vectors(db_path)
        print(json.dumps({"index": str(path), "scenario": manifest["id"],
                          "chunks": count}, ensure_ascii=False, indent=2))
        return
    query = args.search_query or args.question
    if args.strategy == "hybrid" and not args.search_query:
        raise SystemExit("Hybrid retrieval requires --search-query with an English keyword query")
    try:
        if args.strategy == "bm25":
            candidates = search(db_path, query, args.top_k)
        elif args.strategy == "vector":
            candidates = search_vectors(db_path, args.question, args.top_k)
        else:
            candidates = search_hybrid(db_path, args.question, query, args.top_k)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.command == "search":
        print(json.dumps({"query": args.question, "search_query": query if args.strategy != "vector" else args.question,
                          "strategy": args.strategy,
                          "candidates": [{**item, "text": item["text"][:350]} for item in candidates]},
                         ensure_ascii=False, indent=2))
        return

    selected = candidates[:args.context_k]
    started = time.perf_counter()
    result = generate_answer(args.question, selected, args.model)
    result["sources"] = [
        {"number": number, "url": item["source_url"], "heading_path": item["heading_path"]}
        for number, item in enumerate(selected, 1)
    ]
    trace = {
        "request_id": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario": manifest["id"], "source_commit": manifest["upstream_commit"],
        "index": str(db_path.relative_to(ROOT)), "strategy": args.strategy,
        "question": args.question, "search_query": query if args.strategy != "vector" else args.question,
        "candidates": candidates, "selected_chunk_ids": [item["id"] for item in selected],
        "result": result, "generation_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    log_path = ROOT / "logs" / "requests.jsonl"
    log_path.parent.mkdir(exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(json.dumps(trace, ensure_ascii=False) + "\n")
    print(json.dumps({"request_id": trace["request_id"], **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
