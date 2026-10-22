"""Run a frozen held-out comparison set with original and automatic queries."""

from hashlib import sha256
from pathlib import Path
import json
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.decomposition import PROMPT_VERSION, SYSTEM_PROMPT, decompose_question  # noqa: E402
from raglab.service import retrieve  # noqa: E402
from raglab.store import index_path, load_manifest  # noqa: E402
from raglab.vector import MODEL_ID, MODEL_REVISION, load_model  # noqa: E402
from scripts.evaluate_retrieval import anchors_found  # noqa: E402
from scripts.run_with_deepseek import load_local_env, require_key  # noqa: E402


DATASET = ROOT / "scenarios" / "crewai" / "eval" / "heldout_compare.jsonl"
CACHE = ROOT / "logs" / "auto_decomposition_heldout.json"
OUTPUT = ROOT / "reports" / "crewai-auto-decomposition-heldout.json"
TOP_K = 10
CONTEXT_K = 3


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _evaluate_variant(question: dict, candidates: list[dict]) -> dict:
    top = anchors_found(question, candidates)
    context = anchors_found(question, candidates[:CONTEXT_K])
    return {"all_found_top": all(top), "all_found_context": all(context),
            "anchor_found_top": top, "anchor_found_context": context,
            "top_chunk_ids": [item["id"] for item in candidates],
            "top_headings": [item["heading_path"][-1] for item in candidates],
            "retrieval_ms": candidates[0]["retrieval_ms"] if candidates else None}


def main() -> None:
    manifest = load_manifest(ROOT / "scenarios" / "crewai" / "manifest.json")
    db_path = index_path(ROOT, manifest, 1800)
    questions = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(questions) != 6 or len({item["id"] for item in questions}) != 6:
        raise ValueError("Held-out dataset must contain six unique questions")
    local_cache = ROOT / ".venv" / "hf" / "hub"
    if local_cache.is_dir() and not os.environ.get("HF_HOME"):
        os.environ["HF_HOME"] = str(local_cache.parent)
    model = load_model()
    cached = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.is_file() else {}
    details = []
    for item in questions:
        qid = item["id"]
        fingerprint = sha256(item["question"].encode()).hexdigest()
        decomposition = cached.get(qid)
        if not decomposition or decomposition.get("question_sha256") != fingerprint or \
                decomposition.get("prompt_version") != PROMPT_VERSION:
            load_local_env()
            require_key()
            decomposition = {**decompose_question(item["question"]), "question_sha256": fingerprint}
            cached[qid] = decomposition
            _write_json(CACHE, cached)
        variants = {}
        for strategy in ("vector", "hybrid", "decomposed"):
            candidates = retrieve(db_path, item["question"], strategy,
                                  item["english_query"] if strategy == "hybrid" else None,
                                  TOP_K, model,
                                  decomposition["subqueries"] if strategy == "decomposed" else None)
            variants[strategy] = _evaluate_variant(item, candidates)
        details.append({"id": qid, "question": item["question"], "anchors": item["evidence"],
                        "auto_subqueries": decomposition["subqueries"],
                        "decomposition_model": decomposition["model"],
                        "decomposition_usage": decomposition["usage"],
                        "variants": variants})
        print(f"{qid}: " + ", ".join(f"{name}={int(variants[name]['all_found_context'])}"
                                    for name in variants), flush=True)
    summary = {strategy: {
        "all_anchor_recall_at_10": sum(item["variants"][strategy]["all_found_top"] for item in details),
        "all_anchor_context_hit_at_3": sum(item["variants"][strategy]["all_found_context"] for item in details),
    } for strategy in ("vector", "hybrid", "decomposed")}
    report = {
        "scenario": manifest["id"], "source_commit": manifest["upstream_commit"],
        "dataset_sha256": sha256(DATASET.read_bytes()).hexdigest(),
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "index": str(db_path.relative_to(ROOT)),
        "embedding_model": f"{MODEL_ID}@{MODEL_REVISION}",
        "questions": len(details), "top_k": TOP_K, "context_k": CONTEXT_K,
        "total_decomposition_tokens": sum(item["decomposition_usage"].get("total_tokens", 0)
                                          for item in details),
        "summary": summary, "details": details,
    }
    _write_json(OUTPUT, report)
    print(json.dumps({"summary": summary, "total_decomposition_tokens": report["total_decomposition_tokens"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
