import os
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from src.agents.template_understanding.service import explain_and_store_single_layout


def main():
    load_dotenv()
    if len(sys.argv) < 3:
        print("Usage: uv run python scripts/explain_single_layout.py <presentationId> <layoutObjectId>")
        sys.exit(1)
    pres_id = sys.argv[1]
    layout_id = sys.argv[2]
    result = explain_and_store_single_layout(pres_id, layout_id)
    if not result:
        print("No result. Check presentationId/layoutObjectId inputs.")
        sys.exit(2)
    print("Stored explanation for:", layout_id)
    print(result)


if __name__ == "__main__":
    main()
