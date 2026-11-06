"""Chinese question to an inspectable English keyword query for BM25."""

import json
import re

from .generation import call_chat


PROMPT_VERSION = "english-keywords-v1"
SYSTEM_PROMPT = (
    "Rewrite the user's question as one concise English keyword query for searching "
    "English technical documentation with BM25. Preserve exact API names, class names, "
    "parameters, and technical terms. Include both sides of a comparison. "
    "Do not answer the question or invent terms, facts, or documentation content. "
    "Return only a JSON object with one key: query. The value must be a single "
    "English search string, not an explanation."
)


def rewrite_query(question: str, model: str | None = None) -> dict:
    if not question.strip():
        raise ValueError("Question cannot be empty")
    response, requested_model = call_chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question.strip()},
    ], model)
    content = (response["choices"][0]["message"].get("content") or "").strip()
    if content.startswith("```") and content.endswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("DeepSeek did not return valid query JSON") from exc
    if not isinstance(parsed, dict) or set(parsed) != {"query"}:
        raise ValueError("DeepSeek query rewrite must contain only query")
    query = parsed["query"]
    if (not isinstance(query, str) or not 3 <= len(query.strip()) <= 180
            or re.search(r"[^\x20-\x7e]", query) or "\n" in query
            or not re.search(r"[A-Za-z]", query)):
        raise ValueError("DeepSeek did not return a usable English keyword query")
    return {"query": query.strip(), "model": response.get("model", requested_model),
            "usage": response.get("usage", {}), "prompt_version": PROMPT_VERSION}
