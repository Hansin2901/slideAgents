"""Pydantic models that shape the orchestrator agent output."""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field


class SlidePlan(BaseModel):
    """Structured representation for a single slide in the presentation plan."""

    objectId: str = Field(description="The unique ID of the slide layout.")
    content: Dict[str, Dict[str, str]] = Field(
        description="Mapping of placeholder types to their indexed content.",
    )
    instructions: str = Field(
        description="Concise, human-readable instructions for the slide.",
    )


class PresentationPlan(BaseModel):
    """Top-level container for the full presentation plan payload."""

    presentation_plan: List[SlidePlan]


__all__ = ["PresentationPlan", "SlidePlan"]
