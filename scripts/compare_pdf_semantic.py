"""Compare paragraph and semantic PDF chunking with fixed E5 retrieval."""

from argparse import ArgumentParser
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.generation import generate_answer
from raglab.local_sources import import_document
from raglab.pdf_source import PDF_SEMANTIC_VERSION, SEMANTIC_MIN_SIMILARITY
from raglab.service import retrieve
from raglab.store import build_index
from raglab.vector import MODEL_ID, MODEL_REVISION, build_vectors, load_model
from scripts.compare_pdf_chunking import covered
from scripts.run_with_deepseek import load_local_env, require_key


# Physical pages and layout-extracted line ranges, annotated against the frozen originals.
# For R07 either the normative rule or the appendix can support the cross-origin point.
EVIDENCE_SPANS = {
    "R01": [[(11, 611, 612), (11, 614, 614)]],
    "R02": [[(10, 540, 541), (25, 1414, 1417)]],
    "R03": [[(17, 971, 976)]],
    "R04": [[(13, 712, 717)]],
    "R05": [[(19, 1085, 1086), (15, 833, 834)]],
    "R06": [[(22, 1228, 1231), (22, 1253, 1256)]],
    "R07": [[(19, 1059, 1060), (19, 1066, 1068)], [(19, 1059, 1060), (32, 1831, 1832)]],
    "R08": [[(21, 1197, 1198), (23, 1289, 1291)]],
    "U01": [[(1, 17, 18)]],
    "U02": [[(1, 27, 34)]],
    "U03": [[(1, 25, 26)]],
    "U04": [[(2, 83, 83)]],
    "U05": [[(2, 87, 87), (2, 89, 89), (2, 92, 92)]],
    "U06": [[(2, 78, 80)]],
    "U07": [[(2, 87, 89)]],
    "U08": [[(1, 59, 59), (2, 74, 75), (2, 77, 77)]],
}


def evidence_complete(hits, case_id):
    alternatives = EVIDENCE_SPANS.get(case_id)
    return any(covered(hits, spans) for spans in alternatives) if alternatives else None


def context_with_budget(hits, context_k, character_budget):
    selected = []
    for hit in hits[:context_k]:
        if len(hit["text"]) <= character_budget:
            selected.append(hit)
            character_budget -= len(hit["text"])
    return selected


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--answer-case", action="append", default=[],
                        help="Also call DeepSeek once per mode for this case ID (repeatable)")
    args = parser.parse_args()
    case_bytes = args.cases.read_bytes()
    spec = json.loads(case_bytes)
    content = args.pdf.read_bytes()
    if sha256(content).hexdigest() != spec["sha256"] or args.output.exists():
        parser.error("use the frozen PDF and a new output path")
    settings = spec["settings"]
    if settings["strategy"] != "vector" or settings["context_policy"] != "top_k":
        parser.error("this comparison expects vector retrieval and direct top-K context")
    if set(args.answer_case) - {case["id"] for case in spec["cases"]}:
        parser.error("--answer-case must be an ID in the supplied case file")
    if args.answer_case:
        if not os.environ.get("DEEPSEEK_API_KEY"):
            load_local_env()
        require_key()

    cache = ROOT / ".venv/hf"
    if (cache / "hub").is_dir():
        os.environ.setdefault("HF_HOME", str(cache))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    root = Path(mkdtemp(prefix="semantic-pdf-", dir=logs))
    name = spec["source"].rsplit("/", 1)[-1]
    manifest = import_document(root, name, None, pdf_base64=b64encode(content).decode("ascii"))
    model = load_model()
    result = {"source": spec["source"], "pdf_sha256": spec["sha256"],
              "case_sha256": sha256(case_bytes).hexdigest(), "settings": settings,
              "model": f"{MODEL_ID}@{MODEL_REVISION}", "semantic_version": PDF_SEMANTIC_VERSION,
              "similarity_threshold": SEMANTIC_MIN_SIMILARITY, "max_chars": 1800,
              "evidence_spans": {case["id"]: EVIDENCE_SPANS.get(case["id"]) for case in spec["cases"]},
              "modes": {}}
    budgets = {}
    for mode in ("paragraph", "semantic"):
        started = perf_counter()
        index, count = build_index(root, {**manifest, "pdf_chunking": mode})
        build_vectors(index, model)
        build_seconds = round(perf_counter() - started, 3)
        rows = []
        result["modes"][mode] = {"chunks": count, "build_seconds": build_seconds, "rows": rows}
        for case in spec["cases"]:
            case_id = case["id"]
            hits = retrieve(index, case["question"], "vector", top_k=settings["top_k"], model=model)
            context = hits[:settings["context_k"]]
            budget = budgets.setdefault(case_id, sum(len(hit["text"]) for hit in context))
            selected = context_with_budget(hits, settings["context_k"], budget)
            row = {
                "id": case_id,
                "candidate_evidence_complete": evidence_complete(hits, case_id),
                "top3_evidence_complete": evidence_complete(context, case_id),
                "context_evidence_complete": evidence_complete(selected, case_id),
                "candidate_pages_complete": set(case["pages"]).issubset(
                    hit["page_number"] for hit in hits) if case["pages"] else None,
                "context_pages_complete": set(case["pages"]).issubset(
                    hit["page_number"] for hit in selected) if case["pages"] else None,
                "character_budget": budget,
                "context_chars": sum(len(hit["text"]) for hit in selected),
                "context_ranks": [hit["rank"] for hit in selected],
                "candidates": hits,
            }
            rows.append(row)
            if case_id in args.answer_case:
                row["generation"] = generate_answer(case["question"], selected)
                args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"{mode}: {case_id} answer generated", flush=True)
        print(f"{mode}: {count} chunks, {build_seconds:.3f}s build", flush=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
