"""Focused checks for provenance and the generation boundary."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import io
import json
import os

from raglab.corpus import chunk_mdx
from raglab.generation import build_messages, generate_answer


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
