from __future__ import annotations

from typing import Dict, List, Tuple
import uuid

from .models import ResolvedSlide, TextModel


def _new_id(run_prefix: str, slide_seq: int, placeholder_type: str, idx_key: str) -> str:
    idx_part = idx_key if idx_key != "null" else "0"
    return f"p_{run_prefix}_{slide_seq}_{placeholder_type.lower()}_{idx_part}"


def _layout_placeholder_descriptor(placeholder_type: str, idx_key: str) -> dict:
    descriptor = {"type": placeholder_type}
    if idx_key != "null":
        try:
            descriptor["index"] = int(idx_key)
        except Exception:
            pass
    return descriptor


def textmodel_to_requests(object_id: str, text_model: TextModel) -> List[dict]:
    requests: List[dict] = []
    if not text_model.raw_text:
        return requests
    requests.append(
        {
            "insertText": {
                "objectId": object_id,
                "insertionIndex": 0,
                "text": text_model.raw_text,
            }
        }
    )
    for run in text_model.text_runs:
        style = {}
        fields: List[str] = []
        if run.bold is not None:
            style["bold"] = bool(run.bold)
            fields.append("bold")
        if run.italic is not None:
            style["italic"] = bool(run.italic)
            fields.append("italic")
        if run.underline is not None:
            style["underline"] = bool(run.underline)
            fields.append("underline")
        if fields:
            requests.append(
                {
                    "updateTextStyle": {
                        "objectId": object_id,
                        "textRange": {
                            "type": "FIXED_RANGE",
                            "startIndex": run.start,
                            "endIndex": run.end,
                        },
                        "style": style,
                        "fields": ",".join(fields),
                    }
                }
            )
    for marker in text_model.list_markers:
        preset = "BULLET_DISC_CIRCLE_SQUARE" if marker.type == "unordered" else "NUMBERED_DECIMAL_ALPHA_ROMAN"
        requests.append(
            {
                "createParagraphBullets": {
                    "objectId": object_id,
                    "textRange": {
                        "type": "FIXED_RANGE",
                        "startIndex": marker.start,
                        "endIndex": marker.end,
                    },
                    "bulletPreset": preset,
                }
            }
        )
    return requests


def build_slide_requests(slide_seq: int, resolved: ResolvedSlide, run_prefix: str | None = None) -> dict:
    if not run_prefix:
        run_prefix = uuid.uuid4().hex[:8]

    placeholder_id_mappings: List[dict] = []
    new_ids: Dict[Tuple[str, str], str] = {}
    for placeholder_type, per_index in resolved.mappings.items():
        for idx_key in per_index.keys():
            new_obj_id = _new_id(run_prefix, slide_seq, placeholder_type, idx_key)
            new_ids[(placeholder_type, idx_key)] = new_obj_id
            placeholder_id_mappings.append(
                {
                    "layoutPlaceholder": _layout_placeholder_descriptor(placeholder_type, idx_key),
                    "objectId": new_obj_id,
                }
            )

    requests: List[dict] = [
        {
            "createSlide": {
                "slideLayoutReference": {"layoutId": resolved.layout_id},
                "placeholderIdMappings": placeholder_id_mappings,
            }
        }
    ]

    for placeholder_type, per_index in resolved.parsed.items():
        for idx_key, text_model in per_index.items():
            object_id = new_ids.get((placeholder_type, idx_key))
            if not object_id:
                continue
            requests.extend(textmodel_to_requests(object_id, text_model))

    return {
        "layoutId": resolved.layout_id,
        "slideObjectId": None,
        "requests": requests,
        "placeholderObjectIds": {f"{ptype}:{idx}": obj_id for (ptype, idx), obj_id in new_ids.items()},
    }
