"""Debug helper for single layout explanation (graph path only).

Usage:
    uv run python scripts/debug_explain_single_layout.py <presentationId> <layoutObjectId>

Sets LAYOUT_DEBUG=1 and prints the resulting explanation JSON (truncated) plus
raw length/head via existing debug logs in the graph implementation.
"""
from __future__ import annotations
import os, sys, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.template_dal import get_layout_by_id, get_presentation, get_minimal_layout_geometry  # type: ignore
from src.agents.template_understanding.graph import explain_single_layout  # type: ignore


def _print_result(label: str, res: dict):
    print(f"\n--- {label} RESULT ---")
    if not res:
        print("<no result>")
        return
    print(json.dumps(res, ensure_ascii=False, indent=2)[:800])


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/debug_explain_single_layout.py <presentationId> <layoutObjectId>")
        return 1
    pres_id, layout_id = sys.argv[1:3]
    doc = get_presentation(pres_id)
    if not doc:
        print("Presentation not found")
        return 2
    layout = get_layout_by_id(pres_id, layout_id)
    if not layout:
        print("Layout not found")
        return 3

    os.environ['LAYOUT_DEBUG'] = '1'
    # Use minimal geometry view for LLM input
    min_input = get_minimal_layout_geometry(pres_id, layout_id) or {
        "objectId": layout_id,
        "name": (layout.get("layoutProperties") or {}).get("displayName"),
        "elements": [],
    }
    res_graph = explain_single_layout(min_input)
    _print_result('GRAPH PATH', res_graph)

    return 0

if __name__ == '__main__':
    raise SystemExit(main())
