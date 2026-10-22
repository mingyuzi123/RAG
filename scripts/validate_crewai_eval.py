"""Validate the CrewAI scenario manifest and its evidence-linked questions."""

from collections import Counter
from pathlib import Path
import json
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "crewai"
MANIFEST = SCENARIO / "manifest.json"
QUESTIONS = SCENARIO / "eval" / "questions.jsonl"
HELDOUT = SCENARIO / "eval" / "heldout_compare.jsonl"
SUBQUERIES = SCENARIO / "eval" / "subqueries_zh.json"
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")


def headings_in(path: Path) -> set[str]:
    headings: set[str] = set()
    in_code = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code and (match := HEADING.match(line)):
            headings.add(match.group(1))
    return headings


def main() -> int:
    errors: list[str] = []
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source_root = ROOT / manifest["local_checkout"]
    allowed_files = set(manifest["files"])
    commit = manifest["upstream_commit"]

    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        errors.append("manifest.upstream_commit must be a full Git SHA")
    if len(allowed_files) != len(manifest["files"]):
        errors.append("manifest.files contains duplicates")
    if not source_root.is_dir():
        errors.append(f"source checkout missing: {source_root}")
    else:
        try:
            actual = subprocess.check_output(
                ["git", "-c", f"safe.directory={source_root.as_posix()}", "-C", str(source_root), "rev-parse", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if actual != commit:
                errors.append(f"source commit differs: expected {commit}, got {actual}")
        except (OSError, subprocess.CalledProcessError):
            errors.append("cannot read source checkout commit")

    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    heldout = ([json.loads(line) for line in HELDOUT.read_text(encoding="utf-8").splitlines() if line.strip()]
               if HELDOUT.is_file() else [])
    ids = [question["id"] for question in questions + heldout]
    if len(ids) != len(set(ids)):
        errors.append("question IDs are not unique")
    if heldout and (len(heldout) != 6 or any(item.get("type") != "compare" for item in heldout)):
        errors.append("heldout set must contain six comparison questions")
    if SUBQUERIES.is_file():
        pairs = json.loads(SUBQUERIES.read_text(encoding="utf-8"))
        compare_ids = {question["id"] for question in questions if question["type"] == "compare"}
        if set(pairs) != compare_ids:
            errors.append("subquery IDs must match all comparison questions")
        for qid, values in pairs.items():
            if not isinstance(values, list) or not 2 <= len(values) <= 4 or any(
                    not isinstance(value, str) or not value.strip() for value in values):
                errors.append(f"{qid}: requires 2-4 nonempty subqueries")

    heading_cache: dict[str, set[str]] = {}
    for question in questions + heldout:
        qid = question["id"]
        answerability = question.get("answerability")
        evidence = question.get("evidence", [])
        points = question.get("expected_points", [])
        if not question.get("question") or not question.get("type"):
            errors.append(f"{qid}: question and type are required")
        if answerability == "answerable" and (not evidence or not points):
            errors.append(f"{qid}: answerable question needs evidence and expected points")
        elif answerability == "unanswerable" and (evidence or points):
            errors.append(f"{qid}: unanswerable question must have no evidence or expected points")
        elif answerability not in {"answerable", "unanswerable"}:
            errors.append(f"{qid}: invalid answerability")
        for anchor in evidence:
            path = anchor["path"]
            if path not in allowed_files:
                errors.append(f"{qid}: source is outside the scenario corpus: {path}")
                continue
            source_file = source_root / path
            if not source_file.is_file():
                errors.append(f"{qid}: source file missing: {path}")
                continue
            if path not in heading_cache:
                heading_cache[path] = headings_in(source_file)
            if anchor["heading"] not in heading_cache[path]:
                errors.append(f"{qid}: heading not found in {path}: {anchor['heading']}")

    counts = Counter(q["type"] for q in questions)
    print(f"CrewAI eval: {len(questions)} questions; types={dict(sorted(counts.items()))}")
    print(f"Held-out compare: {len(heldout)} questions")
    print(f"Pinned source: {commit}; files={len(allowed_files)}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("All evidence anchors and source versions validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
