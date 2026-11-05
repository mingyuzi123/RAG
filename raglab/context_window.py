"""Conditional child-parent merging and one query-relevant source window."""

from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3


STOP = {"what", "when", "where", "which", "with", "from", "this", "that", "into", "should",
        "between", "using", "versus", "difference", "about", "does", "default", "model",
        "process", "task", "agent", "field", "flow", "crewai", "pydantic"}


def terms(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z][a-z0-9_]*", value.casefold())
            if len(word) >= 4 and word not in STOP}


def load_chunks(path: Path) -> dict[str, dict]:
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute("SELECT * FROM chunks")]
    return {row["id"]: {**row, "heading_path": json.loads(row["heading_path"])} for row in rows}


def parent_for(child: dict, parents: dict[str, dict]) -> dict:
    same = [row for row in parents.values() if row["source_path"] == child["source_path"]
            and row["heading_path"] == child["heading_path"]]
    containing = [row for row in same if row["start_line"] <= child["start_line"]
                  and row["end_line"] >= child["end_line"]]
    if len(containing) == 1:
        return containing[0]
    candidates = containing or same
    if not candidates:
        raise ValueError(f"No parent for {child['source_path']} L{child['start_line']}")
    return max(candidates, key=lambda row: (max(0, min(row["end_line"], child["end_line"])
        - max(row["start_line"], child["start_line"]) + 1), -len(row["text"])))


def select_context(parent_path: Path, child_path: Path, baseline_hits: list[dict],
                   child_hits: list[dict], english_query: str, context_k: int = 3) -> tuple[list[dict], dict]:
    """Return source-traceable evidence; never use gold labels in selection."""
    if not baseline_hits:
        return [], {"baseline_chunk_ids": [], "child_candidate_ids": [], "selected_chunk_ids": [],
                    "selected_origins": [], "character_budget": 0, "selected_characters": 0,
                    "neighbor_considered": None}
    if context_k < 1:
        raise ValueError("context_k must be positive")
    parents = load_chunks(parent_path)
    children = load_chunks(child_path)
    parent_ids = {chunk_id: parent_for(row, parents)["id"] for chunk_id, row in children.items()}
    parent_sizes = Counter(parent_ids.values())
    child_ids = [hit["id"] for hit in child_hits]
    hit_counts = Counter(parent_ids[chunk_id] for chunk_id in child_ids)
    budget = sum(len(parents[hit["id"]]["text"]) for hit in baseline_hits[:context_k])

    merged = []
    merged_parents = set()
    seen = set()
    used = 0
    for child_id in child_ids:
        parent_id = parent_ids[child_id]
        if parent_id in merged_parents:
            continue
        do_merge = hit_counts[parent_id] >= 2 and hit_counts[parent_id] / parent_sizes[parent_id] > 0.5
        candidate = parents[parent_id] if do_merge else children[child_id]
        if do_merge and used + len(candidate["text"]) > budget:
            candidate = children[child_id]
            do_merge = False
        if candidate["id"] in seen or used + len(candidate["text"]) > budget:
            continue
        merged.append({**candidate, "context_origin": "merged_parent" if do_merge else "child_hit"})
        seen.add(candidate["id"])
        used += len(candidate["text"])
        if do_merge:
            merged_parents.add(parent_id)
        if len(merged) == context_k:
            break

    query_terms = terms(english_query)
    existing_text = set().union(*(terms(row["text"]) for row in merged))
    existing_headings = set().union(*(terms(" ".join(row["heading_path"])) for row in merged))
    by_file: dict[str, list[dict]] = {}
    for row in parents.values():
        by_file.setdefault(row["source_path"], []).append(row)
    for group in by_file.values():
        group.sort(key=lambda row: row["start_line"])
    options = []
    for rank, anchor in enumerate(merged):
        parent_id = anchor["id"] if anchor["id"] in parents else parent_ids[anchor["id"]]
        parent = parents[parent_id]
        group = by_file[parent["source_path"]]
        position = next(i for i, row in enumerate(group) if row["id"] == parent_id)
        if position == 0:
            continue
        preceding = group[position - 1]
        if preceding["id"] in {row["id"] for row in merged}:
            continue
        if preceding["heading_path"] == parent["heading_path"]:
            novel = query_terms & (terms(preceding["text"]) - existing_text)
            reason = "same-heading-query-term"
        elif preceding["heading_path"][:-1] == parent["heading_path"][:-1]:
            novel = query_terms & (terms(preceding["heading_path"][-1]) - existing_headings)
            reason = "adjacent-heading-query-term"
        else:
            continue
        if novel:
            options.append((rank, preceding, f"{reason}:{','.join(sorted(novel))}"))
    selected_order = list(merged)
    neighbor_reason = None
    if options:
        rank, preceding, neighbor_reason = min(options, key=lambda item: item[0])
        selected_order.insert(rank + 1, {**preceding, "context_origin": neighbor_reason})
    selected = []
    used = 0
    for row in selected_order:
        if len(selected) == context_k:
            break
        if used + len(row["text"]) <= budget:
            selected.append(row)
            used += len(row["text"])
    for rank, row in enumerate(selected, 1):
        row["rank"] = rank
        row["score"] = row["context_origin"]
    trace = {"baseline_chunk_ids": [hit["id"] for hit in baseline_hits[:context_k]],
             "child_candidate_ids": child_ids, "selected_chunk_ids": [row["id"] for row in selected],
             "selected_origins": [row["context_origin"] for row in selected],
             "character_budget": budget, "selected_characters": used,
             "neighbor_considered": neighbor_reason}
    return selected, trace
