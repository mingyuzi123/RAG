"""Compare baseline and definition-item retrieval at section and source-span levels."""

from contextlib import closing
from pathlib import Path
import json
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.store import index_path, load_manifest  # noqa: E402
PAIRS = {
    "bm25": ("pydantic-bm25.json", "pydantic-definition-bm25.json"),
    "vector": ("pydantic-vector-zh.json", "pydantic-definition-vector.json"),
    "hybrid": ("pydantic-hybrid-zh.json", "pydantic-definition-hybrid.json"),
}


def chunk_rows(report: dict) -> dict:
    db = ROOT / report["index"] if report.get("index") else index_path(
        ROOT, load_manifest(ROOT / "scenarios/pydantic/manifest.json"), 1800)
    with closing(sqlite3.connect(db)) as connection:
        connection.row_factory = sqlite3.Row
        return {row["id"]: dict(row) for row in connection.execute(
            "SELECT id,source_path,start_line,end_line,heading_path FROM chunks")}


def covered(span: dict, ids: list[str], rows: dict) -> bool:
    return any(rows[chunk_id]["source_path"] == span["path"] and
               rows[chunk_id]["start_line"] <= span["start_line"] and
               rows[chunk_id]["end_line"] >= span["end_line"] for chunk_id in ids)


def describe(report: dict, rows: dict, spans: dict) -> dict:
    details = {}
    for item in report["details"]:
        ids = item["top_chunk_ids"]
        details[item["id"]] = {
            "top_lines": [[rows[chunk_id]["source_path"], rows[chunk_id]["start_line"],
                           rows[chunk_id]["end_line"]] for chunk_id in ids[:3]],
            "section_top": item.get("all_found_top"),
            "section_context": item.get("all_found_context"),
            "spans": [{"point": span["point"], "top10": covered(span, ids, rows),
                       "context3": covered(span, ids[:3], rows)} for span in spans.get(item["id"], [])],
        }
    return details


def main() -> None:
    spans = json.loads((ROOT / "scenarios/pydantic/eval/evidence_spans.json").read_text(encoding="utf-8"))
    output = {}
    for strategy, (baseline_name, experiment_name) in PAIRS.items():
        baseline = json.loads((ROOT / "reports" / baseline_name).read_text(encoding="utf-8"))
        experiment = json.loads((ROOT / "reports" / experiment_name).read_text(encoding="utf-8"))
        if baseline["source_commit"] != experiment["source_commit"]:
            raise ValueError("source versions differ")
        old = describe(baseline, chunk_rows(baseline), spans)
        new = describe(experiment, chunk_rows(experiment), spans)
        output[strategy] = {
            "baseline_report": baseline_name, "experiment_report": experiment_name,
            "baseline_section_top": baseline["all_anchor_recall_at_k"],
            "experiment_section_top": experiment["all_anchor_recall_at_k"],
            "baseline_section_context": baseline["all_anchor_context_hit_at_k"],
            "experiment_section_context": experiment["all_anchor_context_hit_at_k"],
            "changed_context": [key for key in old if old[key]["top_lines"] != new[key]["top_lines"]],
            "details": {key: {"baseline": old[key], "experiment": new[key]} for key in old},
        }
    path = ROOT / "reports/pydantic-definition-comparison.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for strategy, summary in output.items():
        print(strategy, "section", summary["baseline_section_top"], summary["experiment_section_top"],
              summary["baseline_section_context"], summary["experiment_section_context"],
              "changed", summary["changed_context"])
        for key in ("P01", "P06"):
            print(key, "before", summary["details"][key]["baseline"]["spans"],
                  "after", summary["details"][key]["experiment"]["spans"])


if __name__ == "__main__":
    main()
