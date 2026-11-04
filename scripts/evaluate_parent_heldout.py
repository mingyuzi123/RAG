"""Holdout comparison for definition-child/original-parent retrieval."""

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.hybrid import search_hybrid  # noqa: E402
from raglab.store import index_path, load_manifest  # noqa: E402
from raglab.vector import load_model  # noqa: E402
from scripts.evaluate_parent_context import parent_of, rows, sections  # noqa: E402


def main() -> None:
    manifest = load_manifest(ROOT / "scenarios/crewai/manifest.json")
    baseline_path = index_path(ROOT, manifest, 1800)
    child_path = index_path(ROOT, manifest, 1800, definition_items=True)
    parents, children = rows(baseline_path), rows(child_path)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    model = load_model()
    questions = list(map(json.loads,
        (ROOT / "scenarios/crewai/eval/heldout_compare.jsonl").read_text(encoding="utf-8").splitlines()))
    details = []
    for question in questions:
        old_hits = search_hybrid(baseline_path, question["question"], question["english_query"], 10, model)
        child_hits = search_hybrid(child_path, question["question"], question["english_query"], 10, model)
        baseline = [parents[hit["id"]] for hit in old_hits[:3]]
        mapped = []
        seen = set()
        for hit in child_hits:
            parent = parent_of(children[hit["id"]], parents)
            if parent["id"] not in seen:
                mapped.append(parent)
                seen.add(parent["id"])
        selected = mapped[:3]
        details.append({"id": question["id"], "question": question["question"],
            "expected_points": question["expected_points"], "baseline_ids": [row["id"] for row in baseline],
            "parent_ids": [row["id"] for row in selected],
            "baseline_lines": [[row["source_path"], row["start_line"], row["end_line"]] for row in baseline],
            "parent_lines": [[row["source_path"], row["start_line"], row["end_line"]] for row in selected],
            "baseline_chars": sum(len(row["text"]) for row in baseline),
            "parent_chars": sum(len(row["text"]) for row in selected),
            "baseline_sections": sections(question["evidence"], baseline),
            "parent_sections": sections(question["evidence"], selected)})
    output = {"source_commit": manifest["upstream_commit"], "method": "definition-child-to-original-parent",
        "questions": len(details), "baseline_sections": sum(row["baseline_sections"] for row in details),
        "parent_sections": sum(row["parent_sections"] for row in details), "details": details}
    path = ROOT / "reports/crewai-parent-heldout.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output["baseline_sections"], output["parent_sections"],
          "changed", [row["id"] for row in details if row["baseline_ids"] != row["parent_ids"]])


if __name__ == "__main__":
    main()
