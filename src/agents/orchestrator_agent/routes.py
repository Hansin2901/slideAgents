"""Flask blueprint exposing the orchestrator agent UI."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from google.oauth2.credentials import Credentials
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .data_handler import fetch_layout_data, get_user_content
from .orchestrator import generate_plan

try:  # pragma: no cover - optional database wiring
    from src.db.template_dal import list_presentations_for_user
except Exception:  # pragma: no cover - optional dependency
    list_presentations_for_user = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency wiring
    from src.slide_generation.planner_service import (
        MissingPlanError,
        resolve_plan_for_presentation,
    )
    from src.slide_generation.adapter import build_slide_requests
    from src.slide_generation.slides_api import send_batch_requests
except Exception:  # pragma: no cover - optional dependency wiring
    MissingPlanError = None  # type: ignore[assignment]
    resolve_plan_for_presentation = None  # type: ignore[assignment]
    build_slide_requests = None  # type: ignore[assignment]
    send_batch_requests = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

orchestrator_bp = Blueprint(
    "orchestrator",
    __name__,
    template_folder="templates",
    url_prefix="/orchestrator",
)


def _resolve_upload_dir() -> Path:
    upload_root = current_app.config.setdefault(
        "ORCHESTRATOR_UPLOAD_FOLDER",
        str(Path(current_app.instance_path) / "uploads"),
    )
    path = Path(upload_root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_snapshot_root() -> Path:
    snapshot_root = current_app.config.setdefault(
        "ORCHESTRATOR_OUTPUT_FOLDER",
        str(Path(current_app.instance_path) / "runs"),
    )
    root = Path(snapshot_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _create_snapshot_dir() -> Path:
    run_dir = _resolve_snapshot_root() / uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_snapshot(run_dir: Path, filename: str, payload: object) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    dest = run_dir / filename
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def _save_upload(file: FileStorage) -> Path:
    filename = secure_filename(file.filename or "user_upload")
    upload_dir = _resolve_upload_dir()
    dest = upload_dir / filename
    file.save(dest)
    return dest


def _handle_generation(file_path: Path, template_id: str):
    user_content = get_user_content(str(file_path))
    layout_data = fetch_layout_data(template_id)
    plan = generate_plan(user_content, layout_data)
    return plan


def _session_credentials() -> Optional[Credentials]:
    creds_data = session.get("credentials") or {}
    if not creds_data:
        return None
    try:
        return Credentials(**creds_data)
    except Exception:
        return None


def _build_requests_for_plan(
    template_id: str,
    owner_id: str | None,
    plan_dict: dict,
) -> list[dict]:
    if not resolve_plan_for_presentation or not build_slide_requests:
        raise RuntimeError("Slide generation modules unavailable")
    resolved = resolve_plan_for_presentation(template_id, owner_id, plan_dict)
    combined_requests: list[dict] = []
    run_prefix = uuid4().hex[:8]
    for idx, slide in enumerate(resolved, start=1):
        if slide.errors:
            joined = ", ".join(slide.errors)
            raise MissingPlanError(  # type: ignore[call-arg]
                f"Validation errors for layout '{slide.layout_id}': {joined}"
            )
        payload = build_slide_requests(idx, slide, run_prefix=run_prefix)
        combined_requests.extend(payload.get("requests", []))
    return combined_requests


def _load_user_templates() -> list[dict]:
    if not list_presentations_for_user:
        return []
    owner_id = session.get("user_id")
    if not owner_id:
        return []
    try:
        records = list_presentations_for_user(owner_id, limit=100)
    except Exception as exc:  # pragma: no cover - accessor best effort
        logger.debug("Failed to load templates for orchestrator form: %s", exc)
        return []

    templates: list[dict] = []
    for item in records or []:
        if isinstance(item, dict):
            presentation_id = item.get("presentationId") or item.get("id")
            title = item.get("title") or item.get("presentationTitle") or presentation_id
        else:
            presentation_id = getattr(item, "presentationId", None) or getattr(item, "id", None)
            title = getattr(item, "title", None) or getattr(item, "presentationTitle", None) or presentation_id
        if not presentation_id:
            continue
        templates.append({
            "presentation_id": presentation_id,
            "title": title or presentation_id,
        })
    return templates


def _send_plan_to_slides(
    template_id: str,
    plan_dict: dict,
    *,
    prebuilt_requests: list[dict] | None = None,
    snapshot_dir: Path | None = None,
) -> Optional[dict]:
    if not send_batch_requests or MissingPlanError is None:
        flash(
            "Slide generation pipeline unavailable; displaying JSON only.",
            "warning",
        )
        return None

    owner_id = session.get("user_id")
    creds = _session_credentials()
    if not owner_id or not creds:
        flash("Plan generated. Sign in to push updates to Slides.", "info")
        return None

    try:
        requests = prebuilt_requests or _build_requests_for_plan(template_id, owner_id, plan_dict)
    except MissingPlanError as exc:
        flash(str(exc), "error")
        return None

    if not requests:
        flash("No slide updates were generated from the plan.", "warning")
        return None

    if snapshot_dir and requests:
        try:
            _write_snapshot(snapshot_dir, "batch_request.json", requests)
        except Exception as exc:  # pragma: no cover - best effort persistence
            logger.warning("Failed to persist batch requests snapshot: %s", exc)

    try:
        response = send_batch_requests(template_id, requests, credentials_obj=creds)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.exception("Slides batchUpdate failed")
        flash(f"Failed to push plan to Slides: {exc}", "error")
        return None

    flash("Slides updated successfully.", "success")
    return response


@orchestrator_bp.route("/", methods=["GET", "POST"])
@orchestrator_bp.route("", methods=["GET", "POST"])
# @login_required  # Enable when auth is wired up
def orchestrate_presentation():
    if request.method == "POST":
        file: Optional[FileStorage] = request.files.get("user_file")
        template_choice = (request.form.get("template_choice") or "").strip()
        new_template_id = (request.form.get("new_template_id") or "").strip()

        template_id = template_choice
        if template_choice == "__add_new__":
            template_id = new_template_id

        if not file or not file.filename:
            flash("Please choose a content file to upload.", "error")
            return redirect(url_for("orchestrator.orchestrate_presentation"))
        if not template_id:
            flash("Template ID is required.", "error")
            return redirect(url_for("orchestrator.orchestrate_presentation"))

        saved_path = _save_upload(file)
        try:
            plan = _handle_generation(saved_path, template_id)
            plan_dict = plan.model_dump()
            result_json = json.dumps(plan_dict, indent=2)
            snapshot_dir = _create_snapshot_dir()
            plan_snapshot_path: Optional[Path] = None
            batch_snapshot_path: Optional[Path] = None

            try:
                plan_snapshot_path = _write_snapshot(snapshot_dir, "plan.json", plan_dict)
            except Exception as exc:  # pragma: no cover - best effort persistence
                logger.warning("Failed to persist plan snapshot: %s", exc)

            show_requests = bool(request.form.get("show_batch_requests"))
            batch_requests_json: Optional[str] = None
            batch_requests_payload: list[dict] | None = None

            if show_requests and plan_dict:
                try:
                    batch_requests_payload = _build_requests_for_plan(
                        template_id,
                        session.get("user_id"),
                        plan_dict,
                    )
                    batch_requests_json = json.dumps(batch_requests_payload, indent=2)
                    try:
                        batch_snapshot_path = _write_snapshot(
                            snapshot_dir,
                            "batch_request.json",
                            batch_requests_payload,
                        )
                    except Exception as exc:  # pragma: no cover - best effort persistence
                        logger.warning("Failed to persist preview batch requests snapshot: %s", exc)
                except MissingPlanError as exc:
                    flash(str(exc), "error")
                    batch_requests_payload = None
                except Exception as exc:  # pragma: no cover - diagnostic aid
                    logger.exception("Failed to build batch requests for display")
                    flash(f"Unable to build Slides batch requests: {exc}", "error")
                    batch_requests_payload = None

            slides_response = (
                _send_plan_to_slides(
                    template_id,
                    plan_dict,
                    prebuilt_requests=batch_requests_payload,
                    snapshot_dir=snapshot_dir,
                )
                if plan_dict
                else None
            )
            slides_response_json = (
                json.dumps(slides_response, indent=2) if slides_response else None
            )
            return render_template(
                "orchestrator_result.html",
                result_json=result_json,
                template_id=template_id,
                batch_requests_json=batch_requests_json,
                slides_response_json=slides_response_json,
                plan_snapshot_path=str(plan_snapshot_path) if plan_snapshot_path else None,
                batch_snapshot_path=str(batch_snapshot_path) if batch_snapshot_path else None,
            )
        except Exception as exc:  # pragma: no cover - interactive workflow
            logger.exception("Failed to generate presentation plan")
            flash(str(exc), "error")
            return redirect(url_for("orchestrator.orchestrate_presentation"))
        finally:
            try:
                saved_path.unlink(missing_ok=True)
            except Exception:  # pragma: no cover - cleanup best effort
                logger.debug("Failed to remove upload %s", saved_path)

    return render_template("orchestrator_form.html", templates=_load_user_templates())


__all__ = ["orchestrator_bp"]
