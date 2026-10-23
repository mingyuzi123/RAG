"""Generate two answers from fixed baseline and diverse contexts for one eval question."""

from argparse import ArgumentParser
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.generation import generate_answer  # noqa: E402
from raglab.store import index_path, load_manifest  # noqa: E402
from scripts.run_with_deepseek import load_local_env, require_key  # noqa: E402


def main():
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("--report", type=Path,
                     default=ROOT / "reports" / "crewai-diverse-context-w02.json")
    cli.add_argument("--id", default="C10", help="Evaluation question ID")
    args = cli.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    detail = next((item for item in report["details"] if item["id"] == args.id), None)
    if detail is None:
        cli.error(f"question {args.id} not present in selection report")
    questions = [json.loads(line) for line in (ROOT / "scenarios" / "crewai" / "eval" /
                                                "questions.jsonl").read_text(encoding="utf-8").splitlines()]
    question = next((item for item in questions if item["id"] == args.id), None)
    if question is None:
        cli.error(f"question {args.id} not present in CrewAI eval set")
    manifest = load_manifest(ROOT / "scenarios" / "crewai" / "manifest.json")
    if report["source_commit"] != manifest["upstream_commit"]:
        cli.error("selection report and source version differ")
    db_path = index_path(ROOT, manifest, 1800)
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        rows = {row["id"]: row for row in db.execute("SELECT * FROM chunks")}
    load_local_env()
    require_key()
    output = {"timestamp": datetime.now(timezone.utc).isoformat(), "question_id": args.id,
              "question": question["question"], "expected_points": question["expected_points"],
              "source_commit": manifest["upstream_commit"],
              "selection_report": args.report.resolve().relative_to(ROOT).as_posix(),
              "variants": {}}
    for name, field in (("baseline", "baseline_context_ids"),
                        ("diverse", "diverse_context_ids")):
        chunk_ids = detail[field]
        evidence = [{"source_path": rows[chunk_id]["source_path"],
                     "heading_path": json.loads(rows[chunk_id]["heading_path"]),
                     "start_line": rows[chunk_id]["start_line"],
                     "end_line": rows[chunk_id]["end_line"],
                     "text": rows[chunk_id]["text"]} for chunk_id in chunk_ids]
        output["variants"][name] = {"chunk_ids": chunk_ids,
                                    "headings": [item["heading_path"][-1] for item in evidence],
                                    "result": generate_answer(question["question"], evidence)}
    target = ROOT / "logs" / "context_answer_compare.jsonl"
    target.parent.mkdir(exist_ok=True)
    with target.open("a", encoding="utf-8") as log:
        log.write(json.dumps(output, ensure_ascii=False) + "\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
