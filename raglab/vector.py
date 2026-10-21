"""Optional multilingual E5 retrieval over the same traceable SQLite chunks."""

from contextlib import closing
from hashlib import sha256
from pathlib import Path
import json
import os
import sqlite3
import time


MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "f470c6a1a906014160ece1968c484b275f0396de"
VECTOR_VERSION = "e5-prefix-heading-v1"


def load_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("Install optional vector dependencies: python -m pip install -r requirements-vector.txt") from exc
    return SentenceTransformer(MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False)


def vector_path(db_path: Path) -> Path:
    digest = sha256(f"{MODEL_ID}@{MODEL_REVISION}:{VECTOR_VERSION}".encode()).hexdigest()[:10]
    return db_path.with_name(f"{db_path.stem}-e5-{digest}.npz")


def _rows(db_path: Path) -> list[sqlite3.Row]:
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute("SELECT * FROM chunks ORDER BY id").fetchall()


def build_vectors(db_path: Path, model=None) -> tuple[Path, int]:
    import numpy as np

    target = vector_path(db_path)
    if target.exists():
        with np.load(target, allow_pickle=False) as saved:
            return target, len(saved["ids"])
    rows = _rows(db_path)
    if not rows:
        raise ValueError("keyword index has no chunks")
    model = model or load_model()
    passages = ["passage: " + " > ".join(json.loads(row["heading_path"])) + "\n" + row["text"]
                for row in rows]
    vectors = np.asarray(model.encode(passages, batch_size=16, normalize_embeddings=True,
                                      convert_to_numpy=True, show_progress_bar=True), dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] != len(rows):
        raise ValueError("embedding model returned an unexpected shape")
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as output:
            np.savez_compressed(output, ids=np.asarray([row["id"] for row in rows]), vectors=vectors)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target, len(rows)


def search_vectors(db_path: Path, question: str, limit: int = 5, model=None) -> list[dict]:
    import numpy as np

    target = vector_path(db_path)
    if not target.is_file():
        raise FileNotFoundError("Vector index missing. First run: python -m raglab vector-index")
    model = model or load_model()
    started = time.perf_counter()
    query = np.asarray(model.encode(["query: " + question], normalize_embeddings=True,
                                    convert_to_numpy=True), dtype=np.float32)[0]
    with np.load(target, allow_pickle=False) as saved:
        ids = saved["ids"]
        vectors = saved["vectors"]
        if vectors.shape[1] != query.shape[0]:
            raise ValueError("query and index embedding dimensions differ")
        scores = vectors @ query
        order = np.argsort(-scores, kind="stable")[:limit]
        ranked = [(str(ids[index]), float(scores[index])) for index in order]
    rows = {row["id"]: row for row in _rows(db_path)}
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return [
        {"id": chunk_id, "rank": rank, "score": round(score, 6),
         "source_path": rows[chunk_id]["source_path"],
         "heading_path": json.loads(rows[chunk_id]["heading_path"]),
         "start_line": rows[chunk_id]["start_line"], "end_line": rows[chunk_id]["end_line"],
         "source_url": rows[chunk_id]["source_url"], "text": rows[chunk_id]["text"],
         "retrieval_ms": elapsed_ms}
        for rank, (chunk_id, score) in enumerate(ranked, 1)
    ]
