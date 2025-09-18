from __future__ import annotations

from typing import Optional

from src.db.template_dal import (
    get_presentation,
    get_layout_by_id,
    set_layout_explanation,
    get_minimal_layout_geometry,
)
from .extractor import summarize_presentation
from .schemas import TemplateExplainRequest, TemplateExplainResponse, LayoutDescription, Placeholder
from .graph import explain_template, explain_single_layout


def explain_template_from_db(presentation_id: str) -> Optional[TemplateExplainResponse]:
    doc = get_presentation(presentation_id)
    if not doc:
        return None
    pres = doc.get("presentationData") or {}
    summary = summarize_presentation(pres)

    # Map extractor TypedDict to pydantic models
    layouts = []
    for l in summary.get("layouts", []):
        placeholders = []
        for p in l.get("placeHolders", []):
            placeholders.append(
                Placeholder(
                    object_id=p.get("objectId", ""),
                    placeholder_type=p.get("placeholderType", "UNKNOWN"),
                    default_text=p.get("text"),
                )
            )
        layouts.append(
            LayoutDescription(
                # layout_id=l.get("layoutId", ""),
                layout_name=l.get("layoutName"),
                placeholders=placeholders,
            )
        )

    req = TemplateExplainRequest(
        presentation_id=summary.get("presentationId", presentation_id),
        title=summary.get("title"),
        slide_count=summary.get("slideCount", 0),
        layouts=layouts,
    )
    return explain_template(req)


# def _build_layout_input_from_presentation(pres_json: dict, layout_object_id: str) -> Optional[dict]:
#     """Construct a detailed layout input object for the LLM from Slides presentation JSON.

#     Expected structure in pres_json.layouts[*]:
#       - objectId
#       - layoutProperties.displayName
#       - pageElements[*] with either shape.placeholder.type or generic element type,
#         and transform/size fields when available.
#     """
#     layouts = pres_json.get("layouts", [])
#     for layout in layouts:
#         if layout.get("objectId") != layout_object_id:
#             continue
#         display_name = (layout.get("layoutProperties") or {}).get("displayName")
#         page_elements = []
#         for el in layout.get("pageElements", []):
#             # Derive a type label
#             ph_type = (((el.get("shape") or {}).get("placeholder") or {}).get("type"))
#             etype = ph_type or el.get("shape", {}).get("shapeType") or el.get("sheetsChart", {}).get("spreadsheetId") and "SHEETS_CHART" or el.get("objectId") and "UNKNOWN"
#             # Extract transform (position/scale) and size if present
#             transform = el.get("transform") or {}
#             size = (el.get("size") or {})
#             page_elements.append({
#                 "objectId": el.get("objectId"),
#                 "type": etype,
#                 "position": {
#                     "translateX": transform.get("translateX"),
#                     "translateY": transform.get("translateY"),
#                     "scaleX": transform.get("scaleX"),
#                     "scaleY": transform.get("scaleY"),
#                     "unit": transform.get("unit"),
#                 },
#                 "size": {
#                     "height": (size.get("height") or {}).get("magnitude"),
#                     "width": (size.get("width") or {}).get("magnitude"),
#                     "unit": (size.get("height") or {}).get("unit") or (size.get("width") or {}).get("unit"),
#                 },
#             })
#         return {
#             "objectId": layout_object_id,
#             "layoutProperties": {"displayName": display_name},
#             "pageElements": page_elements,
#         }
#     return None


def _build_layout_input_from_db(presentation_id: str, layout_object_id: str) -> Optional[dict]:
    """Build the layout input using a minimal geometry projection for efficiency.

    Prefers aggregation-based extractor; falls back to full layout when necessary.
    """
    min_geo = get_minimal_layout_geometry(presentation_id, layout_object_id)
    if min_geo:
        return {
            "objectId": min_geo.get("objectId"),
            "name": min_geo.get("name"),
            "elements": min_geo.get("elements") or [],
        }
    # Fallback: send the raw layout (older behavior)
    layout = get_layout_by_id(presentation_id, layout_object_id)
    return layout


def explain_and_store_single_layout(presentation_id: str, layout_object_id: str) -> Optional[dict]:
    """Run LLM for one layout and store results back into Mongo under that layout record.

    The results are stored in presentationData.layouts[i].explanation fields keyed by objectId.
    """
    doc = get_presentation(presentation_id)
    if not doc:
        return None
    # If explanation already exists, return it without another LLM call
    # We check on the full layout document to avoid missing the field in the minimal view
    full_layout = get_layout_by_id(presentation_id, layout_object_id)
    existing_expl = (full_layout or {}).get("explanation") if full_layout else None
    if existing_expl and all(k in existing_expl for k in ("generalDescription", "structuralDescription", "usageInstructions")):
        return existing_expl
    # Prefer DB-based single-layout fetch to avoid scanning the layouts array; use minimal geometry for LLM
    layout_input = _build_layout_input_from_db(presentation_id, layout_object_id)
    if not layout_input:
        return None

    result = explain_single_layout(layout_input)
    gen_desc = (result or {}).get("generalDescription") or ""
    if gen_desc.startswith("InvocationError:") or gen_desc.startswith("SchemaError:"):
        # Do not persist failed attempt; caller can retry later.
        return result

    explanation = {
        "objectId": layout_object_id,
        "generalDescription": result.get("generalDescription"),
        "structuralDescription": result.get("structuralDescription"),
        "usageInstructions": result.get("usageInstructions"),
    }
    set_layout_explanation(presentation_id, layout_object_id, explanation)
    return result


def explain_layout_for_slide(presentation_id: str, slide_object_id: str) -> Optional[dict]:
    """Resolve a slide's layoutObjectId then explain that layout.

    Many users copy the slide's objectId instead of the layout's objectId. This helper maps:
      slide.objectId -> slide.slideProperties.layoutObjectId -> layout.objectId
    and invokes the existing single-layout pathway.
    """
    doc = get_presentation(presentation_id)
    if not doc:
        return None
    pres = doc.get("presentationData") or {}
    slides = pres.get("slides", [])
    layout_object_id = None
    for s in slides:
        if s.get("objectId") == slide_object_id:
            layout_object_id = ((s.get("slideProperties") or {}).get("layoutObjectId"))
            break
    if not layout_object_id:
        return None
    return explain_and_store_single_layout(presentation_id, layout_object_id)
