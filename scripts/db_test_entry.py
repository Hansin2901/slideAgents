"""Utility script to create a test presentation entry and update explanations.

Usage:
  uv run python scripts/db_test_entry.py create
  uv run python scripts/db_test_entry.py update-layout <layoutObjectId>
  uv run python scripts/db_test_entry.py update-template

Requires MONGODB_URI env set. Designed for quick manual smoke checks.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from src.db.template_dal import (
    create_or_replace_presentation,
    get_presentation,
    set_layout_explanation,
    set_template_explanation,
)

TEST_PRESENTATION_ID = "TEST_PRESENTATION_DB_ENTRY"
TEST_OWNER_ID = "TEST_OWNER"


def _now():
    return datetime.now(timezone.utc).isoformat()


def cmd_create():
    # Minimal fake presentationData with one layout
    pres_json = {
        "presentationId": TEST_PRESENTATION_ID,
        "title": "Test Presentation",
        "layouts": [
            {
                "objectId": "layout_1",
                "layoutProperties": {"displayName": "Title & Body"},
                "pageElements": [],
            }
        ],
        "slides": [],
    }
    doc = create_or_replace_presentation(TEST_PRESENTATION_ID, TEST_OWNER_ID, pres_json, title="Test Presentation")
    print("Created/Updated test presentation.")
    print({k: doc.get(k) for k in ["presentationId", "ownerId", "title", "updated_at"]})


def cmd_update_layout(layout_id: str):
    explanation = {
        "objectId": layout_id,
        "generalDescription": "Layout for testing (" + _now() + ")",
        "structuralDescription": "Structure placeholder",
        "usageInstructions": "Use only in tests.",
    }
    ok = set_layout_explanation(TEST_PRESENTATION_ID, layout_id, explanation)
    print("Layout explanation set?", ok)
    doc = get_presentation(TEST_PRESENTATION_ID)
    if doc:
        for l in (doc.get("presentationData") or {}).get("layouts", []):
            if l.get("objectId") == layout_id:
                print("Stored explanation:", l.get("explanation"))


def cmd_update_template():
    explanation = {
        "generalDescription": "Template level explanation " + _now(),
        "structuralDescription": "Template structure placeholder",
        "usageInstructions": "Testing only.",
    }
    ok = set_template_explanation(TEST_PRESENTATION_ID, TEST_OWNER_ID, explanation)
    print("Template explanation set?", ok)
    doc = get_presentation(TEST_PRESENTATION_ID)
    if doc:
        print("Stored templateExplanation:", doc.get("templateExplanation"))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "create":
        cmd_create()
    elif cmd == "update-layout":
        if len(sys.argv) < 3:
            print("Need layout object id")
            return
        cmd_update_layout(sys.argv[2])
    elif cmd == "update-template":
        cmd_update_template()
    else:
        print("Unknown command")


if __name__ == "__main__":
    main()
