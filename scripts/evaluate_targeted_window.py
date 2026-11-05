"""Add one query-relevant preceding parent window to conditional auto-merge context."""

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.store import index_path, load_manifest  # noqa: E402
from scripts.evaluate_parent_context import parent_of, rows, sections, spans  # noqa: E402

STOP = {"what", "when", "where", "which", "with", "from", "this", "that", "into", "should",
        "between", "using", "versus", "difference", "about", "does", "default", "model",
        "process", "task", "agent", "field", "flow", "crewai", "pydantic"}


def terms(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z][a-z0-9_]*", value.casefold())
            if len(word) >= 4 and word not in STOP}


def neighbor_options(selected: list[dict], english_query: str, parents: dict,
                     parent_of_child: dict[str, str]) -> list[tuple[int, dict, str]]:
    query_terms = terms(english_query)
    existing_text_terms = set().union(*(terms(row["text"]) for row in selected))
    existing_heading_terms = set().union(*(terms(" ".join(row["heading_path"])) for row in selected))
    by_file = {}
    for row in parents.values():
        by_file.setdefault(row["source_path"], []).append(row)
    for group in by_file.values():
        group.sort(key=lambda row: row["start_line"])
    options = []
    for rank, anchor in enumerate(selected):
        parent_id = anchor["id"] if anchor["id"] in parents else parent_of_child[anchor["id"]]
        parent = parents[parent_id]
        group = by_file[parent["source_path"]]
        pos = next(i for i, row in enumerate(group) if row["id"] == parent_id)
        if pos == 0:
            continue
        preceding = group[pos - 1]
        if preceding["id"] in {row["id"] for row in selected}:
            continue
        if preceding["heading_path"] == parent["heading_path"]:
            novel = query_terms & terms(preceding["text"]) - existing_text_terms
            reason = "same-heading-new-query-term"
        elif preceding["heading_path"][:-1] == parent["heading_path"][:-1]:
            novel = query_terms & terms(preceding["heading_path"][-1]) - existing_heading_terms
            reason = "adjacent-sibling-heading-match"
        else:
            continue
        if novel:
            options.append((rank, preceding, f"{reason}:{','.join(sorted(novel))}"))
    return options


def evaluate(scenario: str, heldout: bool = False) -> dict:
    manifest = load_manifest(ROOT / "scenarios" / scenario / "manifest.json")
    parents = rows(index_path(ROOT, manifest, 1800))
    children = rows(index_path(ROOT, manifest, 1800, True))
    parent_of_child = {chunk_id: parent_of(row, parents)["id"] for chunk_id, row in children.items()}
    suffix = "-heldout" if heldout else ""
    source = json.loads((ROOT / "reports" / f"{scenario}-auto-merge{suffix}.json").read_text(encoding="utf-8"))
    question_file = "heldout_compare.jsonl" if heldout else "questions.jsonl"
    questions = {row["id"]: row for row in map(json.loads,
        (ROOT / "scenarios" / scenario / "eval" / question_file).read_text(encoding="utf-8").splitlines())}
    if heldout:
        english = {qid: row["english_query"] for qid, row in questions.items()}
    else:
        english = json.loads((ROOT / "scenarios" / scenario / "eval/queries_en.json").read_text(encoding="utf-8"))
    gold_path = ROOT / "scenarios" / scenario / "eval/evidence_spans.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path.exists() else {}
    details = []
    for entry in source["details"]:
        qid = entry["id"]
        original = [{**(parents if item["kind"] == "parent" else children)[item["id"]], "kind": item["kind"]}
                    for item in entry["selected"]]
        options = neighbor_options(original, english[qid], parents, parent_of_child)
        # One expansion max; prioritize the earliest retrieved anchor.
        option = min(options, key=lambda item: item[0]) if options else None
        ordered = list(original)
        if option:
            rank, neighbor, reason = option
            ordered.insert(rank + 1, {**neighbor, "kind": "neighbor_parent", "reason": reason})
        selected, used = [], 0
        for row in ordered:
            if len(selected) == 3:
                break
            if used + len(row["text"]) <= entry["baseline_chars"]:
                selected.append(row)
                used += len(row["text"])
        details.append({"id": qid, "answerability": questions[qid]["answerability"],
            "baseline_ids": entry["baseline_ids"],
            "selected": [{"id": row["id"], "kind": row["kind"], "source_path": row["source_path"],
                          "lines": [row["start_line"], row["end_line"]],
                          "reason": row.get("reason")} for row in selected],
            "added_neighbor": option[1]["id"] if option and any(row["id"] == option[1]["id"] for row in selected) else None,
            "baseline_chars": entry["baseline_chars"], "selected_chars": used,
            "baseline_sections": entry["baseline_sections"],
            "selected_sections": sections(questions[qid]["evidence"], selected),
            "baseline_spans": entry["baseline_spans"], "selected_spans": spans(gold.get(qid, []), selected)})
    answerable = [row for row in details if row["answerability"] == "answerable"]
    return {"scenario": scenario, "heldout": heldout, "method": "conditional-merge-plus-targeted-preceding-window-v1",
        "questions": len(details), "baseline_sections": sum(row["baseline_sections"] for row in answerable),
        "selected_sections": sum(row["selected_sections"] for row in answerable),
        "neighbor_added": [row["id"] for row in details if row["added_neighbor"]], "details": details}


if __name__ == "__main__":
    for name, hold in (("pydantic", False), ("crewai", False), ("crewai", True)):
        result = evaluate(name, hold)
        suffix = "-heldout" if hold else ""
        path = ROOT / "reports" / f"{name}-targeted-window{suffix}.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(name, hold, result["baseline_sections"], result["selected_sections"], result["neighbor_added"])
