"""Check that the optional context policy keeps source and budget boundaries."""

from pathlib import Path
from contextlib import closing
from tempfile import TemporaryDirectory
from unittest import TestCase
import json
import sqlite3

from raglab.context_window import select_context

ROOT = Path(__file__).resolve().parents[1]


def make_index(path: Path, rows: list[tuple]) -> None:
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE chunks (id TEXT, source_path TEXT, heading_path TEXT, "
                   "start_line INTEGER, end_line INTEGER, text TEXT, source_url TEXT)")
        db.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        db.commit()


def row(chunk_id: str, start: int, end: int, text: str, heading: str = "Basic") -> tuple:
    return (chunk_id, "guide.md", json.dumps(["Guide", heading]), start, end,
            text, f"https://example.test/guide.md#L{start}-L{end}")


class WindowSelectionTests(TestCase):
    def test_missing_query_term_adds_preceding_source_block_within_budget(self):
        with TemporaryDirectory(dir=ROOT) as folder:
            parent, child = Path(folder) / "parent.db", Path(folder) / "child.db"
            make_index(parent, [row("required-parent", 1, 3, "required field definition"),
                                row("conversion-parent", 4, 6, "string int conversion"),
                                row("distractor-parent", 7, 9, "unrelated example " * 4, "Other")])
            make_index(child, [row("required-child", 2, 2, "required field"),
                               row("conversion-child", 5, 5, "string int conversion"),
                               row("distractor-child", 8, 8, "unrelated example", "Other")])
            selected, trace = select_context(parent, child,
                [{"id": "conversion-parent"}, {"id": "distractor-parent"}],
                [{"id": "conversion-child"}, {"id": "distractor-child"}],
                "required field string int conversion", context_k=2)
            self.assertEqual([item["id"] for item in selected],
                             ["conversion-child", "required-parent"])
            self.assertEqual(selected[1]["start_line"], 1)
            self.assertIn("required", selected[1]["context_origin"])
            self.assertLessEqual(trace["selected_characters"], trace["character_budget"])

    def test_multiple_child_hits_merge_into_one_parent(self):
        with TemporaryDirectory(dir=ROOT) as folder:
            parent, child = Path(folder) / "parent.db", Path(folder) / "child.db"
            make_index(parent, [row("parent", 1, 6, "structured and unstructured state")])
            make_index(child, [row("child-a", 1, 3, "structured state"),
                               row("child-b", 4, 6, "unstructured state")])
            selected, trace = select_context(parent, child, [{"id": "parent"}],
                [{"id": "child-a"}, {"id": "child-b"}], "structured state", context_k=1)
            self.assertEqual([item["id"] for item in selected], ["parent"])
            self.assertEqual(selected[0]["context_origin"], "merged_parent")
            self.assertEqual(trace["selected_chunk_ids"], ["parent"])
