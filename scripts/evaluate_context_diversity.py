"""Replay fixed retrieval reports with an MMR-style context selector."""

from argparse import ArgumentParser
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.diversity import select_diverse  # noqa: E402
from raglab.store import index_path, load_manifest  # noqa: E402
from raglab.vector import MODEL_ID, MODEL_REVISION, VECTOR_VERSION, vector_path  # noqa: E402


def anchors_found(anchors: list[dict], candidates: list[dict]) -> list[bool]:
    return [any(item["source_path"] == anchor["path"] and
                anchor["heading"] in item["heading_path"] for item in candidates)
            for anchor in anchors]


def evaluate(report_path: Path, relevance_weight: float = 0.7,
             context_k: int = 3, variant: str = "hybrid") -> dict:
    import numpy as np

    source = report_path.read_bytes()
    report = json.loads(source)
    manifest = load_manifest(ROOT / "scenarios" / "crewai" / "manifest.json")
    db_path = index_path(ROOT, manifest, 1800)
    if report["scenario"] != manifest["id"] or report["source_commit"] != manifest["upstream_commit"]:
        raise ValueError("report and current scenario source version differ")
    if report["top_k"] < context_k:
        raise ValueError("context_k exceeds the saved candidate count")
    if "embedding_model" in report and isinstance(report["embedding_model"], dict):
        expected = {"id": MODEL_ID, "revision": MODEL_REVISION, "protocol": VECTOR_VERSION}
        if report["embedding_model"] != expected:
            raise ValueError("report and current vector model differ")
    if isinstance(report.get("embedding_model"), str) and report["embedding_model"] != f"{MODEL_ID}@{MODEL_REVISION}":
        raise ValueError("report and current vector model differ")
    if report.get("index") and report["index"].replace("\\", "/") != db_path.relative_to(ROOT).as_posix():
        raise ValueError("report and current keyword index differ")
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        rows = {row["id"]: row for row in db.execute(
            "SELECT id, source_path, heading_path, text FROM chunks")}
    with np.load(vector_path(db_path), allow_pickle=False) as saved:
        vectors = {str(chunk_id): vector for chunk_id, vector in
                   zip(saved["ids"], saved["vectors"])}

    details = []
    for question in report["details"]:
        if question.get("answerability") == "unanswerable":
            continue
        ids = question.get("top_chunk_ids")
        if ids is None:
            ids = question["variants"][variant]["top_chunk_ids"]
        candidates = [{"id": chunk_id, "source_path": rows[chunk_id]["source_path"],
                       "heading_path": json.loads(rows[chunk_id]["heading_path"]),
                       "text": rows[chunk_id]["text"]} for chunk_id in ids]
        baseline = candidates[:context_k]
        budget = sum(len(item["text"]) for item in baseline)
        selected = select_diverse(candidates, vectors, context_k, relevance_weight, budget)
        baseline_hits = anchors_found(question["anchors"], baseline)
        selected_hits = anchors_found(question["anchors"], selected)
        details.append({
            "id": question["id"], "anchors": question["anchors"],
            "baseline_all_found": all(baseline_hits), "diverse_all_found": all(selected_hits),
            "baseline_anchor_found": baseline_hits, "diverse_anchor_found": selected_hits,
            "candidate_ids": ids, "baseline_context_ids": [item["id"] for item in baseline],
            "diverse_context_ids": [item["id"] for item in selected],
            "baseline_headings": [item["heading_path"][-1] for item in baseline],
            "diverse_headings": [item["heading_path"][-1] for item in selected],
            "char_budget": budget, "diverse_chars": sum(len(item["text"]) for item in selected),
        })
    return {
        "scenario": manifest["id"], "source_commit": manifest["upstream_commit"],
        "index": db_path.relative_to(ROOT).as_posix(),
        "source_report": report_path.relative_to(ROOT).as_posix(),
        "source_report_sha256": sha256(source).hexdigest(),
        "vector_model": f"{MODEL_ID}@{MODEL_REVISION}", "vector_protocol": VECTOR_VERSION,
        "method": "greedy-rank-cosine-diversity-v1", "relevance_weight": relevance_weight,
        "candidate_top_k": report["top_k"], "context_k": context_k,
        "budget": "same character count as the original top-k context, per question",
        "questions": len(details),
        "baseline_all_found": sum(item["baseline_all_found"] for item in details),
        "diverse_all_found": sum(item["diverse_all_found"] for item in details),
        "gained": [item["id"] for item in details if item["diverse_all_found"] and not item["baseline_all_found"]],
        "lost": [item["id"] for item in details if item["baseline_all_found"] and not item["diverse_all_found"]],
        "details": details,
    }


def main():
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("--report", type=Path,
                     default=ROOT / "reports" / "crewai-table-v3-hybrid-zh.json")
    cli.add_argument("--output", type=Path,
                     default=ROOT / "reports" / "crewai-diverse-context.json")
    cli.add_argument("--weight", type=float, default=0.7)
    cli.add_argument("--context-k", type=int, default=3)
    args = cli.parse_args()
    result = evaluate(args.report.resolve(), args.weight, args.context_k)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "details"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
