import os
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from src.agents.template_understanding.service import explain_template_from_db


def main():
    load_dotenv()
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/explain_template.py <presentationId>")
        sys.exit(1)
    pres_id = sys.argv[1]
    resp = explain_template_from_db(pres_id)
    if not resp:
        print("No presentation found for:", pres_id)
        sys.exit(2)
    print("Presentation:", resp.title or resp.presentation_id)
    print("Slide count:", resp.slide_count)
    print("\nLayout explanations:\n")
    for i, text in enumerate(resp.layout_explanations, 1):
        print(f"-- Layout {i} --")
        print(text)
        print()


if __name__ == "__main__":
    main()
