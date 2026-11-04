"""Compare paired answers for CrewAI questions whose evidence changed materially."""

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
    old = json.loads((ROOT / "reports/crewai-table-v3-hybrid-zh.json").read_text(encoding="utf-8"))
    new = json.loads((ROOT / "reports/crewai-definition-hybrid.json").read_text(encoding="utf-8"))
    manifest = load_manifest(ROOT / "scenarios/crewai/manifest.json")
    paths = {"baseline": index_path(ROOT, manifest, 1800), "definition_items": ROOT / new["index"]}
    reports = {"baseline": old, "definition_items": new}
    questions = {item["id"]: item for item in map(json.loads,
        (ROOT / "scenarios/crewai/eval/questions.jsonl").read_text(encoding="utf-8").splitlines())}
    output = []
    for qid in ("C01", "C13"):
        for variant in ("baseline", "definition_items"):
            report = reports[variant]
            entry = next(row for row in report["details"] if row["id"] == qid)
            with closing(sqlite3.connect(paths[variant])) as db:
                db.row_factory = sqlite3.Row
                selected = []
                for chunk_id in entry["top_chunk_ids"][:3]:
                    row = dict(db.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone())
                    row["heading_path"] = json.loads(row["heading_path"])
                    selected.append(row)
            result = generate_answer(questions[qid]["question"], selected)
            output.append({"id": qid, "variant": variant, "expected_points": questions[qid]["expected_points"],
                "context": [{"path": row["source_path"], "lines": [row["start_line"], row["end_line"]]} for row in selected],
                "context_chars": sum(len(row["text"]) for row in selected), "answer": result["answer"],
                "cited_numbers": result["cited_numbers"], "citation_numbers_valid": result["citation_numbers_valid"],
                "usage": result["usage"]})
            print(qid, variant, result["usage"])
    path = ROOT / "reports/crewai-definition-risk-answers.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
