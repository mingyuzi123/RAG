"""Resolve scenario defaults and keyword queries for each request entry point."""

from .query_rewrite import rewrite_query
from .service import CONTEXT_POLICIES, STRATEGIES
from .store import WORDS


def resolve_runtime(manifest: dict, **overrides) -> dict:
    language = manifest.get("language", "mixed")
    defaults = {"strategy": "vector", "top_k": 10, "context_k": 3,
                "context_policy": "top_k", "auto_rewrite": language == "en"}
    configured = manifest.get("retrieval", {})
    if not isinstance(configured, dict) or configured.keys() - defaults.keys():
        raise ValueError("retrieval must contain only strategy, top_k, context_k, context_policy and auto_rewrite")
    settings = {**defaults, **configured}
    _validate(settings)
    settings.update({key: value for key, value in overrides.items() if value is not None})
    if overrides.get("context_k") is None and type(settings["top_k"]) is int:
        settings["context_k"] = min(settings["context_k"], settings["top_k"])
    _validate(settings)
    return {"language": language, **settings}


def _validate(settings: dict) -> None:
    if settings["strategy"] not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {settings['strategy']}")
    if type(settings["top_k"]) is not int or not 1 <= settings["top_k"] <= 30:
        raise ValueError("top_k must be an integer between 1 and 30")
    if type(settings["context_k"]) is not int or not 1 <= settings["context_k"] <= settings["top_k"]:
        raise ValueError("context_k must be an integer between 1 and top_k")
    if settings["context_policy"] not in CONTEXT_POLICIES:
        raise ValueError(f"Unknown context policy: {settings['context_policy']}")
    if settings["context_policy"] == "targeted_window" and settings["strategy"] != "hybrid":
        raise ValueError("Targeted window requires hybrid RRF retrieval")
    if type(settings["auto_rewrite"]) is not bool:
        raise ValueError("auto_rewrite must be a boolean")


def resolve_keyword_query(question: str, settings: dict, english_query: str | None = None,
                          metadata: dict | None = None) -> tuple[str | None, dict]:
    if not question.strip():
        raise ValueError("Question cannot be empty")
    if settings["strategy"] in ("vector", "decomposed"):
        return None, {"source": "original_question"}
    if english_query and english_query.strip():
        return english_query.strip(), metadata or {"source": "manual"}
    if question.isascii() and WORDS.search(question):
        return question, {"source": "original_question"}
    if settings["auto_rewrite"]:
        result = rewrite_query(question)
        return result["query"], {"source": "auto", **{k: v for k, v in result.items() if k != "query"}}
    raise ValueError("请提供英文检索词、开启自动改写，或使用 E5 检索原问题。")
