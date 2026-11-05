"""Verify real PDF parsing, page citations, and versioned local indexing."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
import base64
import importlib.util

from raglab.generation import build_messages
from raglab.local_sources import import_document, local_source_file
from raglab.pdf_source import chunk_pdf, extract_pages
from raglab.store import build_index, search


HAS_PYPDF = importlib.util.find_spec("pypdf") is not None


def sample_pdf(*pages: str) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
        })
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


@skipUnless(HAS_PYPDF, "install requirements-pdf.txt")
class PdfSourceTests(TestCase):
    def test_two_pages_keep_real_page_links_in_retrieval_and_prompt(self):
        pdf = sample_pdf("Apples are red and belong to the first page of this manual.",
                         "Bananas are yellow and belong to the second page of this manual.")
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            root = Path(folder)
            manifest = import_document(root, "manual.pdf", None,
                                       pdf_base64=base64.b64encode(pdf).decode("ascii"))
            path, count = build_index(root, manifest)
            self.assertEqual(count, 2)
            banana = search(path, "Bananas", 1)[0]
            self.assertEqual(banana["page_number"], 2)
            self.assertTrue(banana["source_url"].endswith("#page=2"))
            self.assertIn("page 2", build_messages("What color?", [banana])[1]["content"])
            self.assertEqual(local_source_file(root, banana["source_path"]).read_bytes(), pdf)

    def test_scanned_textless_pdf_is_rejected_without_changing_manifest(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            root = Path(folder)
            empty = base64.b64encode(sample_pdf("")).decode("ascii")
            with self.assertRaisesRegex(ValueError, "OCR"):
                import_document(root, "scan.pdf", None, pdf_base64=empty)
            self.assertFalse((root / "data/local-docs/manifest.json").exists())

    def test_replacing_pdf_uses_new_index_and_preserves_old_source(self):
        first = base64.b64encode(sample_pdf("Retries are limited to two attempts in this manual.")).decode("ascii")
        second = base64.b64encode(sample_pdf("Retries are limited to four attempts in this manual.")).decode("ascii")
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            root = Path(folder)
            old = import_document(root, "policy.pdf", None, pdf_base64=first)
            old_path, _ = build_index(root, old)
            new = import_document(root, "policy.pdf", None, replace=True, pdf_base64=second)
            new_path, _ = build_index(root, new)
            self.assertNotEqual(old_path, new_path)
            self.assertIn("four", search(new_path, "four", 1)[0]["text"])
            self.assertEqual(search(new_path, "two", 1), [])
            self.assertTrue((root / "data/local-docs" / old["files"][0]).exists())

    def test_sparse_page_reports_ocr_risk_without_faking_a_citation(self):
        pdf = sample_pdf("A full text page describes stable evidence in this guide.", "")
        pages, sparse = extract_pages(pdf)
        self.assertEqual(len(pages), 2)
        self.assertEqual(sparse, [2])
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            file = Path(folder) / "source.pdf"
            file.write_bytes(pdf)
            chunks = chunk_pdf(file, "docs/source.pdf", "version", "http://localhost/{path}")
            self.assertEqual({item.page_number for item in chunks}, {1})
