"""SQLite FTS5 keyword baseline, with versioned index files."""

from hashlib import sha256
from contextlib import closing
from pathlib import Path
import json
import os
import re
import sqlite3
import subprocess
import time

from .corpus import Chunk, chunk_mdx


PARSER_VERSION = "mdx-heading-table-row-v3"
WORDS = re.compile(r"[A-Za-z0-9_]+")


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = {"id", "upstream_commit", "local_checkout", "files", "source_url_template"}
    missing = required - manifest.keys()
    if missing:
        raise ValueError(f"manifest missing fields: {', '.join(sorted(missing))}")
    return manifest


def index_path(root: Path, manifest: dict, max_chars: int) -> Path:
    settings = {"scenario": manifest["id"], "commit": manifest["upstream_commit"],
                "files": manifest["files"], "max_chars": max_chars, "parser": PARSER_VERSION}
    digest = sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:12]
    return root / "indexes" / manifest["id"] / f"bm25-{digest}.db"


def _check_source(root: Path, manifest: dict) -> Path:
    source_root = (root / manifest["local_checkout"]).resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"source checkout missing; run python scripts/fetch_scenario_docs.py --scenario <manifest.json>: {source_root}")
    actual = subprocess.check_output(
        ["git", "-c", f"safe.directory={source_root.as_posix()}", "-C", str(source_root), "rev-parse", "HEAD"],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()
    if actual != manifest["upstream_commit"]:
        raise ValueError(f"source commit differs: expected {manifest['upstream_commit']}, got {actual}")
    return source_root


def build_index(root: Path, manifest: dict, max_chars: int = 1800) -> tuple[Path, int]:
    source_root = _check_source(root, manifest)
    target = index_path(root, manifest, max_chars)
    if target.exists():
        with closing(sqlite3.connect(target)) as db:
            count = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return target, count
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    chunks: list[Chunk] = []
    for relative in manifest["files"]:
        source_file = (source_root / relative).resolve()
        if not source_file.is_relative_to(source_root) or not source_file.is_file():
            raise FileNotFoundError(f"invalid or missing source: {relative}")
        chunks.extend(chunk_mdx(source_file, relative, manifest["upstream_commit"],
                                manifest["source_url_template"], max_chars))

    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.executescript("""
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE chunks (
                    id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    heading_path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    source_url TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE chunks_fts USING fts5(
                    chunk_id UNINDEXED, heading, body, tokenize='porter unicode61'
                );
            """)
            db.execute("INSERT INTO meta VALUES (?, ?)", ("scenario", manifest["id"]))
            db.execute("INSERT INTO meta VALUES (?, ?)", ("source_commit", manifest["upstream_commit"]))
            db.execute("INSERT INTO meta VALUES (?, ?)", ("parser_version", PARSER_VERSION))
            db.execute("INSERT INTO meta VALUES (?, ?)", ("max_chars", str(max_chars)))
            for chunk in chunks:
                db.execute("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (chunk.id, chunk.source_path, chunk.title, json.dumps(chunk.heading_path),
                            chunk.start_line, chunk.end_line, chunk.text, chunk.source_url))
                db.execute("INSERT INTO chunks_fts VALUES (?, ?, ?)",
                           (chunk.id, " > ".join(chunk.heading_path), chunk.text))
            db.commit()
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target, len(chunks)


def search(db_path: Path, query: str, limit: int = 5) -> list[dict]:
    terms = WORDS.findall(query)
    if not terms:
        raise ValueError("keyword baseline requires an English search query")
    expression = " OR ".join(f'"{term}"' for term in terms)
    started = time.perf_counter()
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("""
            SELECT c.*, bm25(chunks_fts) AS rank_score
            FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ?
            ORDER BY rank_score ASC LIMIT ?
        """, (expression, limit)).fetchall()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return [
        {"id": row["id"], "rank": rank, "score": round(-row["rank_score"], 6),
         "source_path": row["source_path"], "heading_path": json.loads(row["heading_path"]),
         "start_line": row["start_line"], "end_line": row["end_line"],
         "source_url": row["source_url"], "text": row["text"], "retrieval_ms": elapsed_ms}
        for rank, row in enumerate(rows, 1)
    ]
