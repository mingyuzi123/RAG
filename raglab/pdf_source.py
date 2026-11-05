"""Extract text PDFs into page-bounded, source-traceable chunks."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re

from .corpus import Chunk


MAX_PAGES = 200
MAX_PAGE_STREAM = 4 * 1024 * 1024
MAX_EXTRACTED_CHARS = 2_000_000
MIN_PAGE_CHARS = 20


def extract_pages(content: bytes) -> tuple[list[str], list[int]]:
    """Return per-page text and sparse page numbers; never run OCR silently."""
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
            text = (page.extract_text(extraction_mode="layout") or "").replace("\r\n", "\n").replace("\r", "\n")
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
    return pages, sparse


def chunk_pdf(file: Path, source_path: str, commit: str, url_template: str,
              max_chars: int = 1800, title: str | None = None) -> list[Chunk]:
    """Split within each page only, preserving PDF page links and stable IDs."""
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    pages, _ = extract_pages(file.read_bytes())
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
                if pending:
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
    return chunks
