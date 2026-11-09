"""Compare PDF chunk boundaries with frozen NIST development questions and local E5."""

from argparse import ArgumentParser
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.local_sources import import_document
from raglab.service import retrieve
from raglab.store import build_index
from raglab.vector import build_vectors, load_model


# Physical PDF page and extracted line range, checked against the original pages.
SPANS = {"N01": [(2, 54, 55)], "N02": [(4, 103, 107)], "N03": [(5, 129, 130)],
         "N04": [(5, 146, 146), (8, 235, 236)], "N05": [(7, 195, 199)], "N06": [(9, 259, 261)]}


def covered(hits, spans):
    return all(all(any(hit["page_number"] == page and hit["start_line"] <= line <= hit["end_line"]
                       for hit in hits) for line in range(start, end + 1))
               for page, start, end in spans)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads((ROOT / "reports/STAGE5C_PDF_CASES.json").read_text(encoding="utf-8"))
    pdf = args.pdf.read_bytes()
    if sha256(pdf).hexdigest() != spec["sha256"] or args.output.exists():
        parser.error("use the frozen PDF and a new output path")
    cache = ROOT / ".venv/hf"
    if (cache / "hub").is_dir():
        os.environ.setdefault("HF_HOME", str(cache))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    root = Path(mkdtemp(prefix="pdf-chunking-", dir=logs))
    manifest = import_document(root, "NIST.SP.1300.pdf", None, pdf_base64=b64encode(pdf).decode("ascii"))
    model = load_model()
    results = {"pdf_sha256": spec["sha256"], "evidence_spans": SPANS, "modes": {}}
    for mode in ("paragraph", "pack_short"):
        path, count = build_index(root, {**manifest, "pdf_chunking": mode})
        build_vectors(path, model)
        rows = []
        for case in spec["cases"]:
            spans = SPANS.get(case["id"])
            if spans is None:
                continue
            hits = retrieve(path, case["question"], "vector", top_k=10, model=model)
            rows.append({"id": case["id"], "covered_top10": covered(hits, spans),
                         "covered_top3": covered(hits[:3], spans),
                         "top3": [{"page": hit["page_number"], "start": hit["start_line"],
                                   "end": hit["end_line"], "visible_chars": len(" ".join(hit["text"].split()))}
                                  for hit in hits[:3]],
                         "overlapping_ranks": [hit["rank"] for hit in hits if any(
                             hit["page_number"] == page and hit["start_line"] <= end and hit["end_line"] >= start
                             for page, start, end in spans)]})
        results["modes"][mode] = {"chunks": count, "index": path.name, "rows": rows}
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
