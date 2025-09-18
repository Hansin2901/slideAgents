from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Sequence

from src.db.template_dal import get_presentation

from .models import ResolvedSlide, TemplateLayout, TextModel
from .storage import load_layouts_from_document
from .validator import validate_plan_slide
from .xml_parser import parse_inline_xml_to_textmodel


class MissingPlanError(ValueError):
    pass


def _load_plan_payload(plan_path: str | Path) -> dict:
    path = Path(plan_path)
    if not path.exists():
        raise FileNotFoundError(f"plan file not found: {plan_path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_resolved_plan(document: dict, plan: dict) -> List[ResolvedSlide]:
    if not plan:
        raise MissingPlanError("plan document is empty")
    presentation_data = document.get("presentationData") if isinstance(document, dict) else None
    if not presentation_data:
        return []
    layouts = load_layouts_from_document(document)

    resolved: List[ResolvedSlide] = []
    for slide in plan.get("presentation_plan", []):
        result = validate_plan_slide(slide, layouts)
        parsed: Dict[str, Dict[str, TextModel]] = {}
        content = slide.get("content", {})
        for placeholder_type, per_index in content.items():
            if placeholder_type not in result.mappings:
                continue
            parsed.setdefault(placeholder_type, {})
            for idx_key, value in per_index.items():
                if idx_key in result.mappings[placeholder_type] and value:
                    parsed[placeholder_type][idx_key] = parse_inline_xml_to_textmodel(value)
        result.parsed = parsed
        resolved.append(result)
    return resolved


def resolve_plan_for_presentation(presentation_id: str, owner_id: str | None, plan: dict) -> List[ResolvedSlide]:
    doc = get_presentation(presentation_id)
    if not doc:
        raise MissingPlanError(f"Presentation '{presentation_id}' not found")
    if owner_id and doc.get("ownerId") != owner_id:
        raise MissingPlanError("Owner mismatch for the requested presentation")
    return build_resolved_plan(doc, plan)


def resolve_plan_from_file(
    presentation_id: str,
    plan_path: str | Path,
    owner_id: str | None = None,
) -> List[ResolvedSlide]:
    plan = _load_plan_payload(plan_path)
    return resolve_plan_for_presentation(presentation_id, owner_id, plan)


def build_batch_requests_from_plan(
    presentation_id: str,
    plan_path: str | Path,
    owner_id: str | None = None,
    *,
    run_prefix: str | None = None,
) -> Sequence[dict]:
    resolved = resolve_plan_from_file(presentation_id, plan_path, owner_id)
    for slide in resolved:
        if slide.errors:
            joined = "; ".join(slide.errors)
            raise MissingPlanError(f"Plan validation failed for layout '{slide.layout_id}': {joined}")
    from .adapter import build_slide_requests

    requests: List[dict] = []
    for idx, slide in enumerate(resolved, start=1):
        requests.append(build_slide_requests(idx, slide, run_prefix))
    return requests
