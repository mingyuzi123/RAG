"""Compare two-intent retrieval with the current hybrid strategy on compare questions."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.service import retrieve  # noqa: E402
from raglab.store import index_path, load_manifest  # noqa: E402
from raglab.vector import MODEL_ID, MODEL_REVISION, load_model  # noqa: E402
from scripts.evaluate_retrieval import anchors_found  # noqa: E402


def evaluate(top_k: int = 10, context_k: int = 3) -> dict:
    manifest = load_manifest(ROOT / "scenarios" / "crewai" / "manifest.json")
    db_path = index_path(ROOT, manifest, 1800)
    eval_dir = ROOT / "scenarios" / "crewai" / "eval"
    questions = [json.loads(line) for line in (eval_dir / "questions.jsonl").read_text(encoding="utf-8").splitlines()]
    comparisons = [item for item in questions if item["type"] == "compare"]
    english = json.loads((eval_dir / "queries_en.json").read_text(encoding="utf-8"))
    subqueries = json.loads((eval_dir / "subqueries_zh.json").read_text(encoding="utf-8"))
    if set(subqueries) != {item["id"] for item in comparisons}:
        raise ValueError("Subquery IDs must match all comparison questions")
    model = load_model()
    details = []
    for item in comparisons:
        variants = {}
        for strategy in ("hybrid", "decomposed"):
            candidates = retrieve(db_path, item["question"], strategy,
                                  english[item["id"]] if strategy == "hybrid" else None,
                                  top_k, model, subqueries[item["id"]] if strategy == "decomposed" else None)
            found_top = anchors_found(item, candidates)
            found_context = anchors_found(item, candidates[:context_k])
            variants[strategy] = {
                "all_found_top": all(found_top), "all_found_context": all(found_context),
                "anchor_found_top": found_top, "anchor_found_context": found_context,
                "top_chunk_ids": [candidate["id"] for candidate in candidates],
                "top_headings": [candidate["heading_path"][-1] for candidate in candidates],
                "retrieval_ms": candidates[0]["retrieval_ms"] if candidates else None,
            }
        details.append({"id": item["id"], "question": item["question"],
                        "subqueries": subqueries[item["id"]], "anchors": item["evidence"],
                        "variants": variants})
    summary = {strategy: {
        "all_anchor_recall_at_k": sum(row["variants"][strategy]["all_found_top"] for row in details) / len(details),
        "all_anchor_context_hit_at_k": sum(row["variants"][strategy]["all_found_context"] for row in details) / len(details),
    } for strategy in ("hybrid", "decomposed")}
    return {"scenario": manifest["id"], "source_commit": manifest["upstream_commit"],
            "index": str(db_path.relative_to(ROOT)), "embedding_model": f"{MODEL_ID}@{MODEL_REVISION}",
            "query_source": "six manually written comparison subquery pairs",
            "evaluated_questions": len(details), "top_k": top_k, "context_k": context_k,
            "summary": summary, "details": details}


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "crewai-decomposed-compare.json")
    args = parser.parse_args()
    result = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    for row in result["details"]:
        print(row["id"], *(f"{strategy}: top={row['variants'][strategy]['all_found_top']}, "
                           f"context={row['variants'][strategy]['all_found_context']}"
                           for strategy in ("hybrid", "decomposed")))


if __name__ == "__main__":
    main()
