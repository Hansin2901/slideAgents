# Template Explainer Module

This document describes the current design of the per-layout template explanation subsystem.

## Purpose

Given a Google Slides template presentation, we generate structured, concise explanations for each layout so downstream agents (planner, workers) can select appropriate layouts and map user content reliably.

## Scope

-   Single-layout invocation model (one LLM call per layout)
-   Deterministic persistence of explanation under `presentationData.layouts[i].explanation`
-   Strict schema validation of LLM output (with graceful degradation on errors)

## Input (Layout Extract)

We pass a minimally transformed layout object to the model:

```
{
  "objectId": "g123abc...",
  "layoutProperties": { "displayName": "Title and Body" },
  "pageElements": [ ...raw element objects as needed... ]
}
```

Currently, we only guarantee these keys are present; additional raw keys may be added later for richer semantics (theme colors, master references, text styles, etc.).

## LLM Prompt Contract

Model must return a JSON array with exactly one object containing ONLY:

```
[
  {
    "generalDescription": string,
    "structuralDescription": string,
    "usageInstructions": string
  }
]
```

Constraints:

-   No extra fields.
-   No need to echo the layout id.
-   Each field concise (< ~1000 tokens target, soft constraint).

## Validation & Error Handling

`explain_single_layout(layout_input)` parses the raw response:

1. Must be valid JSON
2. Must be a non-empty array
3. First element must be an object
4. Must contain all required keys with non-null values

On failure, it returns a synthetic explanation object:

```
{
  "objectId": <input layout id>,
  "generalDescription": "SchemaError: <reason>",
  "structuralDescription": <raw model output>,
  "usageInstructions": ""
}
```

This preserves raw output for debugging while keeping downstream shape stable.

## Persistence

DAL method `set_layout_explanation(presentation_id, layout_object_id, explanation)` performs an in-place positional `$` update, avoiding rewriting the entire layouts array.

## Indexing

Compound index: `("presentationId", "presentationData.layouts.objectId")` accelerates:

-   Fetch single layout via `$elemMatch`
-   Positional updates for explanation

## Retrieval Flow

1. `service.explain_and_store_single_layout(presentation_id, layout_id)`
2. Fetch layout via `get_layout_by_id` (elemMatch projection)
3. Normalize / ensure required keys
4. Call `explain_single_layout`
5. Persist explanation via `set_layout_explanation`

## Extension Points

| Area | How to Extend | Notes |
| --- | --- | --- |
| Output fields | Add new keys to prompt + required list in validator | Bump tests in `test_graph_validation.py` |
| Layout enrichment | Add more raw properties to `layout_input` before invoke | Avoid renaming existing keys |
| Retry policy | Wrap call in retry loop (network / transient errors) | Use exponential backoff |
| Multi-layout batching | Build new graph to process a list; keep current for per-layout parallelism | Ensure ordering determinism |

## Adding a New Output Field Example

1. Decide new field, e.g. `designTips` (string)
2. Update prompt JSON spec snippet to include it
3. Update validator in `explain_single_layout` (`required_keys` list)
4. Adjust tests: add success path assertion + missing field case
5. Run tests (`uv run pytest -q`)

## Testing

-   DAL tests: `test_layout_dal.py`
-   Graph validation tests: `test_graph_validation.py` (schema error + success)

## Future Enhancements

-   Include placeholder geometry summary pre-processing (size, alignment buckets)
-   Add language fallback / translation memory
-   Add cached hash to skip re-explaining unchanged layouts
-   Cache layout geometry lookups (in-process or Redis) to reduce repeated Mongo calls
-   Integrate with orchestrator queue once implemented

## Rationale

A per-layout, strict JSON contract reduces coupling and isolates LLM variability. Rigid validation + atomic positional updates maintain data integrity and support safe parallelization.
