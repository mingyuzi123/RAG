"""Versioned local Markdown/MDX documents for the private custom scenario."""

from hashlib import sha256
from pathlib import Path
from base64 import b64decode
from binascii import Error as Base64Error
import json
import os
import re

from .pdf_source import extract_pages


SCENARIO_ID = "local-docs"
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_PDF_BYTES = 8 * 1024 * 1024
STORED_PATH = re.compile(r"^docs/[0-9a-f]{20}\.(?:md|mdx|pdf)$")


def local_manifest_path(root: Path) -> Path:
    return root / "data" / "local-docs" / "manifest.json"


def ensure_local_scenario(root: Path) -> Path:
    path = local_manifest_path(root)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "id": SCENARIO_ID, "name": "我的本地文档", "language": "mixed",
            "source_type": "local", "upstream_commit": sha256(b"empty").hexdigest(),
            "docs_version": "empty", "local_checkout": "data/local-docs",
            "source_url_template": "/api/source?scenario=local-docs&path={path}",
            "files": [], "display_names": {}, "pdf_sparse_pages": {},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    ui = path.parent / "ui.json"
    if not ui.is_file():
        ui.write_text(json.dumps({"title": "我的本地文档", "badge": "LOCAL · 自定义场景",
            "subtitle": "上传 Markdown/MDX 或文本型 PDF，建立独立索引后检索自己的资料",
            "accent": "#287caa", "learning_points": ["资料与索引按版本隔离", "先看召回，再看答案引用"]},
            ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def import_document(root: Path, filename: str, content: str | None,
                    replace: bool = False, pdf_base64: str | None = None) -> dict:
    if (not isinstance(filename, str) or not filename or len(filename) > 180 or
            any(ord(char) < 32 or char in '/\\<>:"|?*' for char in filename) or
            Path(filename).suffix.lower() not in (".md", ".mdx", ".pdf")):
        raise ValueError("只支持文件名有效的 .md、.mdx 或 .pdf 文档")
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        if not isinstance(pdf_base64, str) or len(pdf_base64) > (MAX_PDF_BYTES * 4 // 3 + 8):
            raise ValueError("PDF 内容缺失或超过 8 MB")
        try:
            raw = b64decode(pdf_base64, validate=True)
        except Base64Error as exc:
            raise ValueError("PDF 编码无效") from exc
        if len(raw) > MAX_PDF_BYTES:
            raise ValueError("单篇 PDF 不能超过 8 MB")
        _, sparse_pages = extract_pages(raw)
    else:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("文档内容不能为空")
        raw = content.encode("utf-8")
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise ValueError("单篇文档不能超过 1 MB")
        sparse_pages = []
    manifest_path = ensure_local_scenario(root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = dict(manifest.get("display_names", {}))
    previous = next((path for path, name in names.items() if name == filename), None)
    if previous and not replace:
        raise ValueError("同名文档已存在；勾选替换后再次导入")
    digest = sha256(filename.encode("utf-8") + b"\0" + raw).hexdigest()[:20]
    relative = f"docs/{digest}{extension}"
    source = manifest_path.parent / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        temporary = source.with_suffix(source.suffix + f".{os.getpid()}.tmp")
        temporary.write_bytes(raw)
        os.replace(temporary, source)
    files = [path for path in manifest["files"] if path != previous and path != relative]
    files.append(relative)
    names = {path: name for path, name in names.items() if path != previous}
    names[relative] = filename
    warnings = {path: pages for path, pages in manifest.get("pdf_sparse_pages", {}).items()
                if path != previous}
    if extension == ".pdf" and sparse_pages:
        warnings[relative] = sparse_pages
    manifest["files"] = files
    manifest["display_names"] = names
    manifest["pdf_sparse_pages"] = warnings
    manifest["upstream_commit"] = sha256("\n".join(sorted(files)).encode()).hexdigest()
    manifest["docs_version"] = manifest["upstream_commit"][:8]
    temporary = manifest_path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, manifest_path)
    return manifest


def local_source_file(root: Path, relative: str) -> Path:
    if not STORED_PATH.fullmatch(relative):
        raise ValueError("Invalid local document path")
    source = local_manifest_path(root).parent / relative
    if not source.is_file():
        raise FileNotFoundError("Local document not found")
    return source
