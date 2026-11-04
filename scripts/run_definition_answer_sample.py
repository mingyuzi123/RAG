"""Call DeepSeek once with P06 context from the experimental definition index."""

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
    report = json.loads((ROOT / "reports/pydantic-definition-hybrid.json").read_text(encoding="utf-8"))
    item = next(row for row in report["details"] if row["id"] == "P06")
    with closing(sqlite3.connect(ROOT / report["index"])) as db:
        db.row_factory = sqlite3.Row
        rows = {row["id"]: dict(row) for row in db.execute("SELECT * FROM chunks")}
    selected = [{**rows[chunk_id], "heading_path": json.loads(rows[chunk_id]["heading_path"])}
                for chunk_id in item["top_chunk_ids"][:3]]
    questions = [json.loads(line) for line in
                 (ROOT / "scenarios/pydantic/eval/questions.jsonl").read_text(encoding="utf-8").splitlines()]
    question = next(row["question"] for row in questions if row["id"] == "P06")
    result = generate_answer(question, selected)
    output = {"question_id": "P06", "source_commit": report["source_commit"],
              "index": report["index"], "parser_variant": report["parser_variant"],
              "context": [{"id": row["id"], "path": row["source_path"],
                           "lines": [row["start_line"], row["end_line"]]} for row in selected],
              "answer": result["answer"], "cited_numbers": result["cited_numbers"],
              "citation_numbers_valid": result["citation_numbers_valid"], "usage": result["usage"]}
    path = ROOT / "reports/pydantic-definition-p06-answer.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
