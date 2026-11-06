"""Run end-to-end answers with frozen v1/v3 queries; assess saved evidence separately."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_with_deepseek import load_local_env
from raglab.service import answer
from raglab.vector import load_model
from raglab.web import scenario_context


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--version", choices=["v1", "v3", "both"], default="both")
    cli.add_argument("--context-policy", choices=["top_k", "targeted_window"], default="top_k")
    cli.add_argument("--output", type=Path, default=ROOT / "reports/QUERY_REWRITE_ANSWERS.json")
    args = cli.parse_args()
    load_local_env()
    os.environ.setdefault("HF_HOME", str(ROOT / ".venv" / "hf"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    old = json.loads((ROOT / "reports/QUERY_REWRITE_V2.json").read_text(encoding="utf-8"))
    new = {r["id"]: r for r in json.loads((ROOT / "reports/QUERY_REWRITE_V3.json").read_text(encoding="utf-8"))}
    output = args.output
    if output.exists():
        raise SystemExit("Output already exists; preserve the previous run before rerunning.")
    model = load_model()
    results = []
    for row in old:
        context = scenario_context(ROOT, ROOT / "scenarios" / row["scenario"] / "manifest.json")
        item = next(q for q in context["examples"] if q["id"] == row["id"])
        for version, query in [("v1", row["v1_query"]), ("v3", new[row["id"]]["v3_query"])]:
            if args.version != "both" and args.version != version:
                continue
            trace = answer(ROOT, context["manifest"], context["db_path"], item["question"],
                           "hybrid", query, 10, 3, model,
                           context_policy=args.context_policy,
                           query_metadata={"source": "auto", "prompt_version": "english-keywords-" + version,
                                           "frozen_query": True})
            results.append({"id": item["id"], "version": version, "question": item["question"],
                            "expected_points": item["expected_points"], "query": query,
                            "source_commit": trace["source_commit"], "request_id": trace["request_id"],
                            "answer": trace["result"]["answer"], "model": trace["result"].get("model"),
                            "context_policy": args.context_policy, "window": trace["window"],
                            "selected_chunk_ids": trace["selected_chunk_ids"],
                            "citation_format_valid": trace["result"]["citation_numbers_valid"],
                            "usage": trace["result"]["usage"], "sources": trace["result"]["sources"],
                            "generation_ms": trace["generation_ms"]})
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(item["id"], version, trace["request_id"], flush=True)


if __name__ == "__main__":
    main()
