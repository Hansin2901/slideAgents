import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path when running this script directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from pymongo import ASCENDING
from pymongo.errors import OperationFailure, CollectionInvalid

from src.db.mongo import get_db


def ensure_users(db):
    validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["_id", "userdata"],
            "properties": {
                "_id": {"bsonType": "string"},
                "userdata": {
                    "bsonType": "object",
                    "required": ["email"],
                    "properties": {
                        "email": {"bsonType": "string"},
                        "name": {"bsonType": ["string", "null"]},
                        "photo_url": {"bsonType": ["string", "null"]},
                        "provider": {"bsonType": ["string", "null"]},
                    },
                },
            },
        }
    }
    try:
        db.create_collection("users", validator=validator)
    except (OperationFailure, CollectionInvalid):
        # Already exists -> collMod (best-effort)
        try:
            db.command({"collMod": "users", "validator": validator})
        except OperationFailure:
            pass

    # Unique index on email
    db["users"].create_index([("userdata.email", ASCENDING)], unique=True, name="uniq_user_email")


def ensure_template(db):
    validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["presentationId", "ownerId", "presentationData"],
            "properties": {
                "presentationId": {"bsonType": "string"},
                "ownerId": {"bsonType": "string"},
                "presentationData": {"bsonType": "object"},
                "title": {"bsonType": ["string", "null"]},
            },
        }
    }
    try:
        db.create_collection("template", validator=validator)
    except (OperationFailure, CollectionInvalid):
        try:
            db.command({"collMod": "template", "validator": validator})
        except OperationFailure:
            pass

    # Indexes on ownerId and presentationId
    db["template"].create_index([("ownerId", ASCENDING)], name="idx_ownerId")
    db["template"].create_index([("presentationId", ASCENDING)], unique=True, name="uniq_presentationId")
    # Compound index to efficiently query a specific layout within a presentation
    db["template"].create_index(
        [("presentationId", ASCENDING), ("presentationData.layouts.objectId", ASCENDING)],
        name="idx_pres_layoutObjectId",
    )


def main():
    load_dotenv()
    db = get_db()
    ensure_users(db)
    ensure_template(db)
    print("Initialized MongoDB collections: users, template (validators + indexes)")


if __name__ == "__main__":
    main()
