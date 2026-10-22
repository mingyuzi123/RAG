"""Small CLI for building, inspecting and querying a scenario index."""

from argparse import ArgumentParser
from pathlib import Path
import json

from .service import answer, retrieve
from .store import build_index, index_path, load_manifest
from .vector import build_vectors


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
        sub.add_argument("--strategy", choices=("bm25", "vector", "hybrid", "decomposed"), default="bm25")
        sub.add_argument("--subquery", action="append", help="Repeat 2-4 times for decomposed retrieval")
        sub.add_argument("--top-k", type=int, default=5)
        if name == "ask":
            sub.add_argument("--context-k", type=int, default=3)
            sub.add_argument("--model", help="DeepSeek model ID (default: DEEPSEEK_MODEL or deepseek-flash)")
    return cli


def main() -> None:
    args = parser().parse_args()
    if args.max_chars < 200:
        raise SystemExit("--max-chars must be at least 200")
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
    if args.command == "search":
        try:
            candidates = retrieve(db_path, args.question, args.strategy, args.search_query,
                                  args.top_k, subqueries=args.subquery)
        except (ValueError, FileNotFoundError) as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps({"query": args.question, "search_query": (args.search_query or args.question) if args.strategy != "vector" else args.question,
                          "strategy": args.strategy,
                          "candidates": [{**item, "text": item["text"][:350]} for item in candidates]},
                         ensure_ascii=False, indent=2))
        return

    try:
        trace = answer(ROOT, manifest, db_path, args.question, args.strategy,
                       args.search_query, args.top_k, args.context_k, generation_model=args.model,
                       subqueries=args.subquery)
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"request_id": trace["request_id"], **trace["result"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
