"""Automatic comparison question decomposition using the configured DeepSeek API."""

import json

from .generation import call_chat


PROMPT_VERSION = "compare-two-intents-v1"
SYSTEM_PROMPT = (
    "You turn a comparison question into exactly two independent retrieval questions. "
    "Each question must target one side of the comparison and be understandable on its own. "
    "Preserve technical names and the language of the user's question. "
    "Do not answer, add facts, mention source documents, or include explanations. "
    "Return only a JSON object with one key, subqueries, containing an array of exactly two strings."
)


def decompose_question(question: str, model: str | None = None) -> dict:
    if not question.strip():
        raise ValueError("Question cannot be empty")
    response, requested_model = call_chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question.strip()},
    ], model)
    content = response["choices"][0]["message"].get("content") or ""
    content = content.strip()
    if content.startswith("```") and content.endswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("DeepSeek did not return valid decomposition JSON") from exc
    if not isinstance(parsed, dict) or set(parsed) != {"subqueries"}:
        raise ValueError("DeepSeek decomposition must contain only subqueries")
    subqueries = parsed["subqueries"]
    if not isinstance(subqueries, list) or len(subqueries) != 2 or any(
            not isinstance(item, str) or not item.strip() or len(item) > 300 for item in subqueries):
        raise ValueError("DeepSeek decomposition must contain two nonempty questions")
    subqueries = [item.strip() for item in subqueries]
    if subqueries[0].casefold() == subqueries[1].casefold():
        raise ValueError("DeepSeek returned duplicate subquestions")
    return {"subqueries": subqueries, "model": response.get("model", requested_model),
            "usage": response.get("usage", {}), "prompt_version": PROMPT_VERSION}
