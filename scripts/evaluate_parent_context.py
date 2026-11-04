"""Replay definition-child retrieval with original chunks as parent context."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.store import index_path, load_manifest  # noqa: E402


def rows(path: Path) -> dict[str, dict]:
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        result = [dict(row) for row in db.execute("SELECT * FROM chunks")]
    return {row["id"]: {**row, "heading_path": json.loads(row["heading_path"])} for row in result}


def parent_of(child: dict, parents: dict[str, dict]) -> dict:
    same = [row for row in parents.values() if row["source_path"] == child["source_path"]
            and row["heading_path"] == child["heading_path"]]
    containing = [row for row in same if row["start_line"] <= child["start_line"]
                  and row["end_line"] >= child["end_line"]]
    if len(containing) == 1:
        return containing[0]
    # Chunks may straddle an original boundary; retain the largest line overlap.
    candidates = containing or same
    if not candidates:
        raise ValueError(f"No parent in source section: {child['source_path']} {child['heading_path']}")
    return max(candidates, key=lambda row: (max(0, min(row["end_line"], child["end_line"])
        - max(row["start_line"], child["start_line"]) + 1), -len(row["text"])))


def sections(anchors: list[dict], selected: list[dict]) -> bool:
    return all(any(row["source_path"] == anchor["path"] and anchor["heading"] in row["heading_path"]
                   for row in selected) for anchor in anchors)


def spans(gold: list[dict], selected: list[dict]) -> list[dict]:
    return [{"point": item["point"], "covered": any(row["source_path"] == item["path"]
            and row["start_line"] <= item["start_line"] and row["end_line"] >= item["end_line"]
            for row in selected)} for item in gold]


def evaluate(scenario: str) -> dict:
    manifest = load_manifest(ROOT / "scenarios" / scenario / "manifest.json")
    old_name = "pydantic-hybrid-zh.json" if scenario == "pydantic" else "crewai-table-v3-hybrid-zh.json"
    old = json.loads((ROOT / "reports" / old_name).read_text(encoding="utf-8"))
    new = json.loads((ROOT / "reports" / f"{scenario}-definition-hybrid.json").read_text(encoding="utf-8"))
    if old["source_commit"] != new["source_commit"] or old["source_commit"] != manifest["upstream_commit"]:
        raise ValueError("Source versions differ")
    parents = rows(index_path(ROOT, manifest, 1800))
    children = rows(ROOT / new["index"])
    questions = {row["id"]: row for row in map(json.loads,
        (ROOT / "scenarios" / scenario / "eval/questions.jsonl").read_text(encoding="utf-8").splitlines())}
    span_path = ROOT / "scenarios" / scenario / "eval/evidence_spans.json"
    gold = json.loads(span_path.read_text(encoding="utf-8")) if span_path.exists() else {}
    old_details = {row["id"]: row for row in old["details"]}
    details = []
    for result in new["details"]:
        qid = result["id"]
        baseline = [parents[chunk_id] for chunk_id in old_details[qid]["top_chunk_ids"][:3]]
        seen = set()
        mapped = []
        for child_id in result["top_chunk_ids"]:
            parent = parent_of(children[child_id], parents)
            if parent["id"] not in seen:
                mapped.append(parent)
                seen.add(parent["id"])
        full = mapped[:3]
        budget = sum(len(row["text"]) for row in baseline)
        equal = []
        used = 0
        for row in mapped:
            if len(equal) == 3:
                break
            if used + len(row["text"]) <= budget:
                equal.append(row)
                used += len(row["text"])
        question = questions[qid]
        details.append({"id": qid, "answerability": question["answerability"],
            "baseline_ids": [row["id"] for row in baseline],
            "parent_ids": [row["id"] for row in full], "equal_budget_ids": [row["id"] for row in equal],
            "baseline_lines": [[row["source_path"], row["start_line"], row["end_line"]] for row in baseline],
            "parent_lines": [[row["source_path"], row["start_line"], row["end_line"]] for row in full],
            "equal_budget_lines": [[row["source_path"], row["start_line"], row["end_line"]] for row in equal],
            "baseline_chars": budget, "parent_chars": sum(len(row["text"]) for row in full),
            "equal_budget_chars": used,
            "sections": {"baseline": sections(question["evidence"], baseline),
                         "parent": sections(question["evidence"], full),
                         "equal_budget": sections(question["evidence"], equal)},
            "spans": {"baseline": spans(gold.get(qid, []), baseline),
                      "parent": spans(gold.get(qid, []), full),
                      "equal_budget": spans(gold.get(qid, []), equal)}})
    answerable = [row for row in details if row["answerability"] == "answerable"]
    return {"scenario": scenario, "method": "definition-child-to-original-parent",
        "source_commit": new["source_commit"], "baseline_report": old_name,
        "child_report": f"{scenario}-definition-hybrid.json",
        "parent_index": index_path(ROOT, manifest, 1800).relative_to(ROOT).as_posix(),
        "answerable_count": len(answerable),
        "section_context": {key: sum(row["sections"][key] for row in answerable)
                            for key in ("baseline", "parent", "equal_budget")},
        "details": details}


if __name__ == "__main__":
    for name in ("pydantic", "crewai"):
        result = evaluate(name)
        output = ROOT / "reports" / f"{name}-parent-context.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(name, result["section_context"], output.relative_to(ROOT))
