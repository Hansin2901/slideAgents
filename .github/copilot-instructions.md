# Copilot Instructions for slideAgents

Purpose: Enable AI coding agents to be productive immediately in this repo by capturing the architecture, workflows, and conventions actually used here. Always use uv for this project. Do not add any emojis.

## Big picture

-   Goal: Given a presentation template and user content, generate Google Slides that follow the template.
-   Three core roles (see `README.md` and `AGENTS.md`):
    -   Template Understanding LLM: parse the template into layout descriptions usable by code/agents.
    -   Orchestrator/Planner Agent: turns user content + layouts into a presentation plan (slides, chosen layouts, content-to-placeholder mapping, deterministic IDs), collects approvals, enqueues tasks.
    -   Worker Agent(s): consume slide tasks, perform Google Slides API actions with retries and report results back.
-   Parallelism: multiple workers can build different slides concurrently. Failures are isolated per slide.
-   State: tracked in a DB (see `docs/sw/dataModel.md`), with collections for `users`, `presentations`, `conversations`, and `tasks`.

## Data & IDs

-   Persist full Google Slides JSON for each presentation under `presentations.presentationData` plus metadata.
-   Task granularity is slide-level. Each task links `userId`, `presentationId`, and `conversationId`.
-   Deterministic object IDs for slide elements: planner proposes base IDs like `textbox_1`, code should prefix with slide number, e.g., `sld_1_textbox_1` to ensure global uniqueness.

## Workflows

-   Auth: Start with Google OAuth to access Slides; see "OauthInstructions.md" referenced by `docs/sw/workflowDescription.md` (add implementation/docs here when wiring code).
-   Template ingestion: pass the template presentation to the Template Understanding LLM and store layout descriptions.
-   Planning loop: orchestrator prepares a plan, requests user approval/feedback, then enqueues slide tasks.
-   Execution: workers translate tasks to concrete Google Slides API calls, validate inputs, retry up to 5 times on failures, and report success/failure with explanations.
-   User feedback: orchestrator summarizes progress to the user and updates the task list; update tasks may require current slide state.

## Conventions

-   Repo layout today is docs-first. When adding code:
    -   Use `src/` for implementation and `tests/` mirrored by package/module.
    -   Organize by agent role: `src/orchestrator/`, `src/agents/template-understanding/`, `src/agents/worker/`.
    -   Keep diagram sources in `xcaliDraw-Diagrams.excalidraw`; export PNGs to `docs/sw/`.
-   Naming:
    -   Files/dirs: snake_case for code; kebab-case for assets/images; PascalCase for classes.
    -   Slide object IDs: `sld_<n>_<kind>_<i>` (e.g., `sld_3_title_1`).
-   Messaging: maintain conversation history per user/presentation in `conversations.messages` for context and auditing.

## External integrations

-   Google Slides API (and Drive for template access). Plan for rate limits and partial failures; workers should be idempotent where possible.
-   Database: target MongoDB (see data model). Ensure indices on foreign keys (`ownerId`, `userId`, `presentationId`, `conversationId`).

## Examples from docs

-   High-level flow and diagrams: `docs/sw/high_level_overview.png`, `docs/sw/system_diagram.png`.
-   Workflow details: `docs/sw/workflowDescription.md`.
-   Data model (mermaid ERD): `docs/sw/dataModel.md`.

## What to implement next (practical steps)

-   Bootstrap minimal services:
    -   Auth module for Google OAuth and token management.
    -   Data models for the four collections (users, presentations, conversations, tasks).
    -   Orchestrator with a planning endpoint, task queue interface, and status reporting.
    -   Worker that accepts a task payload and executes Slides API mutations with up to 5 retries.
-   Add `README.md` sections with run commands and env vars once code exists.

If any section here doesn’t match current direction or you have library/runtime preferences (Node, Python, etc.), please add them and we’ll refine these instructions.
