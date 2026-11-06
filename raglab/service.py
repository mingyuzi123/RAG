"""Shared retrieval and answer workflow for the CLI and local web UI."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import os
import time

from .generation import generate_answer
from .context_window import select_context
from .hybrid import reciprocal_rank_fusion
from .multiquery import search_subqueries
from .store import build_index, index_path, search
from .vector import build_vectors, search_vectors, vector_path


STRATEGIES = ("bm25", "vector", "hybrid", "decomposed")
CONTEXT_POLICIES = ("top_k", "targeted_window")


def validate_request(question: str, strategy: str, english_query: str | None,
                     top_k: int, context_k: int | None = None,
                     subqueries: list[str] | None = None) -> None:
    if not question.strip():
        raise ValueError("Question cannot be empty")
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy}")
    if not 1 <= top_k <= 30:
        raise ValueError("top_k must be between 1 and 30")
    if context_k is not None and not 1 <= context_k <= top_k:
        raise ValueError("context_k must be between 1 and top_k")
    if strategy == "hybrid" and not (english_query or "").strip():
        raise ValueError("Hybrid retrieval needs an English keyword query")
    if strategy == "decomposed" and (not isinstance(subqueries, list) or
            not 2 <= len(subqueries) <= 4 or
            any(not isinstance(item, str) or not item.strip() for item in subqueries)):
        raise ValueError("Decomposed retrieval needs 2 to 4 nonempty subquestions")


def retrieve(db_path: Path, question: str, strategy: str = "bm25",
             english_query: str | None = None, top_k: int = 5, model=None,
             subqueries: list[str] | None = None) -> list[dict]:
    validate_request(question, strategy, english_query, top_k, subqueries=subqueries)
    if not db_path.is_file():
        raise FileNotFoundError("Keyword index missing. Run python -m raglab index")
    if strategy == "bm25":
        return search(db_path, english_query or question, top_k)
    if not vector_path(db_path).is_file():
        raise FileNotFoundError("Vector index missing. Run python -m raglab vector-index")
    if strategy == "vector":
        return search_vectors(db_path, question, top_k, model)
    if strategy == "decomposed":
        return search_subqueries(db_path, subqueries, top_k, model)
    pool = max(top_k, 20)
    keyword = search(db_path, english_query, pool)
    vector = search_vectors(db_path, question, pool, model)
    return reciprocal_rank_fusion(keyword, vector, top_k)


def compare(db_path: Path, question: str, english_query: str, top_k: int = 10,
            model=None) -> dict:
    validate_request(question, "hybrid", english_query, top_k)
    if not vector_path(db_path).is_file():
        raise FileNotFoundError("Vector index missing. Run python -m raglab vector-index")
    pool = max(top_k, 20)
    keyword = search(db_path, english_query, pool)
    vector = search_vectors(db_path, question, pool, model)
    hybrid = reciprocal_rank_fusion(keyword, vector, top_k)
    return {"bm25": keyword[:top_k], "vector": vector[:top_k], "hybrid": hybrid}


def retrieve_targeted_window(root: Path, manifest: dict, db_path: Path,
                             question: str, english_query: str, top_k: int,
                             context_k: int, model=None, max_chars: int = 1800) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Keep the baseline rank trace while selecting child/parent/neighbor evidence."""
    validate_request(question, "hybrid", english_query, top_k, context_k)
    baseline = retrieve(db_path, question, "hybrid", english_query, top_k, model)
    child_path = index_path(root, manifest, max_chars, definition_items=True)
    if not child_path.is_file():
        build_index(root, manifest, max_chars, definition_items=True)
    if not vector_path(child_path).is_file():
        build_vectors(child_path, model)
    child_hits = retrieve(child_path, question, "hybrid", english_query, top_k, model)
    selected, window = select_context(db_path, child_path, baseline, child_hits,
                                      english_query, context_k)
    return baseline, child_hits, selected, window


def answer(root: Path, manifest: dict, db_path: Path, question: str,
           strategy: str = "bm25", english_query: str | None = None,
           top_k: int = 5, context_k: int = 3, model=None,
           generation_model: str | None = None,
           subqueries: list[str] | None = None,
           context_policy: str = "top_k", max_chars: int = 1800,
           query_metadata: dict | None = None) -> dict:
    validate_request(question, strategy, english_query, top_k, context_k, subqueries)
    if context_policy not in CONTEXT_POLICIES:
        raise ValueError(f"Unknown context policy: {context_policy}")
    if context_policy == "targeted_window":
        if strategy != "hybrid":
            raise ValueError("Targeted window currently requires hybrid RRF retrieval")
        candidates, child_candidates, selected, window = retrieve_targeted_window(
            root, manifest, db_path, question, english_query or "", top_k, context_k, model, max_chars)
    else:
        candidates = retrieve(db_path, question, strategy, english_query, top_k, model, subqueries)
        selected = candidates[:context_k]
        child_candidates, window = [], None
    started = time.perf_counter()
    failure = None
    try:
        result = generate_answer(question, selected, generation_model)
    except Exception as exc:
        failure = exc
        result = {"answer": "", "usage": {}, "cited_numbers": [],
                  "citation_numbers_valid": False, "error": str(exc)}
    result["sources"] = [
        {"number": number, "url": item["source_url"], "heading_path": item["heading_path"],
         "chunk_id": item["id"]}
        for number, item in enumerate(selected, 1)
    ]
    trace = {
        "request_id": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario": manifest["id"], "source_commit": manifest["upstream_commit"],
        "index": str(db_path.relative_to(root)), "strategy": strategy,
        "context_policy": context_policy,
        "question": question, "search_query": question if strategy == "vector" else (english_query or question),
        "query_metadata": query_metadata or {"source": "manual" if english_query else "original_question"},
        "subqueries": subqueries or [],
        "candidates": candidates, "child_candidates": child_candidates,
        "selected_chunks": selected, "window": window,
        "selected_chunk_ids": [item["id"] for item in selected],
        "result": result, "generation_ms": round((time.perf_counter() - started) * 1000, 2),
        "status": "failed" if failure else "completed",
    }
    path = root / "logs" / "requests.jsonl"
    path.parent.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8") as log:
        log.write(json.dumps(trace, ensure_ascii=False) + "\n")
    if failure:
        raise failure
    return trace


def recent_traces(root: Path, limit: int = 20) -> list[dict]:
    path = root / "logs" / "requests.jsonl"
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(line) for line in reversed(lines) if line.strip()]


def status(root: Path, manifest: dict, max_chars: int = 1800) -> dict:
    db_path = index_path(root, manifest, max_chars)
    return {"scenario": manifest["id"], "source_commit": manifest["upstream_commit"],
            "keyword_ready": db_path.is_file(), "vector_ready": vector_path(db_path).is_file(),
            "deepseek_key_set": bool(os.environ.get("DEEPSEEK_API_KEY"))}
