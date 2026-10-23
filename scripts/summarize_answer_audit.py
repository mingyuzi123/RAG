"""Summarize manually reviewed answers; optionally bind labels to local traces."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.review import (CITATION_VERDICTS, POINT_VERDICTS, REFUSAL_VERDICTS,
                           score_review)  # noqa: E402
from raglab.service import recent_traces  # noqa: E402
from raglab.store import load_manifest  # noqa: E402


def summarize(manifest_path: Path, audit_path: Path, verify_local: bool = False) -> dict:
    manifest = load_manifest(manifest_path)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if (audit["scenario"], audit["source_commit"]) != (manifest["id"], manifest["upstream_commit"]):
        raise ValueError("audit source does not match scenario")
    questions = [json.loads(line) for line in (manifest_path.parent / "eval" / "questions.jsonl")
                 .read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {item["id"]: item for item in questions}
    reviews = audit["reviews"]
    if len(reviews) != len(questions) or {item["id"] for item in reviews} != set(by_id):
        raise ValueError("audit must cover every question once")
    if len({item["request_id"] for item in reviews}) != len(reviews):
        raise ValueError("audit request IDs must be unique")
    traces = ({trace["request_id"]: trace for trace in recent_traces(ROOT, 1000)}
              if verify_local else {})
    answerable = {"pass": 0, "fail": 0, "uncertain": 0}
    unanswerable = {"pass": 0, "fail": 0, "uncertain": 0}
    details = []
    for item in reviews:
        question = by_id[item["id"]]
        points = item["point_verdicts"]
        if len(points) != len(question["expected_points"]) or any(value not in POINT_VERDICTS for value in points):
            raise ValueError(f"{item['id']}: invalid point reviews")
        if item["citation_verdict"] not in CITATION_VERDICTS or item["refusal_verdict"] not in REFUSAL_VERDICTS:
            raise ValueError(f"{item['id']}: invalid citation or refusal review")
        verdict = score_review(question["answerability"], points,
                               item["citation_verdict"], item["refusal_verdict"])
        bucket = answerable if question["answerability"] == "answerable" else unanswerable
        bucket[verdict] += 1
        if verify_local:
            trace = traces.get(item["request_id"])
            if (trace is None or trace["status"] != "completed" or
                    trace["scenario"] != manifest["id"] or
                    trace["source_commit"] != manifest["upstream_commit"] or
                    trace["question"] != question["question"] or
                    trace["strategy"] != audit["strategy"] or
                    len(trace["selected_chunk_ids"]) != audit["context_k"]):
                raise ValueError(f"{item['id']}: local trace does not match audit")
        details.append({"id": item["id"], "verdict": verdict,
                        "citation_verdict": item["citation_verdict"],
                        "refusal_verdict": item["refusal_verdict"]})
    return {"scenario": manifest["id"], "source_commit": manifest["upstream_commit"],
            "strategy": audit["strategy"], "top_k": audit["top_k"],
            "context_k": audit["context_k"], "answerable": answerable,
            "unanswerable": unanswerable, "details": details,
            "verified_against_local_traces": verify_local}


def main() -> None:
    cli = ArgumentParser()
    cli.add_argument("--scenario", type=Path, required=True)
    cli.add_argument("--audit", type=Path, required=True)
    cli.add_argument("--verify-local", action="store_true")
    args = cli.parse_args()
    print(json.dumps(summarize(args.scenario, args.audit, args.verify_local),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
