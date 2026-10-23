"""Evaluate evidence retrieval against source headings, never chunk IDs."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.store import index_path, load_manifest, search  # noqa: E402
from raglab.hybrid import search_hybrid  # noqa: E402
from raglab.vector import MODEL_ID, MODEL_REVISION, VECTOR_VERSION, load_model, search_vectors  # noqa: E402


def anchors_found(question: dict, candidates: list[dict]) -> list[bool]:
    return [any(item["source_path"] == anchor["path"] and
                anchor["heading"] in item["heading_path"] for item in candidates)
            for anchor in question["evidence"]]


def evaluate(strategy: str, top_k: int, context_k: int, query_language: str,
             scenario: Path | None = None) -> dict:
    manifest_path = scenario or ROOT / "scenarios" / "crewai" / "manifest.json"
    manifest = load_manifest(manifest_path)
    db_path = index_path(ROOT, manifest, 1800)
    if not db_path.exists():
        raise FileNotFoundError("Run python -m raglab index first")
    eval_dir = manifest_path.parent / "eval"
    questions = [json.loads(line) for line in (eval_dir / "questions.jsonl").read_text(encoding="utf-8").splitlines()]
    english = json.loads((eval_dir / "queries_en.json").read_text(encoding="utf-8"))
    if set(english) != {question["id"] for question in questions}:
        raise ValueError("English query IDs do not match the evaluation set")
    model = load_model() if strategy in ("vector", "hybrid") else None
    details = []
    for question in questions:
        query = english[question["id"]] if query_language == "en" else question["question"]
        if strategy == "bm25":
            candidates = search(db_path, query, top_k)
        elif strategy == "vector":
            candidates = search_vectors(db_path, query, top_k, model)
        else:
            candidates = search_hybrid(db_path, query, english[question["id"]], top_k, model)
        if question["answerability"] == "unanswerable":
            details.append({"id": question["id"], "answerability": "unanswerable",
                            "query": query, "top_chunk_ids": [item["id"] for item in candidates],
                            "retrieval_ms": candidates[0]["retrieval_ms"] if candidates else None})
            continue
        found_top = anchors_found(question, candidates)
        found_context = anchors_found(question, candidates[:context_k])
        first_rank = next((rank for rank in range(1, len(candidates) + 1)
                           if any(anchors_found(question, candidates[:rank]))), None)
        details.append({"id": question["id"], "query": query,
                        "anchors": question["evidence"], "anchor_found_top": found_top,
                        "anchor_found_context": found_context,
                        "all_found_top": all(found_top), "all_found_context": all(found_context),
                        "first_relevant_rank": first_rank,
                        "top_chunk_ids": [item["id"] for item in candidates],
                        "retrieval_ms": candidates[0]["retrieval_ms"] if candidates else None})
    answerable = [item for item in details if item.get("answerability") != "unanswerable"]
    count = len(answerable)
    return {"scenario": manifest["id"], "source_commit": manifest["upstream_commit"],
            "strategy": strategy, "query_language": "English manual translation" if query_language == "en" else "Chinese original",
            "embedding_model": {"id": MODEL_ID, "revision": MODEL_REVISION,
                                "protocol": VECTOR_VERSION} if strategy != "bm25" else None,
            "top_k": top_k, "context_k": context_k, "answerable_questions": count,
            "unanswerable_questions_excluded": len(details) - count,
            "all_anchor_recall_at_k": sum(item["all_found_top"] for item in answerable) / count,
            "all_anchor_context_hit_at_k": sum(item["all_found_context"] for item in answerable) / count,
            "mrr_first_anchor_at_k": sum(1 / item["first_relevant_rank"] for item in answerable
                                         if item["first_relevant_rank"]) / count,
            "details": details}


def main() -> None:
    cli = ArgumentParser()
    cli.add_argument("--strategy", choices=("bm25", "vector", "hybrid"), required=True)
    cli.add_argument("--top-k", type=int, default=10)
    cli.add_argument("--context-k", type=int, default=3)
    cli.add_argument("--query-language", choices=("en", "zh"),
                     help="Defaults to en for BM25 and zh for vector")
    cli.add_argument("--scenario", type=Path, default=ROOT / "scenarios" / "crewai" / "manifest.json")
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    if not 1 <= args.context_k <= args.top_k:
        cli.error("require 1 <= --context-k <= --top-k")
    language = args.query_language or ("en" if args.strategy == "bm25" else "zh")
    if args.strategy == "bm25" and language == "zh":
        cli.error("BM25 baseline requires the manually translated English queries")
    report = evaluate(args.strategy, args.top_k, args.context_k, language, args.scenario)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "details"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
