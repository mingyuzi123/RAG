"""Answer unchanged contexts once so the full frozen suite has a score."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.generation import generate_answer  # noqa: E402
from raglab.store import index_path, load_manifest  # noqa: E402
from scripts.run_with_deepseek import load_local_env, require_key  # noqa: E402


def main() -> None:
    load_local_env()
    require_key()
    target = ROOT / "reports/parent-answer-unchanged.json"
    output = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    done = {(row["scenario"], row["id"]) for row in output}
    for scenario, report_file, question_file in (
        ("pydantic", "pydantic-parent-context.json", "questions.jsonl"),
        ("crewai", "crewai-parent-context.json", "questions.jsonl"),
        ("crewai", "crewai-parent-heldout.json", "heldout_compare.jsonl"),
    ):
        report = json.loads((ROOT / "reports" / report_file).read_text(encoding="utf-8"))
        questions = {row["id"]: row for row in map(json.loads,
            (ROOT / "scenarios" / scenario / "eval" / question_file).read_text(encoding="utf-8").splitlines())}
        path = index_path(ROOT, load_manifest(ROOT / "scenarios" / scenario / "manifest.json"), 1800)
        with closing(sqlite3.connect(path)) as db:
            db.row_factory = sqlite3.Row
            for entry in report["details"]:
                qid = entry["id"]
                if entry["baseline_ids"] != entry["parent_ids"] or (scenario, qid) in done:
                    continue
                evidence = []
                for chunk_id in entry["baseline_ids"]:
                    row = dict(db.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone())
                    row["heading_path"] = json.loads(row["heading_path"])
                    evidence.append(row)
                answer = generate_answer(questions[qid]["question"], evidence)
                output.append({"scenario": scenario, "id": qid, "answerability": questions[qid]["answerability"],
                    "expected_points": questions[qid]["expected_points"], "answer": answer["answer"],
                    "context": [{"path": row["source_path"], "lines": [row["start_line"], row["end_line"]]}
                                for row in evidence], "cited_numbers": answer["cited_numbers"],
                    "citation_numbers_valid": answer["citation_numbers_valid"], "usage": answer["usage"]})
                target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                done.add((scenario, qid))
                print(scenario, qid, answer["usage"].get("total_tokens"), flush=True)


if __name__ == "__main__":
    main()
