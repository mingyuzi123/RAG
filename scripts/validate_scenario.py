"""Validate the generic scenario contract, pinned source and evidence headings."""

from argparse import ArgumentParser
from pathlib import Path
import json
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.store import load_manifest  # noqa: E402


HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")


def headings(path: Path) -> set[str]:
    found = set()
    in_code = False
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        match = HEADING.match(line) if not in_code else None
        if match:
            found.add(match.group(1))
    return found


def validate(path: Path) -> dict:
    manifest = load_manifest(path)
    root = (ROOT / manifest["local_checkout"]).resolve()
    commit = manifest["upstream_commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("upstream_commit must be a full Git SHA")
    if not root.is_dir():
        raise FileNotFoundError(f"source checkout missing: {root}")
    actual = subprocess.check_output([
        "git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), "rev-parse", "HEAD"],
        text=True).strip()
    if actual != commit:
        raise ValueError(f"source checkout differs: {actual} != {commit}")
    files = manifest["files"]
    if len(files) != len(set(files)) or not files:
        raise ValueError("manifest files must be nonempty and unique")
    for relative in files:
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError(f"missing or invalid source: {relative}")
    questions_file = path.parent / "eval" / "questions.jsonl"
    query_file = path.parent / "eval" / "queries_en.json"
    questions = [json.loads(line) for line in questions_file.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    queries = json.loads(query_file.read_text(encoding="utf-8"))
    ids = [item["id"] for item in questions]
    if not ids or len(ids) != len(set(ids)) or set(ids) != set(queries):
        raise ValueError("question and English-query IDs must be nonempty and identical")
    cache = {}
    for item in questions:
        evidence = item.get("evidence", [])
        points = item.get("expected_points", [])
        if not item.get("question") or not queries[item["id"]].strip():
            raise ValueError(f"{item['id']}: question and English query are required")
        if item.get("answerability") == "answerable":
            if not evidence or not points:
                raise ValueError(f"{item['id']}: answerable question requires points and evidence")
        elif item.get("answerability") == "unanswerable":
            if evidence or points:
                raise ValueError(f"{item['id']}: unanswerable question must not have points or evidence")
        else:
            raise ValueError(f"{item['id']}: invalid answerability")
        for anchor in evidence:
            relative = anchor["path"]
            if relative not in files:
                raise ValueError(f"{item['id']}: evidence outside corpus: {relative}")
            if relative not in cache:
                cache[relative] = headings(root / relative)
            if anchor["heading"] not in cache[relative]:
                raise ValueError(f"{item['id']}: heading not found: {relative} > {anchor['heading']}")
    return {"scenario": manifest["id"], "source_commit": commit, "files": len(files),
            "questions": len(questions),
            "answerable": sum(item["answerability"] == "answerable" for item in questions)}


def main() -> None:
    cli = ArgumentParser()
    cli.add_argument("--scenario", type=Path, required=True)
    args = cli.parse_args()
    print(json.dumps(validate(args.scenario), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
