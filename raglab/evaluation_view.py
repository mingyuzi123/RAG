"""Read fixed retrieval reports for the local learning dashboard."""

from pathlib import Path
import json


def _load_report(root: Path, manifest: dict, item: dict) -> dict:
    reports_root = (root / "reports").resolve()
    path = (root / item["path"]).resolve()
    if not path.is_relative_to(reports_root) or path.suffix != ".json":
        raise ValueError("evaluation report must be a JSON file under reports/")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report["scenario"] != manifest["id"] or report["source_commit"] != manifest["upstream_commit"]:
        raise ValueError(f"evaluation report source version differs: {item['path']}")
    return report


def load_dashboard(root: Path, manifest: dict, ui: dict) -> dict:
    """Classify fixed questions by candidate and final-context evidence coverage."""
    configured = ui.get("evaluation_reports", [])
    if not configured:
        return {"strategies": [], "questions": [], "note": "This scenario has no evaluation reports"}
    if len({item["id"] for item in configured}) != len(configured):
        raise ValueError("evaluation report IDs must be unique")
    strategies = []
    questions: dict[str, dict] = {}
    expected_ids = None
    expected_k = None
    for item in configured:
        report = _load_report(root, manifest, item)
        current_k = (report["top_k"], report["context_k"])
        if expected_k is not None and current_k != expected_k:
            raise ValueError("evaluation reports use different Top K or context K")
        expected_k = current_k
        details = [detail for detail in report["details"]
                   if detail.get("answerability") != "unanswerable"]
        ids = [detail["id"] for detail in details]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate question IDs in evaluation report")
        if expected_ids is not None and set(ids) != expected_ids:
            raise ValueError("evaluation reports use different question sets")
        expected_ids = set(ids)
        top_hits = 0
        context_hits = 0
        for detail in details:
            anchors = detail["anchors"]
            top_flags = detail["anchor_found_top"]
            context_flags = detail["anchor_found_context"]
            if len(anchors) != len(top_flags) or len(anchors) != len(context_flags):
                raise ValueError("evidence flags do not match anchor count")
            if any(context and not top for top, context in zip(top_flags, context_flags)):
                raise ValueError("context evidence cannot be absent from candidates")
            top = all(top_flags)
            context = all(context_flags)
            top_hits += top
            context_hits += context
            missing_top = [anchor["heading"] for anchor, found in zip(anchors, top_flags) if not found]
            missing_context = [anchor["heading"] for anchor, found in zip(anchors, context_flags) if not found]
            entry = questions.setdefault(detail["id"], {"id": detail["id"],
                                                           "evidence": anchors, "results": {}})
            if entry["evidence"] != anchors:
                raise ValueError("evaluation reports use different evidence annotations")
            entry["results"][item["id"]] = {
                "state": "context" if context else ("candidate" if top else "missing"),
                "missing_top": missing_top, "missing_context": missing_context,
            }
        strategies.append({"id": item["id"], "label": item["label"],
                           "candidate_hits": top_hits, "context_hits": context_hits,
                           "question_count": len(details), "top_k": current_k[0],
                           "context_k": current_k[1]})
    return {"strategies": strategies,
            "questions": sorted(questions.values(), key=lambda value: value["id"]),
            "note": "Section-level annotations; coverage does not prove answer correctness."}
