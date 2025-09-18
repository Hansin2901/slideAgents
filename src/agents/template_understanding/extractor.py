from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class PlaceholderInfo(TypedDict, total=False):
    objectId: str
    placeholderType: str
    text: Optional[str]


class LayoutInfo(TypedDict, total=False):
    layoutId: str
    layoutName: Optional[str]
    placeHolders: List[PlaceholderInfo]


class PresentationSummary(TypedDict, total=False):
    presentationId: str
    title: Optional[str]
    slideCount: int
    layouts: List[LayoutInfo]


def _get(obj: Dict[str, Any], path: List[str], default=None):
    cur: Any = obj
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def summarize_presentation(pres: Dict[str, Any]) -> PresentationSummary:
    """Extract a compact summary of a Google Slides "presentations.get" JSON.

    Focus on: title, id, slide count, layouts and their placeholders.
    """
    pres_id = pres.get("presentationId") or pres.get("presentation_id") or ""
    title = pres.get("title")

    slides = pres.get("slides") or []
    slide_count = len(slides)

    # Layouts typically appear under "layouts" if requested; if missing, leave empty
    layouts_json = pres.get("layouts") or []
    layouts: List[LayoutInfo] = []

    for layout in layouts_json:
        layout_id = layout.get("objectId", "")
        layout_name = layout.get("layoutProperties", {}).get("displayName")
        page_elements = layout.get("pageElements", [])
        ph_list: List[PlaceholderInfo] = []
        for el in page_elements:
            placeholder = _get(el, ["shape", "placeholder"], None)
            if not placeholder:
                continue
            ph_type = placeholder.get("type")
            obj_id = el.get("objectId")
            text_content: Optional[str] = None
            # Try to extract any default text
            text = _get(el, ["shape", "text", "textElements"], [])
            if isinstance(text, list):
                buf: List[str] = []
                for t in text:
                    s = t.get("textRun", {}).get("content")
                    if s:
                        buf.append(s)
                if buf:
                    text_content = "".join(buf).strip()
            ph_list.append({
                "objectId": obj_id or "",
                "placeholderType": ph_type or "UNKNOWN",
                "text": text_content,
            })
        layouts.append({
            "layoutId": layout_id,
            "layoutName": layout_name,
            "placeHolders": ph_list,
        })

    return {
        "presentationId": pres_id,
        "title": title,
        "slideCount": slide_count,
        "layouts": layouts,
    }
