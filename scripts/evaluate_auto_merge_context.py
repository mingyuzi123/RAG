"""Try LlamaIndex-style conditional child-to-parent merging under a fixed budget."""

from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.store import index_path, load_manifest  # noqa: E402
from scripts.evaluate_parent_context import parent_of, rows, sections, spans  # noqa: E402


def select(child_ids: list[str], children: dict, parents: dict, parent_ids: dict,
           parent_sizes: Counter, budget: int, k: int = 3) -> list[dict]:
    hits = Counter(parent_ids[chunk_id] for chunk_id in child_ids)
    chosen = []
    chosen_ids = set()
    merged_parents = set()
    used = 0
    for chunk_id in child_ids:
        parent_id = parent_ids[chunk_id]
        if parent_id in merged_parents:
            continue
        # AutoMergingRetriever uses a child-hit ratio to decide when a parent
        # carries more coherent context. Require at least two child hits too.
        merge = hits[parent_id] >= 2 and hits[parent_id] / parent_sizes[parent_id] > 0.5
        candidate = parents[parent_id] if merge else children[chunk_id]
        if merge and used + len(candidate["text"]) > budget:
            candidate = children[chunk_id]
            merge = False
        if candidate["id"] in chosen_ids or used + len(candidate["text"]) > budget:
            continue
        chosen.append({**candidate, "kind": "parent" if merge else "child"})
        chosen_ids.add(candidate["id"])
        used += len(candidate["text"])
        if merge:
            merged_parents.add(parent_id)
        if len(chosen) == k:
            break
    return chosen


def evaluate(scenario: str, heldout: bool = False) -> dict:
    manifest = load_manifest(ROOT / "scenarios" / scenario / "manifest.json")
    parents = rows(index_path(ROOT, manifest, 1800))
    children = rows(index_path(ROOT, manifest, 1800, True))
    parent_ids = {chunk_id: parent_of(row, parents)["id"] for chunk_id, row in children.items()}
    parent_sizes = Counter(parent_ids.values())
    if heldout:
        report = json.loads((ROOT / "reports/crewai-parent-heldout.json").read_text(encoding="utf-8"))
        questions_path = ROOT / "scenarios/crewai/eval/heldout_compare.jsonl"
        child_field = "child_ids"
    else:
        report = json.loads((ROOT / "reports" / f"{scenario}-parent-context.json").read_text(encoding="utf-8"))
        child_report = json.loads((ROOT / "reports" / f"{scenario}-definition-hybrid.json").read_text(encoding="utf-8"))
        child_lookup = {row["id"]: row["top_chunk_ids"] for row in child_report["details"]}
        questions_path = ROOT / "scenarios" / scenario / "eval/questions.jsonl"
        child_field = None
    questions = {row["id"]: row for row in map(json.loads, questions_path.read_text(encoding="utf-8").splitlines())}
    gold_path = ROOT / "scenarios" / scenario / "eval/evidence_spans.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path.exists() else {}
    details = []
    for entry in report["details"]:
        qid = entry["id"]
        baseline = [parents[chunk_id] for chunk_id in entry["baseline_ids"]]
        budget = sum(len(row["text"]) for row in baseline)
        child_ids = entry[child_field] if child_field else child_lookup[qid]
        selected = select(child_ids, children, parents, parent_ids, parent_sizes, budget)
        details.append({"id": qid, "answerability": questions[qid]["answerability"],
            "selected": [{"id": row["id"], "kind": row["kind"], "source_path": row["source_path"],
                          "lines": [row["start_line"], row["end_line"]]} for row in selected],
            "baseline_ids": entry["baseline_ids"], "selected_chars": sum(len(row["text"]) for row in selected),
            "baseline_chars": budget,
            "baseline_sections": sections(questions[qid]["evidence"], baseline),
            "selected_sections": sections(questions[qid]["evidence"], selected),
            "baseline_spans": spans(gold.get(qid, []), baseline),
            "selected_spans": spans(gold.get(qid, []), selected)})
    answerable = [row for row in details if row["answerability"] == "answerable"]
    return {"scenario": scenario, "heldout": heldout, "method": "conditional-auto-merge-v1",
        "rule": "merge if >=2 retrieved children and ratio > 0.5; otherwise child; baseline character budget",
        "questions": len(details), "baseline_sections": sum(row["baseline_sections"] for row in answerable),
        "selected_sections": sum(row["selected_sections"] for row in answerable),
        "changed": [row["id"] for row in details if row["baseline_ids"] != [x["id"] for x in row["selected"]]],
        "details": details}


if __name__ == "__main__":
    for name, hold in (("pydantic", False), ("crewai", False), ("crewai", True)):
        result = evaluate(name, hold)
        suffix = "-heldout" if hold else ""
        path = ROOT / "reports" / f"{name}-auto-merge{suffix}.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(name, hold, result["baseline_sections"], result["selected_sections"], result["changed"])
