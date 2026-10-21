"""Rank fusion for keyword and vector candidate lists."""

from .store import search
from .vector import search_vectors


def reciprocal_rank_fusion(keyword: list[dict], vector: list[dict], limit: int,
                           constant: int = 60) -> list[dict]:
    merged: dict[str, dict] = {}
    for name, candidates in (("bm25", keyword), ("vector", vector)):
        for item in candidates:
            entry = merged.setdefault(item["id"], {**item, "score": 0.0, "retriever_ranks": {}})
            entry["score"] += 1 / (constant + item["rank"])
            entry["retriever_ranks"][name] = item["rank"]
    ordered = sorted(merged.values(), key=lambda item: (-item["score"], item["id"]))[:limit]
    elapsed = round((keyword[0]["retrieval_ms"] if keyword else 0) +
                    (vector[0]["retrieval_ms"] if vector else 0), 2)
    return [{**item, "rank": rank, "score": round(item["score"], 8), "retrieval_ms": elapsed}
            for rank, item in enumerate(ordered, 1)]


def search_hybrid(db_path, question: str, english_query: str, limit: int = 5,
                  model=None) -> list[dict]:
    pool = max(limit, 20)
    return reciprocal_rank_fusion(search(db_path, english_query, pool),
                                  search_vectors(db_path, question, pool, model), limit)
