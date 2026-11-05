"""Compare manual expected-point grades after conditional merge and targeted window."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    baseline = json.loads((ROOT / "reports/parent-answer-grades.json").read_text(encoding="utf-8"))
    auto_answers = {row["id"]: row for row in json.loads(
        (ROOT / "reports/auto-merge-answers.json").read_text(encoding="utf-8"))}
    window_answers = {row["id"]: row for row in json.loads(
        (ROOT / "reports/targeted-window-answers.json").read_text(encoding="utf-8"))}
    assert len(auto_answers) == 9 and len(window_answers) == 4
    baseline_rows = {row["id"]: row for row in baseline["reviews"] if row["variant"] == "baseline"}
    assert len(baseline_rows) == 35
    # Manual review of the saved answers against the existing expected points.
    auto_incomplete = {"C04": "仍未召回 Agent/Task tools 两侧的范围证据",
                       "H01": "条件合并单独使用时仍缺前一任务输出作为后续上下文"}
    result = []
    for qid, prior in sorted(baseline_rows.items()):
        if qid in window_answers:
            row = window_answers[qid]
            verdict = True
            reason = "新增邻块补齐答案要点" if not prior["complete"] else "新增邻块后原要点仍完整"
            source = "targeted-window-answers.json"
        elif qid in auto_answers:
            row = auto_answers[qid]
            verdict = qid not in auto_incomplete
            reason = auto_incomplete.get(qid, "条件合并后答案要点完整")
            source = "auto-merge-answers.json"
        else:
            row = None
            verdict = prior["complete"]
            reason = "上下文与基线完全相同，同一次回答计入两方案"
            source = "parent-answer-unchanged.json"
        result.append({"id": qid, "answerability": prior["answerability"],
                       "baseline_complete": prior["complete"], "window_complete": verdict,
                       "reason": reason, "answer_source": source,
                       "citation_numbers_valid": row["citation_numbers_valid"] if row else prior["citation_numbers_valid"]})
    answerable = [row for row in result if row["answerability"] == "answerable"]
    summary = {"all": {"baseline": sum(row["baseline_complete"] for row in result),
                       "window": sum(row["window_complete"] for row in result), "total": len(result)},
               "answerable": {"baseline": sum(row["baseline_complete"] for row in answerable),
                              "window": sum(row["window_complete"] for row in answerable),
                              "total": len(answerable)},
               "gained": [row["id"] for row in result if row["window_complete"] and not row["baseline_complete"]],
               "lost": [row["id"] for row in result if row["baseline_complete"] and not row["window_complete"]]}
    output = {"method": "manual expected-point completeness on saved single-run answers",
              "summary": summary, "reviews": result}
    path = ROOT / "reports/targeted-window-grades.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
