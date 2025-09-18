"""Batch explain all layouts for a presentation template.

Usage (Windows cmd):
  uv run python scripts/explain_all_layouts.py <presentationId>

Behavior:
- Fetches presentation by ID.
- Iterates each layout in presentationData.layouts.
- Skips layouts that already have a complete explanation (all three fields present).
- For each layout, calls existing single-layout explain+store logic with retry.
- Rate limited to <= 15 requests per minute INCLUDING retries.
- Produces a final report summary of successes, failures, skipped, and timing.

Environment:
Requires GOOGLE_API_KEY set (.env supported via existing code paths).
"""
from __future__ import annotations

import sys
import time
from typing import List, Dict, Any

import os
import sys as _sys

# Ensure project root (parent of scripts/) is on sys.path so 'src' package resolves
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

from src.db.template_dal import get_presentation  # type: ignore
from src.agents.template_understanding.service import explain_and_store_single_layout  # type: ignore

RATE_LIMIT_PER_MIN = 15
MIN_INTERVAL = 60.0 / RATE_LIMIT_PER_MIN  # seconds between requests (worst-case pacing)
MAX_RETRIES = 2  # total attempts = 1 + MAX_RETRIES
RETRY_BACKOFF = 2.0  # seconds, exponential base


def _now() -> float:
    return time.time()


def main(presentation_id: str) -> int:
    doc = get_presentation(presentation_id)
    if not doc:
        print(f"Presentation not found: {presentation_id}")
        return 1
    pres = doc.get("presentationData") or {}
    layouts: List[Dict[str, Any]] = pres.get("layouts") or []
    if not layouts:
        print("No layouts found in presentationData.layouts")
        return 1

    successes: List[str] = []
    failures: List[str] = []
    skipped: List[str] = []

    last_request_time = 0.0
    start_time = _now()

    for layout in layouts:
        layout_id = layout.get("objectId") or ""
        display_name = (layout.get("layoutProperties") or {}).get("displayName") or "(no name)"
        if not layout_id:
            print("Skipping layout without objectId")
            continue

        existing = layout.get("explanation") or {}
        if all(k in existing and existing.get(k) for k in ("generalDescription", "structuralDescription", "usageInstructions")):
            skipped.append(layout_id)
            continue

        attempts = 0
        success = False
        error_msg = None
        while attempts <= MAX_RETRIES and not success:
            attempts += 1
            # Rate limiting: ensure at least MIN_INTERVAL since last request
            elapsed_since_last = _now() - last_request_time
            if elapsed_since_last < MIN_INTERVAL:
                time.sleep(MIN_INTERVAL - elapsed_since_last)
            last_request_time = _now()

            try:
                result = explain_and_store_single_layout(presentation_id, layout_id)
                if not result:
                    error_msg = "No result returned"
                else:
                    # Treat InvocationError or SchemaError markers as failure allowing retry
                    gen_desc = result.get("generalDescription") or ""
                    if gen_desc.startswith("InvocationError:") or gen_desc.startswith("SchemaError:"):
                        error_msg = gen_desc.split("::", 1)[-1]
                    else:
                        success = True
                        successes.append(layout_id)
                        print(f"[OK] {layout_id} - {display_name}")
                        break
            except Exception as e:  # pragma: no cover - defensive catch
                error_msg = f"Exception: {e}"

            if not success and attempts <= MAX_RETRIES:
                backoff = RETRY_BACKOFF ** (attempts - 1)
                print(f"[RETRY] {layout_id} attempt {attempts} failed: {error_msg}. Backing off {backoff:.1f}s")
                time.sleep(backoff)

        if not success:
            failures.append(layout_id)
            print(f"[FAIL] {layout_id} - {display_name} :: {error_msg}")

    total_time = _now() - start_time
    print("\n=== Batch Layout Explanation Report ===")
    print(f"Presentation: {presentation_id}")
    print(f"Total layouts: {len(layouts)}")
    print(f"Explained (new): {len(successes)}")
    print(f"Skipped (already had explanation): {len(skipped)}")
    print(f"Failures: {len(failures)}")
    if failures:
        print("Failed layout IDs:")
        for lid in failures:
            print(f"  - {lid}")
    print(f"Elapsed time: {total_time:.1f}s")
    return 0 if not failures else 2


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/explain_all_layouts.py <presentationId>")
        raise SystemExit(1)
    sys.exit(main(sys.argv[1]))
