from __future__ import annotations

from typing import Dict, List

from .models import ResolvedSlide, TemplateLayout
from .mapper import build_placeholder_map


def validate_plan_slide(plan_slide: dict, layouts: Dict[str, TemplateLayout]) -> ResolvedSlide:
    layout_id = plan_slide.get("objectId")
    content: Dict[str, Dict[str, str]] = plan_slide.get("content", {})

    errors: List[str] = []
    warnings: List[str] = []

    layout = layouts.get(layout_id)
    if not layout:
        return ResolvedSlide(
            layout_id=str(layout_id),
            mappings={},
            parsed={},
            errors=[f"Template not found for layout objectId '{layout_id}'."],
            warnings=[],
        )

    mapping = build_placeholder_map(layout)

    for placeholder_type, per_index in content.items():
        if placeholder_type not in mapping:
            warnings.append(
                f"Placeholder '{placeholder_type}' not present in template '{layout_id}'. Available types: {sorted(mapping.keys())}"
            )
            continue
        for idx_key in per_index.keys():
            idx_norm = idx_key if idx_key != "None" else "null"
            if idx_norm not in mapping[placeholder_type]:
                available = sorted(mapping[placeholder_type].keys())
                errors.append(
                    f"Placeholder '{placeholder_type}' index '{idx_key}' not present in template '{layout_id}'. Available indices: {available}"
                )

    return ResolvedSlide(layout_id=layout_id, mappings=mapping, parsed={}, errors=errors, warnings=warnings)
