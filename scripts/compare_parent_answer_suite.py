"""Run paired DeepSeek answers only where parent retrieval changed the prompt context."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.generation import generate_answer  # noqa: E402
from scripts.run_with_deepseek import load_local_env, require_key  # noqa: E402


def selected(db: sqlite3.Connection, ids: list[str]) -> list[dict]:
    output = []
    for chunk_id in ids:
        row = dict(db.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone())
        row["heading_path"] = json.loads(row["heading_path"])
        output.append(row)
    return output


def main() -> None:
    load_local_env()
    require_key()
    target = ROOT / "reports/parent-answer-suite.json"
    existing = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    done = {(row["scenario"], row["id"], row["variant"]) for row in existing}
    for scenario, report_name, question_name in (
        ("pydantic", "pydantic-parent-context.json", "questions.jsonl"),
        ("crewai", "crewai-parent-context.json", "questions.jsonl"),
        ("crewai", "crewai-parent-heldout.json", "heldout_compare.jsonl"),
    ):
        report = json.loads((ROOT / "reports" / report_name).read_text(encoding="utf-8"))
        questions = {row["id"]: row for row in map(json.loads,
            (ROOT / "scenarios" / scenario / "eval" / question_name).read_text(encoding="utf-8").splitlines())}
        index = report.get("parent_index")
        if index is None:
            from raglab.store import index_path, load_manifest
            index = index_path(ROOT, load_manifest(ROOT / "scenarios" / scenario / "manifest.json"), 1800)
        else:
            index = ROOT / index
        with closing(sqlite3.connect(index)) as db:
            db.row_factory = sqlite3.Row
            for entry in report["details"]:
                if entry["baseline_ids"] == entry["parent_ids"]:
                    continue
                qid = entry["id"]
                for variant, field in (("baseline", "baseline_ids"), ("parent", "parent_ids")):
                    if (scenario, qid, variant) in done:
                        continue
                    evidence = selected(db, entry[field])
                    result = generate_answer(questions[qid]["question"], evidence)
                    existing.append({"scenario": scenario, "id": qid, "variant": variant,
                        "expected_points": questions[qid]["expected_points"],
                        "context": [{"path": row["source_path"], "lines": [row["start_line"], row["end_line"]]}
                                    for row in evidence], "answer": result["answer"],
                        "cited_numbers": result["cited_numbers"],
                        "citation_numbers_valid": result["citation_numbers_valid"], "usage": result["usage"]})
                    target.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    done.add((scenario, qid, variant))
                    print(scenario, qid, variant, result["usage"].get("total_tokens"), flush=True)


if __name__ == "__main__":
    main()
