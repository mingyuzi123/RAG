"""Save the manual expected-point review of the frozen parent-context suite."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Manual review against the prewritten expected points and saved answers.
# An answer passes only when every expected point is present with a valid citation;
# for unanswerable items, it must explicitly state the excerpts are insufficient.
MISSING = {
    ("P01", "baseline"): "无默认值字段必填仅作为推断，缺少摘录直接支持",
    ("P01", "parent"): "与基线相同：无默认值字段必填缺少摘录直接支持",
    ("P06", "baseline"): "未回答 after 在内部校验之后运行",
    ("C04", "baseline"): "未说明 Agent/Task tools 两侧的完整作用范围",
    ("C04", "parent"): "仍缺 Agent/Task tools 两侧的完整作用范围",
    ("C10", "baseline"): "未明确回答 @start 是 Flow 入口",
    ("C10", "parent"): "与基线相同：未明确回答 @start 是 Flow 入口",
    ("H01", "baseline"): "Sequential 只回答顺序，未回答前一个任务输出作为后续上下文",
    ("H01", "parent"): "Sequential 只回答顺序，未回答前一个任务输出作为后续上下文",
    ("H03", "baseline"): "未明确回答 output_pydantic 通过指定模型验证",
    ("H03", "parent"): "与基线相同：未明确回答 output_pydantic 通过指定模型验证",
}


def main() -> None:
    changed = json.loads((ROOT / "reports/parent-answer-suite.json").read_text(encoding="utf-8"))
    unchanged = json.loads((ROOT / "reports/parent-answer-unchanged.json").read_text(encoding="utf-8"))
    questions = {}
    for row in changed:
        key = row["id"]
        questions.setdefault(key, {})[row["variant"]] = row
    for row in unchanged:
        questions[row["id"]] = {"baseline": row, "parent": row}
    assert len(questions) == 35 and len(changed) == 16 and len(unchanged) == 27
    records = []
    for qid in sorted(questions):
        pair = questions[qid]
        assert set(pair) == {"baseline", "parent"}
        for variant, answer in pair.items():
            answerability = "unanswerable" if not answer["expected_points"] else "answerable"
            reason = MISSING.get((qid, variant))
            records.append({"id": qid, "variant": variant, "answerability": answerability,
                            "complete": reason is None, "reason_if_incomplete": reason,
                            "citation_numbers_valid": answer["citation_numbers_valid"]})
    summary = {}
    for variant in ("baseline", "parent"):
        subset = [row for row in records if row["variant"] == variant]
        summary[variant] = {"all": sum(row["complete"] for row in subset),
                            "all_total": len(subset),
                            "answerable": sum(row["complete"] for row in subset if row["answerability"] == "answerable"),
                            "answerable_total": sum(row["answerability"] == "answerable" for row in subset),
                            "unanswerable": sum(row["complete"] for row in subset if row["answerability"] == "unanswerable")}
        summary[variant]["no_valid_citation_number"] = sum(not row["citation_numbers_valid"] for row in subset)
    result = {"method": "manual expected-point completeness with citation-number check",
              "limitation": "Single answer per unique prompt; citation numbers checked mechanically, semantic support manually reviewed on changed cases.",
              "summary": summary, "reviews": records}
    path = ROOT / "reports/parent-answer-grades.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
