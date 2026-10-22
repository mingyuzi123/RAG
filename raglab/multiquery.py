"""Coverage-first retrieval from several explicit subquestions."""

from .vector import search_vectors


def interleave_results(groups: list[list[dict]], limit: int) -> list[dict]:
    """Take turns across intents, keeping each chunk once and recording its ranks."""
    if not groups or limit < 1:
        return []
    unique: dict[str, dict] = {}
    order: list[str] = []
    for rank_index in range(max(map(len, groups), default=0)):
        for query_index, candidates in enumerate(groups, 1):
            if rank_index >= len(candidates):
                continue
            item = candidates[rank_index]
            if item["id"] not in unique:
                unique[item["id"]] = {**item, "subquery_ranks": {}}
                order.append(item["id"])
            unique[item["id"]]["subquery_ranks"][f"query_{query_index}"] = item["rank"]
    elapsed = round(sum(candidates[0]["retrieval_ms"] for candidates in groups if candidates), 2)
    return [{**unique[chunk_id], "rank": rank, "retrieval_ms": elapsed}
            for rank, chunk_id in enumerate(order[:limit], 1)]


def search_subqueries(db_path, subqueries: list[str], limit: int = 10, model=None) -> list[dict]:
    pool = max(limit, 20)
    groups = [search_vectors(db_path, question, pool, model) for question in subqueries]
    return interleave_results(groups, limit)
