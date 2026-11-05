"""Generate answers only for questions that gained a targeted neighbor."""

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
    target = ROOT / "reports/targeted-window-answers.json"
    output = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    done = {(row["scenario"], row["id"]) for row in output}
    for scenario, heldout in (("pydantic", False), ("crewai", False), ("crewai", True)):
        suffix = "-heldout" if heldout else ""
        report = json.loads((ROOT / "reports" / f"{scenario}-targeted-window{suffix}.json").read_text(encoding="utf-8"))
        question_file = "heldout_compare.jsonl" if heldout else "questions.jsonl"
        questions = {row["id"]: row for row in map(json.loads,
            (ROOT / "scenarios" / scenario / "eval" / question_file).read_text(encoding="utf-8").splitlines())}
        manifest = load_manifest(ROOT / "scenarios" / scenario / "manifest.json")
        with closing(sqlite3.connect(index_path(ROOT, manifest, 1800))) as parent_db, \
             closing(sqlite3.connect(index_path(ROOT, manifest, 1800, True))) as child_db:
            parent_db.row_factory = sqlite3.Row
            child_db.row_factory = sqlite3.Row
            for entry in report["details"]:
                qid = entry["id"]
                if not entry["added_neighbor"] or (scenario, qid) in done:
                    continue
                evidence = []
                for hit in entry["selected"]:
                    db = child_db if hit["kind"] == "child" else parent_db
                    row = dict(db.execute("SELECT * FROM chunks WHERE id=?", (hit["id"],)).fetchone())
                    row["heading_path"] = json.loads(row["heading_path"])
                    evidence.append(row)
                result = generate_answer(questions[qid]["question"], evidence)
                output.append({"scenario": scenario, "id": qid, "heldout": heldout,
                    "expected_points": questions[qid]["expected_points"],
                    "context": entry["selected"], "answer": result["answer"],
                    "cited_numbers": result["cited_numbers"],
                    "citation_numbers_valid": result["citation_numbers_valid"], "usage": result["usage"]})
                target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                done.add((scenario, qid))
                print(qid, result["usage"].get("prompt_tokens"), flush=True)


if __name__ == "__main__":
    main()
