from datetime import datetime, timezone
from typing import Optional, Dict, Any

from .mongo import get_db
from pymongo.errors import DuplicateKeyError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_users_coll():
    return get_db()["users"]


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    return get_users_coll().find_one({"_id": user_id})


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    return get_users_coll().find_one({"userdata.email": email})


def upsert_user(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Insert or update a user document.

    profile expects keys: id, email, name (opt), photo_url (opt), provider (opt)
    """
    user_id = profile.get("id")
    email = profile.get("email")
    if not user_id or not email:
        raise ValueError("profile.id and profile.email are required")

    coll = get_users_coll()
    now = _now_iso()
    doc = {
        "_id": user_id,
        "userdata": {
            "email": email,
            "name": profile.get("name"),
            "photo_url": profile.get("photo_url"),
            "provider": profile.get("provider", "google"),
        },
        "created_at": now,
        "updated_at": now,
    }

    existing = coll.find_one({"_id": user_id})
    if existing:
        update = {
            "$set": {
                "userdata.email": email,
                "userdata.name": profile.get("name"),
                "userdata.photo_url": profile.get("photo_url"),
                "userdata.provider": profile.get("provider", "google"),
                "updated_at": now,
            }
        }
        coll.update_one({"_id": user_id}, update)
        return coll.find_one({"_id": user_id})
    else:
        try:
            coll.insert_one(doc)
        except DuplicateKeyError:
            # Fallback read in case of race
            pass
        return coll.find_one({"_id": user_id})
