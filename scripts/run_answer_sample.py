"""Run a fixed scenario's questions through the real answer pipeline."""

from argparse import ArgumentParser
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.service import answer  # noqa: E402
from raglab.store import index_path, load_manifest  # noqa: E402
from raglab.vector import load_model  # noqa: E402
from scripts.run_with_deepseek import load_local_env, require_key  # noqa: E402


def main() -> None:
    cli = ArgumentParser()
    cli.add_argument("--scenario", type=Path, required=True)
    cli.add_argument("--id", action="append", dest="ids", help="Repeat to run selected question IDs; default all")
    cli.add_argument("--strategy", choices=("bm25", "vector", "hybrid"), default="hybrid")
    cli.add_argument("--top-k", type=int, default=10)
    cli.add_argument("--context-k", type=int, default=3)
    args = cli.parse_args()
    load_local_env(ROOT / ".env")
    require_key()
    manifest = load_manifest(args.scenario)
    db_path = index_path(ROOT, manifest, 1800)
    questions = [json.loads(line) for line in (args.scenario.parent / "eval" / "questions.jsonl")
                 .read_text(encoding="utf-8").splitlines() if line.strip()]
    english = json.loads((args.scenario.parent / "eval" / "queries_en.json").read_text(encoding="utf-8"))
    if args.ids:
        unknown = set(args.ids) - {item["id"] for item in questions}
        if unknown:
            cli.error(f"unknown question IDs: {', '.join(sorted(unknown))}")
        questions = [item for item in questions if item["id"] in args.ids]
    model = load_model() if args.strategy in ("vector", "hybrid") else None
    records = []
    for item in questions:
        trace = answer(ROOT, manifest, db_path, item["question"], args.strategy,
                       english.get(item["id"]), args.top_k, args.context_k, model)
        record = {"id": item["id"], "request_id": trace["request_id"],
                  "tokens": trace["result"].get("usage", {}).get("total_tokens"),
                  "citation_numbers_valid": trace["result"]["citation_numbers_valid"]}
        records.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    target = ROOT / "logs" / f"answer_sample_{manifest['id']}.json"
    target.write_text(json.dumps({"scenario": manifest["id"], "source_commit": manifest["upstream_commit"],
                                  "strategy": args.strategy, "top_k": args.top_k,
                                  "context_k": args.context_k, "records": records},
                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved local request IDs: {target}")


if __name__ == "__main__":
    main()
