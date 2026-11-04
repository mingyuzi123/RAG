"""Build an isolated scenario index with definition items split into small chunks."""

from argparse import ArgumentParser
from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.store import build_index, load_manifest  # noqa: E402
from raglab.vector import build_vectors, load_model  # noqa: E402


def main() -> None:
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("--scenario", type=Path, default=ROOT / "scenarios" / "pydantic" / "manifest.json")
    args = cli.parse_args()
    cache = ROOT / ".venv" / "hf"
    if cache.is_dir() and not os.environ.get("HF_HOME"):
        os.environ["HF_HOME"] = str(cache)
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    manifest = load_manifest(args.scenario)
    db_path, count = build_index(ROOT, manifest, definition_items=True)
    print(f"Experimental keyword index: {db_path.relative_to(ROOT)}; chunks={count}", flush=True)
    vector, vector_count = build_vectors(db_path, load_model())
    print(f"Experimental vector index: {vector.relative_to(ROOT)}; chunks={vector_count}", flush=True)


if __name__ == "__main__":
    main()
