"""Versioned local Markdown/MDX documents for the private custom scenario."""

from hashlib import sha256
from pathlib import Path
import json
import os
import re


SCENARIO_ID = "local-docs"
MAX_DOCUMENT_BYTES = 1024 * 1024
STORED_PATH = re.compile(r"^docs/[0-9a-f]{20}\.(?:md|mdx)$")


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
            "files": [], "display_names": {},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    ui = path.parent / "ui.json"
    if not ui.is_file():
        ui.write_text(json.dumps({"title": "我的本地文档", "badge": "LOCAL · 自定义场景",
            "subtitle": "上传 Markdown/MDX，建立独立索引后检索自己的资料",
            "accent": "#287caa", "learning_points": ["资料与索引按版本隔离", "先看召回，再看答案引用"]},
            ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def import_document(root: Path, filename: str, content: str, replace: bool = False) -> dict:
    if (not isinstance(filename, str) or not filename or len(filename) > 180 or
            any(char in filename for char in "/\\\r\n\0") or
            Path(filename).suffix.lower() not in (".md", ".mdx")):
        raise ValueError("只支持文件名有效的 .md 或 .mdx 文档")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("文档内容不能为空")
    if len(content.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise ValueError("单篇文档不能超过 1 MB")
    manifest_path = ensure_local_scenario(root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = dict(manifest.get("display_names", {}))
    previous = next((path for path, name in names.items() if name == filename), None)
    if previous and not replace:
        raise ValueError("同名文档已存在；勾选替换后再次导入")
    extension = Path(filename).suffix.lower()
    digest = sha256((filename + "\0" + content).encode("utf-8")).hexdigest()[:20]
    relative = f"docs/{digest}{extension}"
    source = manifest_path.parent / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        temporary = source.with_suffix(source.suffix + f".{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, source)
    files = [path for path in manifest["files"] if path != previous and path != relative]
    files.append(relative)
    names = {path: name for path, name in names.items() if path != previous}
    names[relative] = filename
    manifest["files"] = files
    manifest["display_names"] = names
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
