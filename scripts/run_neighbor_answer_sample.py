"""Run one paid P01 answer using the saved neighbor experiment context."""

from contextlib import closing
from pathlib import Path
import json
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.generation import generate_answer  # noqa: E402
from scripts.run_with_deepseek import load_local_env, require_key  # noqa: E402


def main() -> None:
    load_local_env()
    require_key()
    experiment = json.loads((ROOT / "reports/pydantic-neighbor-context.json").read_text(encoding="utf-8"))
    detail = next(item for item in experiment["details"] if item["id"] == "P01")
    db_path = ROOT / experiment["index"]
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        rows = {row["id"]: dict(row) for row in db.execute("SELECT * FROM chunks")}
    selected = [{**rows[chunk_id], "heading_path": json.loads(rows[chunk_id]["heading_path"])}
                for chunk_id in detail["selected_ids"]]
    question = next(json.loads(line)["question"] for line in
                    (ROOT / "scenarios/pydantic/eval/questions.jsonl").read_text(encoding="utf-8").splitlines()
                    if json.loads(line)["id"] == "P01")
    result = generate_answer(question, selected)
    output = {
        "question_id": "P01", "source_commit": experiment["source_commit"],
        "experiment_method": experiment["method"],
        "context_ids": detail["selected_ids"],
        "context_lines": [[item["source_path"], item["start_line"], item["end_line"]] for item in selected],
        "answer": result["answer"], "cited_numbers": result["cited_numbers"],
        "citation_numbers_valid": result["citation_numbers_valid"], "usage": result["usage"],
    }
    path = ROOT / "reports/pydantic-neighbor-p01-answer.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
