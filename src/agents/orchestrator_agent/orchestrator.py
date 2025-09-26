"""Core orchestration logic for generating presentation plans."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict, Optional

import google.generativeai as genai
from pydantic import ValidationError

try:  # pragma: no cover - defensive import
    from instructor import from_generativeai
except ImportError:  # pragma: no cover - compatibility fallback
    from_generativeai = None  # type: ignore[assignment]

try:  # pragma: no cover - defensive import
    from instructor import Mode
except ImportError:  # pragma: no cover - fallback for older instructor
    Mode = None

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore[assignment]

from .models import PresentationPlan
from .prompts import MASTER_PROMPT

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = os.environ.get("ORCHESTRATOR_GEMINI_MODEL", "gemini-2.5-flash")
_DEFAULT_PROVIDER = os.environ.get("ORCHESTRATOR_PROVIDER", "gemini").lower()
_DEFAULT_OPENAI_MODEL = os.environ.get("ORCHESTRATOR_OPENAI_MODEL", "gpt-4.1-mini")


@lru_cache(maxsize=None)
def _build_client(model_name: str = _DEFAULT_MODEL) -> tuple[Optional[Any], Any]:
    """Configure the Gemini client and return Instructor (if available) plus base client."""

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY must be set to call Gemini.")

    genai.configure(api_key=api_key)
    base_model = genai.GenerativeModel(model_name)

    if from_generativeai is None:
        logger.warning(
            "Instructor 'from_generativeai' helper not available; falling back to raw Gemini calls.",
        )
        return None, base_model

    if Mode is not None:
        instructor_client = from_generativeai(base_model, mode=Mode.GENERATE_CONTENT)
    else:  # pragma: no cover - compatibility path
        instructor_client = from_generativeai(base_model)
    return instructor_client, base_model


def _compose_prompt(content: str, layout: Dict[str, Any]) -> str:
    """Combine system prompt, layout summary, and content into a single string."""

    layout_json = json.dumps(layout, indent=2)
    return (
        f"{MASTER_PROMPT}\n\n"
        "# Layout Summary\n"
        f"```json\n{layout_json}\n```\n\n"
        "# User Content\n"
        f"{content}\n"
    )


def _extract_json_payload(text: str) -> str:
    """Strip Markdown fences or prose from Gemini output to leave raw JSON."""

    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Drop the opening backticks and optional language tag
        cleaned = cleaned[3:]
        if cleaned.lower().startswith("json"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


@lru_cache(maxsize=None)
def _build_openai_client() -> OpenAI:
    if OpenAI is None:
        raise RuntimeError(
            "openai package is not installed. Install 'openai' to use OpenAI models.",
        )
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY must be set to call OpenAI models.")
    return OpenAI(api_key=api_key)


def _invoke_openai(prompt: str, model_name: Optional[str]) -> PresentationPlan:
    client = _build_openai_client()
    chosen_model = model_name or _DEFAULT_OPENAI_MODEL
    try:
        response = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": MASTER_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as exc:  # pragma: no cover - network dependent
        logger.exception("OpenAI chat completion failed")
        raise

    message = response.choices[0].message
    content = message.content
    if isinstance(content, list):
        text = "".join(getattr(part, "text", "") for part in content)
    else:
        text = content or ""
    text = text.strip()
    if not text:
        raise RuntimeError("OpenAI response did not include content")
    try:
        return PresentationPlan.model_validate_json(text)
    except ValidationError:
        data = json.loads(text)
        return PresentationPlan.model_validate(data)


def generate_plan(
    content: str,
    layout: Dict[str, Any],
    *,
    model_name: Optional[str] = None,
) -> PresentationPlan:
    """Generate a structured presentation plan using the configured LLM provider."""

    if not content:
        raise ValueError("content must not be empty")
    if not layout:
        raise ValueError("layout must not be empty")

    prompt = _compose_prompt(content, layout)
    logger.debug("Generated orchestrator prompt (%d chars)", len(prompt))

    provider = (os.environ.get("ORCHESTRATOR_PROVIDER") or _DEFAULT_PROVIDER).lower()
    if provider == "openai":
        return _invoke_openai(prompt, model_name)

    return _invoke_gemini(prompt, model_name or _DEFAULT_MODEL)


def _invoke_gemini(prompt: str, model_name: str) -> PresentationPlan:
    instructor_client, base_model = _build_client(model_name)
    response: Optional[PresentationPlan] = None

    if instructor_client is not None:
        try:
            response = instructor_client.create(
                response_model=PresentationPlan,
                messages=[{"role": "user", "content": prompt}],
                model=model_name or _DEFAULT_MODEL,
            )
        except ValidationError as exc:
            logger.error("LLM returned invalid payload: %s", exc)
            raise
        except AttributeError:
            logger.debug("Instructor client missing 'create'; falling back to raw Gemini call")
        except Exception as exc:  # pragma: no cover - network dependent
            logger.exception("Gemini invocation failed")
            raise

    if response is None:
        raw = base_model.generate_content(prompt)
        text = getattr(raw, "text", None) or ""
        if not text:
            logger.error("Gemini response did not include text payload")
            raise RuntimeError("Gemini response did not include text output")
        payload = _extract_json_payload(text)
        try:
            response = PresentationPlan.model_validate_json(payload)
        except ValidationError:
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                logger.error("Gemini response not valid JSON: %s", exc)
                raise RuntimeError("Gemini response not valid JSON output") from exc
            response = PresentationPlan.model_validate(data)

    logger.info("Generated presentation plan with %d slides", len(response.presentation_plan))
    return response


__all__ = ["generate_plan"]
