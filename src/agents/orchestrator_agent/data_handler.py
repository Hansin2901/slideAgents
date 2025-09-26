"""Utilities for preparing user content and template layout data."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.db.template_dal import get_presentation

logger = logging.getLogger(__name__)

_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}


def _extract_pdf_text(path: Path) -> str:
    """Read a PDF file via PyMuPDF (fitz) and return concatenated text."""

    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "PyMuPDF is required to process PDF uploads. Install 'pymupdf'.",
        ) from exc

    text_chunks: list[str] = []
    with fitz.open(path) as doc:  # type: ignore[attr-defined]
        for page in doc:  # pragma: no branch - PyMuPDF iter
            text_chunks.append(page.get_text("text"))
    return "\n".join(chunk.strip() for chunk in text_chunks if chunk.strip())


def get_user_content(file_path: str) -> str:
    """Return the textual content supplied by the user.

    Accepts plain-text formats or PDF files and normalises the output into a
    single string suitable for prompting an LLM.
    """

    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"User file not found: {file_path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        content = _extract_pdf_text(path)
    elif suffix in _TEXT_EXTENSIONS:
        content = path.read_text(encoding="utf-8", errors="ignore")
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    content = content.strip()
    if not content:
        raise ValueError("Uploaded file did not contain any readable text.")

    logger.debug("Loaded user content from %s (%.0f chars)", file_path, len(content))
    return content


def _extract_text_elements(element: Dict[str, Any]) -> Optional[str]:
    text = ((element.get("shape") or {}).get("text") or {}).get("textElements")
    if not isinstance(text, list):
        return None
    parts: List[str] = []
    for chunk in text:
        content = ((chunk.get("textRun") or {}).get("content") or "").strip()
        if content:
            parts.append(content)
    return "".join(parts).strip() if parts else None


def _build_layout_summary(document: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce the stored template document to the LLM-friendly subset."""

    presentation_data = (document.get("presentationData") or {}) if document else {}
    summary: Dict[str, Any] = {
        "presentationId": document.get("presentationId"),
        "title": presentation_data.get("title"),
        "layouts": [],
    }

    for layout in presentation_data.get("layouts") or []:
        layout_entry: Dict[str, Any] = {
            "objectId": layout.get("objectId"),
            "name": (layout.get("layoutProperties") or {}).get("displayName"),
            "placeholders": [],
        }
        for element in layout.get("pageElements", []):
            placeholder = (element.get("shape") or {}).get("placeholder") or {}
            placeholder_type = placeholder.get("type")
            if not placeholder_type:
                continue
            transform = element.get("transform") or {}
            placeholder_payload = {
                "objectId": element.get("objectId"),
                "placeholderType": placeholder_type,
                "placeHolderIndex": placeholder.get("index"),
                "loc": {
                    "x": transform.get("translateX"),
                    "y": transform.get("translateY"),
                },
                "size": {
                    "width": ((element.get("size") or {}).get("width") or {}).get("magnitude"),
                    "height": ((element.get("size") or {}).get("height") or {}).get("magnitude"),
                },
                "defaultText": _extract_text_elements(element),
            }
            layout_entry["placeholders"].append(placeholder_payload)
        summary["layouts"].append(layout_entry)

    return summary


def fetch_layout_data(template_id: str) -> Dict[str, Any]:
    """Fetch and normalise layout information for the given template ID."""

    if not template_id:
        raise ValueError("template_id is required")

    document = get_presentation(template_id)
    if not document:
        raise LookupError(f"Template {template_id!r} was not found in MongoDB")

    summary = _build_layout_summary(document)
    logger.debug(
        "Resolved layout summary for template %s: %s",
        template_id,
        json.dumps(summary, indent=2)[:500],
    )
    return summary


__all__ = ["fetch_layout_data", "get_user_content"]
