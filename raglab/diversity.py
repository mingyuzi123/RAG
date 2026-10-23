"""Select a compact context by balancing retrieval rank and passage diversity."""


def select_diverse(candidates: list[dict], vectors: dict, limit: int,
                   relevance_weight: float = 0.7, max_chars: int | None = None) -> list[dict]:
    """Greedy MMR-style selection from an already ranked candidate list.

    Retrieval rank is mapped linearly to [1, 0]. Passage cosine similarity is
    used only as a redundancy penalty. No gold labels enter this selection.
    """
    if not 0 <= relevance_weight <= 1:
        raise ValueError("relevance_weight must be between 0 and 1")
    if limit < 1:
        raise ValueError("limit must be positive")
    if max_chars is not None and max_chars < 1:
        raise ValueError("max_chars must be positive")
    if len({item["id"] for item in candidates}) != len(candidates):
        raise ValueError("candidate IDs must be unique")
    missing = [item["id"] for item in candidates if item["id"] not in vectors]
    if missing:
        raise ValueError(f"missing vectors for {len(missing)} candidates")

    selected = []
    remaining = list(enumerate(candidates))
    used_chars = 0
    denominator = max(len(candidates) - 1, 1)
    while remaining and len(selected) < limit:
        feasible = [(index, item) for index, item in remaining
                    if max_chars is None or used_chars + len(item["text"]) <= max_chars]
        if not feasible:
            break

        def score(index, item):
            relevance = 1 - index / denominator
            redundancy = max((max(0.0, float(vectors[item["id"]] @ vectors[prior["id"]]))
                              for prior in selected), default=0.0)
            return relevance_weight * relevance - (1 - relevance_weight) * redundancy

        index, choice = max(feasible, key=lambda pair: (score(*pair), -pair[0]))
        selected.append(choice)
        used_chars += len(choice["text"])
        remaining = [(position, item) for position, item in remaining if position != index]
    return selected
