"""Read versioned Markdown/MDX sources into traceable chunks."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re


HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class Chunk:
    id: str
    source_path: str
    title: str
    heading_path: tuple[str, ...]
    start_line: int
    end_line: int
    text: str
    source_url: str


def _title_and_body(lines: list[str], fallback: str) -> tuple[str, list[tuple[int, str]]]:
    title = fallback
    start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                start = index + 1
                break
            if lines[index].startswith("title:"):
                title = lines[index].split(":", 1)[1].strip().strip('"\'') or fallback
    return title, [(index + 1, line) for index, line in enumerate(lines) if index >= start]


def _sections(body: list[tuple[int, str]], title: str):
    stack: list[tuple[int, str]] = []
    current: list[tuple[int, str]] = []
    current_heading: tuple[str, ...] = (title,)
    in_code = False
    for line_no, line in body:
        if line.lstrip().startswith("```"):
            in_code = not in_code
        match = None if in_code else HEADING.match(line)
        if match:
            if any(text.strip() for _, text in current):
                yield current_heading, current
            level, heading = len(match.group(1)), match.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading))
            current_heading = (title, *(name for _, name in stack))
            current = [(line_no, line)]
        else:
            current.append((line_no, line))
    if any(text.strip() for _, text in current):
        yield current_heading, current


def _blocks(section: list[tuple[int, str]]):
    block: list[tuple[int, str]] = []
    in_code = False
    for line_no, line in section:
        if line.lstrip().startswith("```"):
            in_code = not in_code
        block.append((line_no, line))
        if not line.strip() and not in_code:
            if any(text.strip() for _, text in block):
                yield block
            block = []
    if any(text.strip() for _, text in block):
        yield block


def chunk_mdx(
    file: Path,
    source_path: str,
    commit: str,
    url_template: str,
    max_chars: int = 1800,
) -> list[Chunk]:
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    lines = file.read_text(encoding="utf-8-sig").splitlines()
    title, body = _title_and_body(lines, file.stem)
    chunks: list[Chunk] = []
    base_url = url_template.format(commit=commit, path=source_path)

    for heading_path, section in _sections(body, title):
        pending: list[tuple[int, str]] = []

        def flush() -> None:
            if not pending:
                return
            text = "\n".join(value for _, value in pending).strip()
            if not text:
                return
            start, end = pending[0][0], pending[-1][0]
            digest = sha256(f"{commit}\n{source_path}\n{start}\n{end}\n{text}".encode()).hexdigest()[:20]
            chunks.append(
                Chunk(
                    id=digest,
                    source_path=source_path,
                    title=title,
                    heading_path=heading_path,
                    start_line=start,
                    end_line=end,
                    text=text,
                    source_url=f"{base_url}#L{start}-L{end}",
                )
            )

        for block in _blocks(section):
            new_length = len("\n".join(value for _, value in pending + block))
            if pending and new_length > max_chars:
                flush()
                pending = []
            pending.extend(block)
        flush()
    return chunks
