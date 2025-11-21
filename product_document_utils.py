from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

root_dir = Path(__file__).parent


def to_project_relative(path: Path) -> str:
    """
    Return a path relative to the project root when possible.
    Falls back to as_posix() if already relative or outside the project.
    """
    try:
        return path.relative_to(root_dir).as_posix()
    except ValueError:
        return path.as_posix()


def make_document_id(source_stem: str, product_index: int) -> str:
    """Default document_id pattern used by extractors."""
    return f"{source_stem}--p{product_index:05d}"


def build_source_document(
    file_path: Path,
    *,
    source_system: str,
    format: str,
    kind: str = "file",
    mime_type: Optional[str] = None,
    source_document_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds the meta.source_document block."""
    stem = source_document_id or file_path.stem
    return {
        "id": stem,
        "kind": kind,
        "format": format,
        "mime_type": mime_type,
        "filename": file_path.name,
        "path": to_project_relative(file_path),
        "url": None,
        "source_system": source_system,
    }


def build_meta(
    *,
    source_type: str,
    file_path: Path,
    product_index: int = 0,
    page_range: Optional[list[int]] = None,
    anchor: Optional[str] = None,
    artifacts: Optional[Dict[str, Any]] = None,
    language: Optional[Dict[str, Any]] = None,
    source_system: str = "local_input",
    format: str = "unknown",
    kind: str = "file",
    mime_type: Optional[str] = None,
    source_document_id: Optional[str] = None,
    document_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a meta block for ProductDocument with sane defaults.
    Caller provides artifacts/language when available.
    """
    source_doc = build_source_document(
        file_path,
        source_system=source_system,
        format=format,
        kind=kind,
        mime_type=mime_type,
        source_document_id=source_document_id,
    )
    stem = source_doc["id"]
    doc_id = document_id or make_document_id(stem, product_index)
    meta = {
        "document_id": doc_id,
        "source_type": source_type,
        "source_document": source_doc,
        "source_product": {
            "index": product_index,
            "page_range": page_range,
            "anchor": anchor,
        },
        "artifacts": artifacts or {},
        "language": language or {},
        "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return meta


def write_product_document(doc: Dict[str, Any], output_path: Path) -> None:
    """Persist a ProductDocument to disk with UTF-8 and pretty formatting."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
