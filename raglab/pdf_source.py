"""Extract text PDFs into page-bounded, source-traceable chunks."""

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from itertools import groupby
from pathlib import Path
import re

from .corpus import Chunk


MAX_PAGES = 200
MAX_PAGE_STREAM = 4 * 1024 * 1024
MAX_EXTRACTED_CHARS = 2_000_000
MIN_PAGE_CHARS = 20
PDF_CHUNKING_MODES = ("paragraph", "pack_short", "semantic")
PDF_EXTRACTION_MODES = ("layout", "ordered", "ordered_tables")
SHORT_BLOCK_CHARS = 80
PDF_SEMANTIC_VERSION = "semantic-v1"
SEMANTIC_MIN_SIMILARITY = 0.82
SECTION_START = re.compile(r"^(?:#{1,6}\s|\d+(?:\.\d+)*\.\s)")
TABLE_MARKER = re.compile(r"\bTable\s+(?:\d+\s*[.:]|columns:|row\s+\d+\s*\()", re.I)


def _semantic_page(chunks: list[Chunk], max_chars: int, model) -> list[Chunk]:
    # Flattened table pages do not reliably separate table cells from prose.
    if len(chunks) < 2 or any(TABLE_MARKER.search(chunk.text) for chunk in chunks):
        return chunks
    vectors = model.encode(["passage: " + chunk.text for chunk in chunks],
                           batch_size=16, normalize_embeddings=True)
    result = []
    index = 0
    while index < len(chunks) - 1:
        left, right = chunks[index:index + 2]
        length = len(left.text) + 2 + len(right.text)
        is_margin = ((index == 0 and re.search(r" {12,}", left.text.splitlines()[0])) or
                     (index + 1 == len(chunks) - 1 and re.search(r" {12,}", right.text.splitlines()[-1])))
        if (length <= max_chars and not is_margin and not SECTION_START.match(right.text)
                and float(vectors[index] @ vectors[index + 1]) >= SEMANTIC_MIN_SIMILARITY):
            body = f"{left.text}\n\n{right.text}"
            chunk_id = sha256(f"{PDF_SEMANTIC_VERSION}\n{left.id}\n{right.id}\n{body}".encode()).hexdigest()[:20]
            result.append(replace(left, id=chunk_id, end_line=right.end_line, text=body))
            index += 2
        else:
            result.append(left)
            index += 1
    if index < len(chunks):
        result.append(chunks[index])
    return result


def extract_pages(content: bytes, mode: str = "layout") -> tuple[list[str], list[int]]:
    """Return per-page text and sparse page numbers; never run OCR silently."""
    if mode not in PDF_EXTRACTION_MODES:
        raise ValueError(f"Unknown PDF extraction mode: {mode}")
    if not content.startswith(b"%PDF-"):
        raise ValueError("文件不是有效的 PDF")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF 解析依赖缺失，请安装 requirements-pdf.txt") from exc
    try:
        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise ValueError("暂不支持加密 PDF，请先提供可读取的版本")
        count = len(reader.pages)
        if not 1 <= count <= MAX_PAGES:
            raise ValueError(f"PDF 页数需在 1–{MAX_PAGES} 页之间")
        pages = []
        total = 0
        for page in reader.pages:
            stream = page.get_contents()
            if stream is not None and len(stream.get_data()) > MAX_PAGE_STREAM:
                raise ValueError("PDF 单页解压内容过大，暂不导入")
            text = (page.extract_text(extraction_mode="layout" if mode == "layout" else "plain") or "")
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
            total += len(text)
            if total > MAX_EXTRACTED_CHARS:
                raise ValueError("PDF 提取文本过大，暂不导入")
            pages.append(text)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"PDF 无法解析：{type(exc).__name__}") from exc
    sparse = [number for number, text in enumerate(pages, 1)
              if len(re.sub(r"\s", "", text)) < MIN_PAGE_CHARS]
    if len(sparse) == len(pages):
        raise ValueError("PDF 未提取到足够文字；扫描件需要 OCR，不能作为空知识库导入")
    if mode == "ordered_tables":
        from .pdf_layout import extract_table_blocks

        tables = extract_table_blocks(content)
        if len(tables) != len(pages):
            raise ValueError("表格解析页数与原始 PDF 不一致")
        pages = ["\n\n".join([text, *blocks]) if blocks else text for text, blocks in zip(pages, tables)]
        if sum(map(len, pages)) > MAX_EXTRACTED_CHARS:
            raise ValueError("PDF 提取文本过大，暂不导入")
    return pages, sparse


def chunk_pdf(file: Path, source_path: str, commit: str, url_template: str,
              max_chars: int = 1800, title: str | None = None,
              mode: str = "paragraph", extraction: str = "layout") -> list[Chunk]:
    """Split within each page only, preserving PDF page links and stable IDs."""
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    if mode not in PDF_CHUNKING_MODES:
        raise ValueError(f"Unknown PDF chunking mode: {mode}")
    pages, _ = extract_pages(file.read_bytes(), extraction)
    title = title or file.stem
    base_url = url_template.format(commit=commit, path=source_path)
    chunks = []
    line_offset = 0
    for page_number, text in enumerate(pages, 1):
        lines = text.splitlines()
        pending: list[tuple[int, str]] = []

        def flush() -> None:
            if not pending:
                return
            body = "\n".join(line for _, line in pending).strip()
            if not body:
                return
            start, end = pending[0][0], pending[-1][0]
            digest = sha256(f"{commit}\n{source_path}\n{page_number}\n{start}\n{end}\n{body}".encode()).hexdigest()[:20]
            chunks.append(Chunk(id=digest, source_path=source_path, title=title,
                                heading_path=(title, f"第 {page_number} 页"),
                                start_line=start, end_line=end, text=body,
                                source_url=f"{base_url}#page={page_number}",
                                page_number=page_number))

        for local_line, raw in enumerate(lines, 1):
            number = line_offset + local_line
            line = raw.strip()
            if not line:
                keep_short = (mode == "pack_short" and
                              len(" ".join(" ".join(text for _, text in pending).split())) <= SHORT_BLOCK_CHARS)
                if pending and not keep_short:
                    flush()
                    pending = []
                continue
            # A long extracted line gets bounded fragments; no block crosses pages.
            pieces = [line[index:index + max_chars] for index in range(0, len(line), max_chars)]
            for piece in pieces:
                length = len("\n".join(value for _, value in pending + [(number, piece)]))
                if pending and length > max_chars:
                    flush()
                    pending = []
                pending.append((number, piece))
        flush()
        line_offset += len(lines) + 1
    if mode == "semantic" and chunks:
        from .vector import load_model

        model = load_model()
        return [chunk for _, page in groupby(chunks, key=lambda item: item.page_number)
                for chunk in _semantic_page(list(page), max_chars, model)]
    return chunks
