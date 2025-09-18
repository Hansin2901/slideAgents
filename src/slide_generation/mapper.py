from __future__ import annotations

from typing import Dict

from .models import TemplateLayout


def build_placeholder_map(layout: TemplateLayout) -> Dict[str, Dict[str, str]]:
    mapping: Dict[str, Dict[str, str]] = {}
    for placeholder in layout.placeholders:
        placeholder_type = placeholder.type.value
        index_key = "null" if placeholder.index is None else str(placeholder.index)
        mapping.setdefault(placeholder_type, {})[index_key] = placeholder.object_id
    return mapping
