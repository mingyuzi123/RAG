"""Replay a fixed retrieval report with bounded same-section neighbors."""

from argparse import ArgumentParser
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.store import index_path, load_manifest  # noqa: E402


def covers(span: dict, chunks: list[dict]) -> bool:
    return any(chunk["source_path"] == span["path"] and
               chunk["start_line"] <= span["start_line"] and
               chunk["end_line"] >= span["end_line"] for chunk in chunks)


def covers_sections(anchors: list[dict], chunks: list[dict]) -> bool:
    return all(any(chunk["source_path"] == anchor["path"] and
                   anchor["heading"] in chunk["heading_path"] for chunk in chunks)
               for anchor in anchors)


def neighbors(anchor: dict, by_section: dict) -> list[dict]:
    key = (anchor["source_path"], tuple(anchor["heading_path"]))
    section = by_section[key]
    position = next(index for index, item in enumerate(section) if item["id"] == anchor["id"])
    result = []
    if position > 0:
        result.append(section[position - 1])
    if position + 1 < len(section):
        result.append(section[position + 1])
    return result


def evaluate(report_path: Path, spans_path: Path, context_k: int = 3) -> dict:
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes)
    manifest = load_manifest(ROOT / "scenarios" / "pydantic" / "manifest.json")
    db_path = index_path(ROOT, manifest, 1800)
    if report["scenario"] != manifest["id"] or report["source_commit"] != manifest["upstream_commit"]:
        raise ValueError("report and current scenario source version differ")
    if not 1 <= context_k <= report["top_k"]:
        raise ValueError("context_k must fit saved candidates")
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute("SELECT * FROM chunks")]
    chunks = {row["id"]: {**row, "heading_path": json.loads(row["heading_path"])} for row in rows}
    by_section = {}
    for chunk in chunks.values():
        key = (chunk["source_path"], tuple(chunk["heading_path"]))
        by_section.setdefault(key, []).append(chunk)
    for section in by_section.values():
        section.sort(key=lambda item: (item["start_line"], item["end_line"]))
    spans = json.loads(spans_path.read_text(encoding="utf-8"))

    details = []
    for question in report["details"]:
        ids = question["top_chunk_ids"]
        baseline = [chunks[chunk_id] for chunk_id in ids[:context_k]]
        budget = sum(len(item["text"]) for item in baseline)
        expanded = list(baseline)
        origin = {item["id"]: "retrieved" for item in expanded}
        for anchor in baseline:
            for adjacent in neighbors(anchor, by_section):
                if adjacent["id"] not in origin:
                    expanded.append(adjacent)
                    origin[adjacent["id"]] = f"neighbor:{anchor['id']}"

        # Deterministic pilot: each retrieved hit is followed by its neighbors.
        # The gold spans below are used only after selection, never here.
        ordered = []
        for anchor in baseline:
            for item in [anchor, *neighbors(anchor, by_section)]:
                if item["id"] not in {seen["id"] for seen in ordered}:
                    ordered.append(item)
        selected = []
        used = 0
        for item in ordered:
            if len(selected) >= context_k:
                break
            if used + len(item["text"]) <= budget:
                selected.append(item)
                used += len(item["text"])

        gold = spans.get(question["id"], [])
        details.append({
            "id": question["id"], "baseline_ids": [item["id"] for item in baseline],
            "expanded_ids": [item["id"] for item in expanded],
            "selected_ids": [item["id"] for item in selected],
            "added_candidates": [item["id"] for item in expanded if item["id"] not in ids],
            "added_context": [item["id"] for item in selected if item["id"] not in {part["id"] for part in baseline}],
            "removed_context": [item["id"] for item in baseline if item["id"] not in {part["id"] for part in selected}],
            "origin": {item["id"]: origin[item["id"]] for item in expanded},
            "char_budget": budget, "selected_chars": used,
            "baseline_sections": covers_sections(question.get("anchors", []), baseline),
            "selected_sections": covers_sections(question.get("anchors", []), selected),
            "spans": [{"point": span["point"], "baseline": covers(span, baseline),
                       "expanded": covers(span, expanded), "selected": covers(span, selected)} for span in gold],
        })
    questions_path = ROOT / "scenarios" / "pydantic" / "eval" / "questions.jsonl"
    answerability = {item["id"]: item["answerability"] for item in
                     (json.loads(line) for line in questions_path.read_text(encoding="utf-8").splitlines())}
    answerable = [item for item in details if answerability[item["id"]] == "answerable"]
    return {
        "scenario": manifest["id"], "source_commit": manifest["upstream_commit"],
        "index": db_path.relative_to(ROOT).as_posix(),
        "source_report": report_path.relative_to(ROOT).as_posix(),
        "source_report_sha256": sha256(report_bytes).hexdigest(),
        "method": "same-section-neighbor-v1", "context_k": context_k,
        "budget": "same character count as baseline top-k, per question",
        "changed_context": [item["id"] for item in details if item["baseline_ids"] != item["selected_ids"]],
        "section_coverage_baseline": sum(item["baseline_sections"] for item in answerable),
        "section_coverage_selected": sum(item["selected_sections"] for item in answerable),
        "section_gained": [item["id"] for item in answerable if item["selected_sections"] and not item["baseline_sections"]],
        "section_lost": [item["id"] for item in answerable if item["baseline_sections"] and not item["selected_sections"]],
        "details": details,
    }


def main() -> None:
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("--report", type=Path, default=ROOT / "reports" / "pydantic-hybrid-zh.json")
    cli.add_argument("--spans", type=Path, default=ROOT / "scenarios" / "pydantic" / "eval" / "evidence_spans.json")
    cli.add_argument("--output", type=Path, default=ROOT / "reports" / "pydantic-neighbor-context.json")
    args = cli.parse_args()
    result = evaluate(args.report.resolve(), args.spans.resolve())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in result["details"]:
        print(json.dumps({key: item[key] for key in ("id", "added_candidates", "added_context", "removed_context", "spans")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
