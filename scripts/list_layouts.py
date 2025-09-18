import os, sys, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from src.db.template_dal import get_presentation

load_dotenv()

import argparse

parser = argparse.ArgumentParser(description="List layout objectIds for a stored presentation")
parser.add_argument("presentation_id", help="Google Slides presentationId")
args = parser.parse_args()

doc = get_presentation(args.presentation_id)
if not doc:
    print("Presentation not found in DB")
    raise SystemExit(1)

pres = doc.get("presentationData") or {}
layouts = pres.get("layouts") or []
print(f"Found {len(layouts)} layouts")
for i,l in enumerate(layouts, start=1):
    oid = l.get("objectId")
    name = (l.get("layoutProperties") or {}).get("displayName")
    print(f"{i:02d}. {oid}  |  {name}")
