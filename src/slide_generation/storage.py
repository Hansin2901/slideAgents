from __future__ import annotations

from typing import Dict, Iterable, Optional

from src.db.template_dal import (
    get_presentation,
)
from .models import Placeholder, PlaceholderType, TemplateLayout


def _coerce_placeholder_type(raw_type: str) -> PlaceholderType:
    try:
        return PlaceholderType(raw_type)
    except ValueError:
        return PlaceholderType.OTHER


def _coerce_index(raw_index) -> Optional[int]:
    if raw_index is None:
        return None
    if isinstance(raw_index, int):
        return raw_index
    if isinstance(raw_index, dict):
        for key in ("$numberInt", "$numberDouble", "$numberLong"):
            if key in raw_index:
                try:
                    return int(float(raw_index[key]))
                except Exception:
                    return None
    try:
        return int(raw_index)
    except Exception:
        return None


def load_layouts_from_document(doc: dict) -> Dict[str, TemplateLayout]:
    presentation_data = (doc or {}).get("presentationData") or {}
    layouts = presentation_data.get("layouts") or []

    by_id: Dict[str, TemplateLayout] = {}
    for layout in layouts:
        layout_id = layout.get("objectId")
        if not layout_id:
            continue
        placeholders: list[Placeholder] = []
        for element in layout.get("pageElements", []):
            placeholder = None
            if "shape" in element and isinstance(element["shape"], dict):
                placeholder = element["shape"].get("placeholder")
            elif "image" in element and isinstance(element["image"], dict):
                placeholder = element["image"].get("placeholder")
            if not placeholder:
                continue
            placeholder_type = _coerce_placeholder_type(str(placeholder.get("type", "OTHER")))
            index_val = _coerce_index(placeholder.get("index"))
            placeholders.append(
                Placeholder(
                    type=placeholder_type,
                    index=index_val,
                    object_id=element.get("objectId", ""),
                )
            )
        by_id[layout_id] = TemplateLayout(layout_id=layout_id, placeholders=placeholders)
    return by_id


class PresentationStorage:
    def __init__(self, presentation_id: str, owner_id: str | None = None) -> None:
        self.presentation_id = presentation_id
        self.owner_id = owner_id

    def load_layouts(self) -> Dict[str, TemplateLayout]:
        query_doc = get_presentation(self.presentation_id)
        if query_doc and self.owner_id and query_doc.get("ownerId") != self.owner_id:
            return {}
        return load_layouts_from_document(query_doc or {})

