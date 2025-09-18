# Project Progress Summary

Date: 2025-09-06

## Overview

This document summarizes the work completed during the current development session. It covers OAuth setup, MongoDB integration, DALs, database initialization, unit tests, Slides template management (add/remove), and supporting tooling/config changes.

## Achievements

-   Added a working Flask app with Google OAuth and People API integration.
-   Integrated MongoDB Atlas with connection helpers, schema validation, and indexes.
-   Implemented Users and Template data access layers (DALs) with tests.
-   Built dashboard login flow that persists users to DB and reads profile data from DB.
-   Implemented add/remove Google Slides templates via Slides API and stored full presentation JSON.
-   Set up uv-based Python project config and environment loading via dotenv.
-   Verified database connectivity and indexes against the live cluster.

## Key Features Delivered

-   OAuth login flow (Google):

    -   Routes: `/`, `/login`, `/callback`, `/dashboard`, `/logout`, `/me` in `app.py`.
    -   Scopes: `openid`, `userinfo.email`, `userinfo.profile`, and `presentations.readonly` for Slides read.
    -   Session stores credentials (including `id_token`) and `user_id`.
    -   Defensive credential rebuild and state validation.

-   User persistence & usage:

    -   On callback, upsert user to `users` collection and store `session['user_id']`.
    -   Dashboard prefers DB user fields (name/email/photo) with People API fallback.
    -   `/me` returns the current user’s DB record as JSON.

-   Templates management (Slides):
    -   Dashboard lists user’s templates with Open/Remove actions.
    -   Add template by pasting a Slides URL; extracts `presentationId`, fetches with Slides API `presentations.get`, and saves.
    -   Remove template deletes the record scoped to the current user.
    -   User feedback via flash messages; detects insufficient scope and instructs re-login.

## Data Layer & Database

-   Mongo helpers and configuration:

    -   `src/db/mongo.py`: central client and DB retrieval using `.env` (`MONGODB_URI`, `MONGODB_DB_NAME`).
    -   `.env.example` added and `.env` consumption via `python-dotenv`.

-   Users DAL (`src/db/users_dal.py`):

    -   `upsert_user(profile)`, `get_user(user_id)`, `get_user_by_email(email)`.
    -   Stores `userdata.email`, `name`, `photo_url`, `provider` with timestamps.

-   Template DAL (`src/db/template_dal.py`):

    -   `create_or_replace_presentation(presentation_id, owner_id, data, title)`.
    -   `get_presentation(presentation_id)`, `list_presentations_for_user(user_id, limit, skip)`.
    -   New: `delete_presentation(presentation_id, owner_id)`.

-   DB initialization (`scripts/init_db.py`):

    -   Ensures validators:
        -   `users`: requires `_id`, `userdata.email`.
        -   `template`: requires `presentationId`, `ownerId`, `presentationData`.
    -   Ensures indexes:
        -   `users`: unique on `userdata.email`.
        -   `template`: `idx_ownerId`, unique `uniq_presentationId`.
    -   Idempotent and resilient to existing collections.

-   DB verification (`scripts/verify_db.py`):
    -   Pings DB, lists collections, and prints index info for `users` and `template`.

## Tests & Tooling

-   Tests:

    -   `tests/test_users_dal.py`: insert/update and retrieval behavior using `mongomock`.
    -   `tests/test_template_dal.py`: create/list behaviors for templates.
    -   `tests/conftest.py`: sys.path setup for `src` imports.
    -   Result: all tests passing (3 passed).

-   Tooling & config:
    -   `pyproject.toml` with uv-managed dependencies.
    -   `.gitignore` updated to include secrets and test artifacts (`tests/`, `.pytest_cache/`, coverage files).
    -   `.github/copilot-instructions.md` added with repo-specific guidance, architecture, data model, and conventions.

## Slides API Usage Notes

-   We use `google-api-python-client` to build `slides` service and call:
    -   `slides.presentations().get(presentationId=...)` to fetch presentation JSON.
-   Required scope: `https://www.googleapis.com/auth/presentations.readonly`.
-   If the consent was granted before scope update, a logout/login is needed to refresh scopes.

## Quality Gates

-   Lint/Typecheck: N/A (not configured), import smoke tests pass (`import app`).
-   Unit tests: PASS (3 tests).
-   DB smoke tests: PASS (ping OK; indexes present on `users` and `template`).

## Files Added/Modified (highlights)

-   `app.py`: OAuth flow, user upsert, `/me`, dashboard updates, templates add/remove.
-   `src/db/mongo.py`, `src/db/users_dal.py`, `src/db/template_dal.py` (added delete helper).
-   `scripts/init_db.py` (idempotent), `scripts/verify_db.py`.
-   `.env.example`, `.gitignore` (secrets/tests), `pyproject.toml` (uv), `.github/copilot-instructions.md`.
