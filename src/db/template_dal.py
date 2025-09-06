from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from .mongo import get_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_template_coll():
    return get_db()["template"]


def get_presentation(presentation_id: str) -> Optional[Dict[str, Any]]:
    return get_template_coll().find_one({"presentationId": presentation_id})


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
