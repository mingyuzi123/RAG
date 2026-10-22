"""Human answer reviews tied to saved requests and scenario evaluation questions."""

from datetime import datetime, timezone
from pathlib import Path
import json


POINT_VERDICTS = {"supported", "unsupported", "missing"}
CITATION_VERDICTS = {"supported", "unsupported", "unclear", "not_applicable"}
REFUSAL_VERDICTS = {"appropriate", "inappropriate", "not_applicable"}


def latest_reviews(root: Path) -> dict[str, dict]:
    path = root / "logs" / "answer_reviews.jsonl"
    if not path.is_file():
        return {}
    reviews = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            review = json.loads(line)
            reviews[review["request_id"]] = review
    return reviews


def score_review(answerability: str, points: list[str], citation: str,
                 refusal: str) -> str:
    """Apply a deliberately strict rule; labels are still chosen by a human."""
    if answerability == "unanswerable":
        if refusal == "inappropriate" or citation == "unsupported":
            return "fail"
        if refusal == "appropriate" and citation in ("supported", "not_applicable"):
            return "pass"
        return "uncertain"
    if refusal != "not_applicable" or "unsupported" in points or "missing" in points:
        return "fail"
    if citation == "unsupported":
        return "fail"
    if citation == "supported" and points and all(item == "supported" for item in points):
        return "pass"
    return "uncertain"


def save_review(root: Path, scenario_id: str, request_id: str,
                traces: list[dict], examples: list[dict],
                point_verdicts: list[str], citation_verdict: str,
                refusal_verdict: str, note: str = "") -> dict:
    trace = next((item for item in traces if item.get("request_id") == request_id), None)
    if trace is None or trace.get("status") != "completed":
        raise ValueError("找不到已完成的问答请求；请刷新请求记录。")
    if trace.get("scenario") != scenario_id:
        raise ValueError("该问答请求属于其他场景。")
    example = next((item for item in examples if item["question"] == trace["question"]), None)
    if example is None:
        raise ValueError("该请求的问题与评测集不一致，暂无法按预期要点评审。")
    expected = example.get("expected_points", [])
    if not isinstance(point_verdicts, list) or len(point_verdicts) != len(expected) or any(
            item not in POINT_VERDICTS for item in point_verdicts):
        raise ValueError("请逐条判断所有预期要点。")
    if citation_verdict not in CITATION_VERDICTS or refusal_verdict not in REFUSAL_VERDICTS:
        raise ValueError("引用或拒答判断无效。")
    if not isinstance(note, str) or len(note) > 2000:
        raise ValueError("评审备注最多 2000 字。")
    if example["answerability"] == "answerable" and refusal_verdict == "appropriate":
        raise ValueError("可回答题不能标为合理拒答；如证据不足，请将该次问答记为失败。")
    if example["answerability"] == "unanswerable" and point_verdicts:
        raise ValueError("无答案题没有预期答案要点。")
    review = {
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario": trace["scenario"],
        "source_commit": trace["source_commit"],
        "index": trace["index"],
        "example_id": example["id"],
        "answerability": example["answerability"],
        "point_reviews": [{"point": point, "verdict": verdict}
                          for point, verdict in zip(expected, point_verdicts)],
        "citation_verdict": citation_verdict,
        "refusal_verdict": refusal_verdict,
        "verdict": score_review(example["answerability"], point_verdicts,
                                citation_verdict, refusal_verdict),
        "note": note.strip(),
    }
    path = root / "logs" / "answer_reviews.jsonl"
    path.parent.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(review, ensure_ascii=False) + "\n")
    return review
