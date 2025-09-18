from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from .mongo import get_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_template_coll():
    return get_db()["template"]


def get_presentation(presentation_id: str, owner_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query: Dict[str, Any] = {"presentationId": presentation_id}
    if owner_id:
        query["ownerId"] = owner_id
    return get_template_coll().find_one(query)


def list_presentations_for_user(user_id: str, limit: int = 20, skip: int = 0) -> List[Dict[str, Any]]:
    cursor = (
        get_template_coll()
        .find({"ownerId": user_id})
        .sort("created_at", -1)
        .skip(int(skip))
        .limit(int(limit))
    )
    return list(cursor)


def create_or_replace_presentation(presentation_id: str, owner_id: str, data: Dict[str, Any], title: Optional[str] = None) -> Dict[str, Any]:
    if not presentation_id:
        raise ValueError("presentation_id is required")
    if not owner_id:
        raise ValueError("owner_id is required")
    if not isinstance(data, dict):
        raise ValueError("data must be a dict of Slides JSON")

    coll = get_template_coll()
    now = _now_iso()
    update = {
        "$set": {
            "presentationId": presentation_id,
            "ownerId": owner_id,
            "presentationData": data,
            "title": title,
            "updated_at": now,
        },
        "$setOnInsert": {"created_at": now},
    }
    coll.update_one({"presentationId": presentation_id}, update, upsert=True)
    return coll.find_one({"presentationId": presentation_id})


def delete_presentation(presentation_id: str, owner_id: str) -> bool:
    """Delete a template by presentationId scoped to owner.

    Returns True if a document was deleted, False otherwise.
    """
    if not presentation_id or not owner_id:
        return False
    res = get_template_coll().delete_one({"presentationId": presentation_id, "ownerId": owner_id})
    return res.deleted_count > 0


def get_layout_by_id(presentation_id: str, layout_object_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single layout object.

    NOTE: Earlier implementation attempted to use $elemMatch in projection on the
    nested path 'presentationData.layouts', which MongoDB disallows (error 31275).
    We instead project the full layouts array then filter client-side. For typical
    template sizes this is acceptable; if layouts become very large, switch to an
    aggregation pipeline with $filter.
    """
    doc = get_template_coll().find_one(
        {"presentationId": presentation_id, "presentationData.layouts.objectId": layout_object_id},
        {"presentationData.layouts": 1, "_id": 0},
    )
    if not doc:
        return None
    for l in (doc.get("presentationData") or {}).get("layouts", []) or []:
        if l.get("objectId") == layout_object_id:
            return l
    return None


def set_layout_explanation(presentation_id: str, layout_object_id: str, explanation: Dict[str, Any]) -> bool:
    """Set the explanation subdocument on the matched layout using positional operator.

    Returns True if a document was modified.
    """
    res = get_template_coll().update_one(
        {"presentationId": presentation_id, "presentationData.layouts.objectId": layout_object_id},
        {"$set": {"presentationData.layouts.$.explanation": explanation}},
    )
    return res.modified_count > 0


def set_template_explanation(presentation_id: str, owner_id: str, explanation: Dict[str, Any]) -> bool:
    """Set or replace a top-level template explanation document.

    Stores under key 'templateExplanation'. Does not modify layout explanations.
    """
    if not presentation_id or not owner_id or not isinstance(explanation, dict):
        return False
    res = get_template_coll().update_one(
        {"presentationId": presentation_id, "ownerId": owner_id},
        {"$set": {"templateExplanation": explanation, "updated_at": _now_iso()}},
    )
    return res.modified_count > 0


def get_template_explanation(presentation_id: str, owner_id: str) -> Optional[Dict[str, Any]]:
    """Return stored templateExplanation if present."""
    if not presentation_id or not owner_id:
        return None
    doc = get_template_coll().find_one(
        {"presentationId": presentation_id, "ownerId": owner_id}, {"templateExplanation": 1, "_id": 0}
    )
    if not doc:
        return None
    return doc.get("templateExplanation")


def migrate_owner_presentations(old_owner_id: str, new_owner_id: str) -> int:
    """Reassign all presentations owned by old_owner_id to new_owner_id.

    Returns the number of modified documents. No-op if inputs invalid or identical.
    """
    if not old_owner_id or not new_owner_id or old_owner_id == new_owner_id:
        return 0
    res = get_template_coll().update_many(
        {"ownerId": old_owner_id},
        {"$set": {"ownerId": new_owner_id, "updated_at": _now_iso()}},
    )
    return int(getattr(res, "modified_count", 0))


def _to_number(val: Any) -> Optional[float]:
    """Best-effort convert extended JSON numeric or native numeric to float.

    Handles cases like {"$numberDouble": "12.3"} or {"$numberInt": "10"} when data
    was imported from Extended JSON, and plain int/float when stored natively.
    Returns None if conversion is not possible.
    """
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        for k in ("$numberDouble", "$numberInt", "$numberLong", "$numberDecimal"):
            if k in val:
                try:
                    return float(val[k])
                except Exception:
                    return None
    return None


def get_minimal_layout_geometry(presentation_id: str, layout_object_id: str) -> Optional[Dict[str, Any]]:
    """Return a compact geometry-only view of a layout using an aggregation pipeline.

    Shape:
      {
        objectId: <str>,
        name: <str|None>,
        elements: [
          {
            loc: { x: <num|None>, y: <num|None> },
            size: { width: <num|None>, height: <num|None> }
          }, ...
        ]
      }

    Falls back to client-side extraction if aggregation features are unavailable.
    """
    coll = get_template_coll()
    try:
        pipeline = [
            {
                "$match": {
                    "presentationId": presentation_id,
                    "presentationData.layouts.objectId": layout_object_id,
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "layout": {
                        "$first": {
                            "$filter": {
                                "input": "$presentationData.layouts",
                                "as": "l",
                                "cond": {"$eq": ["$$l.objectId", layout_object_id]},
                            }
                        }
                    },
                }
            },
            {
                "$project": {
                    "objectId": "$layout.objectId",
                    "name": "$layout.layoutProperties.displayName",
                    "elements": {
                        "$map": {
                            "input": {"$ifNull": ["$layout.pageElements", []]},
                            "as": "e",
                            "in": {
                                "placeHolderType": {"$ifNull": ["$$e.shape.placeholder.type", None]},
                                "placeHolderIndex": {
                                    "$let": {
                                        "vars": {"idx": "$$e.shape.placeholder.index"},
                                        "in": {
                                            "$convert": {
                                                "input": {"$ifNull": [
                                                    "$$idx.$numberInt",
                                                    {"$ifNull": ["$$idx.$numberDouble", "$$idx"]}
                                                ]},
                                                "to": "int",
                                                "onError": None,
                                                "onNull": None,
                                            }
                                        }
                                    }
                                },
                                "loc": {
                                    "x": {
                                        "$let": {
                                            "vars": {"tx": "$$e.transform.translateX"},
                                            "in": {
                                                "$convert": {
                                                    "input": {"$ifNull": ["$$tx.$numberDouble", {"$ifNull": ["$$tx.$numberInt", "$$tx"]}]},
                                                    "to": "double",
                                                    "onError": None,
                                                    "onNull": None,
                                                }
                                            }
                                        }
                                    },
                                    "y": {
                                        "$let": {
                                            "vars": {"ty": "$$e.transform.translateY"},
                                            "in": {
                                                "$convert": {
                                                    "input": {"$ifNull": ["$$ty.$numberDouble", {"$ifNull": ["$$ty.$numberInt", "$$ty"]}]},
                                                    "to": "double",
                                                    "onError": None,
                                                    "onNull": None,
                                                }
                                            }
                                        }
                                    },
                                },
                                "size": {
                                    "width": {
                                        "$let": {
                                            "vars": {"w": "$$e.size.width.magnitude"},
                                            "in": {
                                                "$convert": {
                                                    "input": {"$ifNull": ["$$w.$numberDouble", {"$ifNull": ["$$w.$numberInt", "$$w"]}]},
                                                    "to": "double",
                                                    "onError": None,
                                                    "onNull": None,
                                                }
                                            }
                                        }
                                    },
                                    "height": {
                                        "$let": {
                                            "vars": {"h": "$$e.size.height.magnitude"},
                                            "in": {
                                                "$convert": {
                                                    "input": {"$ifNull": ["$$h.$numberDouble", {"$ifNull": ["$$h.$numberInt", "$$h"]}]},
                                                    "to": "double",
                                                    "onError": None,
                                                    "onNull": None,
                                                }
                                            }
                                        }
                                    },
                                },
                            },
                        }
                    },
                }
            },
        ]
        cur = coll.aggregate(pipeline)
        doc = next(cur, None)
        if doc:
            return {
                "objectId": doc.get("objectId"),
                "name": doc.get("name"),
                "elements": doc.get("elements", []) or [],
            }
    except Exception:
        # Fall through to client-side extraction
        pass

    # Fallback path: fetch the full layout then project in Python
    layout = get_layout_by_id(presentation_id, layout_object_id)
    if not layout:
        return None
    els = []
    for e in (layout.get("pageElements") or []) or []:
        tr = e.get("transform") or {}
        sz = e.get("size") or {}
        ph = ((e.get("shape") or {}).get("placeholder") or {})
        ph_type = ph.get("type")
        ph_idx_raw = ph.get("index")
        ph_idx_num = _to_number(ph_idx_raw)
        ph_index = int(ph_idx_num) if ph_idx_num is not None else None
        width = _to_number(((sz.get("width") or {}).get("magnitude"))) if isinstance(sz, dict) else None
        height = _to_number(((sz.get("height") or {}).get("magnitude"))) if isinstance(sz, dict) else None
        x = _to_number(tr.get("translateX"))
        y = _to_number(tr.get("translateY"))
        els.append({
            "placeHolderType": ph_type,
            "placeHolderIndex": ph_index,
            "loc": {"x": x, "y": y},
            "size": {"width": width, "height": height},
        })
    return {
        "objectId": layout.get("objectId"),
        "name": ((layout.get("layoutProperties") or {}).get("displayName")),
        "elements": els,
    }
