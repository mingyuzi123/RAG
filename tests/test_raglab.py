"""Focused checks for provenance and the generation boundary."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import io
import json
import os

from raglab.corpus import chunk_mdx
from raglab.decomposition import decompose_question
from raglab.generation import build_messages, generate_answer
from raglab.hybrid import reciprocal_rank_fusion
from raglab.multiquery import interleave_results
from raglab.service import answer, validate_request
from scripts.run_with_deepseek import load_local_env, require_key


class LocalKeyTests(TestCase):
    def test_private_env_loads_without_overriding_existing_key(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            env_file = Path(folder) / ".env"
            env_file.write_text("DEEPSEEK_API_KEY='private-test-key'\nDEEPSEEK_MODEL=deepseek-flash\n",
                                encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                load_local_env(env_file)
                require_key()
                self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "private-test-key")
                os.environ["DEEPSEEK_API_KEY"] = "environment-key"
                load_local_env(env_file)
                self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "environment-key")


class CorpusTests(TestCase):
    def test_heading_inside_code_does_not_split_and_id_tracks_content(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            file = Path(folder) / "sample.mdx"
            file.write_text('---\ntitle: Demo\n---\n## Setup\nBefore.\n\n```python\n# Not a heading\nprint(1)\n```\n', encoding="utf-8")
            args = (file, "sample.mdx", "abc123", "https://example.test/{commit}/{path}")
            chunks = chunk_mdx(*args)
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].heading_path, ("Demo", "Setup"))
            self.assertEqual((chunks[0].start_line, chunks[0].end_line), (4, 10))
            self.assertIn("# Not a heading", chunks[0].text)
            self.assertIn("#L4-L10", chunks[0].source_url)
            first_id = chunks[0].id
            file.write_text(file.read_text(encoding="utf-8").replace("Before.", "After."), encoding="utf-8")
            self.assertNotEqual(chunk_mdx(*args)[0].id, first_id)

    def test_long_table_keeps_column_meaning_and_source_lines(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            file = Path(folder) / "table.mdx"
            rows = [f"| Field {n} | `field_{n}` | Explanation for field {n}. |" for n in range(20)]
            file.write_text("## Agent Attributes\n\n| Attribute | Parameter | Description |\n"
                            "| --- | --- | --- |\n" + "\n".join(rows) + "\n", encoding="utf-8")
            chunks = chunk_mdx(file, "table.mdx", "abc123", "https://example.test/{commit}/{path}", 500)
            self.assertGreater(len(chunks), 1)
            self.assertTrue(all(len(chunk.text) <= 500 for chunk in chunks))
            self.assertTrue(all(chunk.heading_path[-1] == "Agent Attributes" for chunk in chunks))
            self.assertIn("Attribute: Field 0; Parameter: `field_0`; Description: Explanation for field 0.",
                          chunks[0].text)
            self.assertEqual(chunks[0].start_line, 1)
            self.assertEqual(chunks[-1].end_line, 24)


class GenerationTests(TestCase):
    def test_prompt_and_citation_validation(self):
        evidence = [{"source_path": "a.mdx", "heading_path": ["Demo", "Setup"],
                     "start_line": 4, "end_line": 10, "text": "The manager delegates tasks."}]
        prompt = build_messages("谁分配任务？", evidence)
        self.assertIn("The manager delegates tasks.", prompt[1]["content"])
        self.assertIn("same language", prompt[0]["content"])

        response = io.BytesIO(json.dumps({"model": "deepseek-flash", "choices": [
            {"message": {"content": "Manager 分配任务。[1]"}}], "usage": {"total_tokens": 42}}).encode())
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only"}):
            with patch("raglab.generation.urlopen", return_value=response) as mocked:
                result = generate_answer("谁分配任务？", evidence)
        self.assertTrue(result["citation_numbers_valid"])
        self.assertEqual(result["cited_numbers"], [1])
        self.assertEqual(result["usage"]["total_tokens"], 42)
        self.assertEqual(mocked.call_args.args[0].full_url, "https://api.deepseek.com/chat/completions")

    def test_decomposition_returns_two_questions_without_answering(self):
        response = io.BytesIO(json.dumps({"model": "deepseek-flash", "choices": [
            {"message": {"content": json.dumps({"subqueries": ["Agent 的 tools 有什么作用？",
                                                        "Task 的 tools 有什么作用？"]}, ensure_ascii=False)}}],
            "usage": {"total_tokens": 71}}).encode())
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only"}):
            with patch("raglab.generation.urlopen", return_value=response) as mocked:
                result = decompose_question("Agent 和 Task 的 tools 有什么区别？")
        self.assertEqual(len(result["subqueries"]), 2)
        self.assertEqual(result["usage"]["total_tokens"], 71)
        payload = json.loads(mocked.call_args.args[0].data)
        self.assertEqual(payload["messages"][1]["content"], "Agent 和 Task 的 tools 有什么区别？")


class HybridTests(TestCase):
    def test_duplicate_candidate_gets_two_rank_signals(self):
        keyword = [{"id": "shared", "rank": 2, "retrieval_ms": 1.0},
                   {"id": "keyword", "rank": 1, "retrieval_ms": 1.0}]
        vector = [{"id": "shared", "rank": 1, "retrieval_ms": 2.0},
                  {"id": "vector", "rank": 2, "retrieval_ms": 2.0}]
        results = reciprocal_rank_fusion(keyword, vector, 2)
        self.assertEqual([item["id"] for item in results], ["shared", "keyword"])
        self.assertEqual(results[0]["retriever_ranks"], {"bm25": 2, "vector": 1})
        self.assertEqual(results[0]["retrieval_ms"], 3.0)


class MultiQueryTests(TestCase):
    def test_interleaving_covers_both_intents_and_deduplicates(self):
        first = [{"id": "agent-overview", "rank": 1, "score": .9, "retrieval_ms": 2.0},
                 {"id": "agent-attributes", "rank": 2, "score": .8, "retrieval_ms": 2.0}]
        second = [{"id": "task-attributes", "rank": 1, "score": .85, "retrieval_ms": 3.0},
                  {"id": "agent-overview", "rank": 2, "score": .7, "retrieval_ms": 3.0}]
        result = interleave_results([first, second], 3)
        self.assertEqual([item["id"] for item in result],
                         ["agent-overview", "task-attributes", "agent-attributes"])
        self.assertEqual(result[0]["subquery_ranks"], {"query_1": 1, "query_2": 2})
        self.assertEqual(result[0]["retrieval_ms"], 5.0)

    def test_decomposed_requires_two_subquestions(self):
        with self.assertRaises(ValueError):
            validate_request("比较 Agent 和 Task 工具", "decomposed", None, 10,
                             subqueries=["Agent tools"])


class WorkflowTests(TestCase):
    def test_answer_trace_keeps_all_candidates_and_selected_context(self):
        candidate = lambda name: {"id": name, "source_url": f"https://example.test/{name}",
                                  "heading_path": [name], "rank": 1, "text": name}
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            root = Path(folder)
            db_path = root / "indexes" / "test.db"
            with patch("raglab.service.retrieve", return_value=[candidate("first"), candidate("second")]):
                with patch("raglab.service.generate_answer", return_value={
                    "answer": "supported [1]", "usage": {"total_tokens": 3},
                    "citation_numbers_valid": True}):
                    trace = answer(root, {"id": "test", "upstream_commit": "abc"}, db_path,
                                   "question", top_k=2, context_k=1)
            self.assertEqual([item["id"] for item in trace["candidates"]], ["first", "second"])
            self.assertEqual(trace["selected_chunk_ids"], ["first"])
            self.assertEqual(trace["result"]["sources"][0]["chunk_id"], "first")
            saved = json.loads((root / "logs" / "requests.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(saved["request_id"], trace["request_id"])

    def test_generation_failure_still_records_retrieved_evidence(self):
        item = {"id": "evidence", "source_url": "https://example.test/evidence",
                "heading_path": ["Demo"], "rank": 1, "text": "evidence"}
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            root = Path(folder)
            with patch("raglab.service.retrieve", return_value=[item]):
                with patch("raglab.service.generate_answer", side_effect=RuntimeError("API unavailable")):
                    with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                        answer(root, {"id": "test", "upstream_commit": "abc"},
                               root / "index.db", "question")
            saved = json.loads((root / "logs" / "requests.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["selected_chunk_ids"], ["evidence"])
