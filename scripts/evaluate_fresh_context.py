"""Paired one-run answer evaluation on questions frozen before this script ran."""

import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.generation import generate_answer  # noqa: E402
from raglab.service import retrieve, retrieve_targeted_window  # noqa: E402
from raglab.store import index_path, load_manifest  # noqa: E402
from raglab.vector import load_model  # noqa: E402
from scripts.run_with_deepseek import load_local_env, require_key  # noqa: E402

QUESTIONS = ROOT / "scenarios/pydantic/eval/fresh_context_v1.jsonl"
OUTPUT = ROOT / "reports/fresh-context-v1-answers.json"


def record(question: dict, policy: str, evidence: list[dict], elapsed_ms: float) -> dict:
    result = generate_answer(question["question"], evidence)
    return {"id": question["id"], "policy": policy,
            "question": question["question"], "answerability": question["answerability"],
            "expected_points": question["expected_points"], "expected_evidence": question["evidence"],
            "context": [{"id": item["id"], "source_path": item["source_path"],
                         "heading_path": item["heading_path"], "start_line": item["start_line"],
                         "end_line": item["end_line"], "text": item["text"],
                         "origin": item.get("context_origin", "baseline_top_k")}
                        for item in evidence],
            "retrieval_ms": round(elapsed_ms, 2), "answer": result["answer"],
            "citation_numbers_valid": result["citation_numbers_valid"],
            "usage": result["usage"]}


def main() -> None:
    load_local_env()
    require_key()
    cache = ROOT / ".venv/hf/hub"
    if cache.is_dir() and not os.environ.get("HF_HOME"):
        os.environ["HF_HOME"] = str(cache.parent)
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    model = load_model()
    manifest = load_manifest(ROOT / "scenarios/pydantic/manifest.json")
    parent_path = index_path(ROOT, manifest, 1800)
    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines()]
    saved = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else []
    done = {(item["id"], item["policy"]) for item in saved}
    for question in questions:
        for policy in ("top_k", "targeted_window"):
            if (question["id"], policy) in done:
                continue
            started = time.perf_counter()
            if policy == "top_k":
                evidence = retrieve(parent_path, question["question"], "hybrid",
                                    question["english_query"], 10, model)[:3]
            else:
                _, _, evidence, _ = retrieve_targeted_window(
                    ROOT, manifest, parent_path, question["question"],
                    question["english_query"], 10, 3, model)
            elapsed = (time.perf_counter() - started) * 1000
            saved.append(record(question, policy, evidence, elapsed))
            OUTPUT.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            done.add((question["id"], policy))
            print(question["id"], policy, saved[-1]["usage"].get("total_tokens"), flush=True)


if __name__ == "__main__":
    main()
