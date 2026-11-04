"""Verify P06 and C13 answers using retrieved original parent chunks."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.generation import generate_answer  # noqa: E402
from scripts.run_with_deepseek import load_local_env, require_key  # noqa: E402


def main() -> None:
    load_local_env()
    require_key()
    output = []
    for scenario, qid in (("pydantic", "P06"), ("crewai", "C13")):
        report = json.loads((ROOT / "reports" / f"{scenario}-parent-context.json").read_text(encoding="utf-8"))
        entry = next(row for row in report["details"] if row["id"] == qid)
        questions = {row["id"]: row for row in map(json.loads,
            (ROOT / "scenarios" / scenario / "eval/questions.jsonl").read_text(encoding="utf-8").splitlines())}
        with closing(sqlite3.connect(ROOT / report["parent_index"])) as db:
            db.row_factory = sqlite3.Row
            selected = []
            for chunk_id in entry["parent_ids"]:
                row = dict(db.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone())
                row["heading_path"] = json.loads(row["heading_path"])
                selected.append(row)
        answer = generate_answer(questions[qid]["question"], selected)
        output.append({"scenario": scenario, "id": qid, "expected_points": questions[qid]["expected_points"],
            "context": [{"path": row["source_path"], "lines": [row["start_line"], row["end_line"]]}
                        for row in selected], "answer": answer["answer"],
            "cited_numbers": answer["cited_numbers"],
            "citation_numbers_valid": answer["citation_numbers_valid"], "usage": answer["usage"]})
        print(scenario, qid, answer["usage"])
    path = ROOT / "reports/parent-context-answers.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
