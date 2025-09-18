from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class Placeholder(BaseModel):
    object_id: str = Field(default="", description="Original objectId from layout element")
    placeholder_type: str = Field(default="UNKNOWN", description="Google Slides placeholder type")
    default_text: Optional[str] = Field(default=None, description="Any default text found")


class LayoutDescription(BaseModel):
    layout_id: str
    layout_name: Optional[str] = None
    placeholders: List[Placeholder] = []


class TemplateExplainRequest(BaseModel):
    presentation_id: str
    title: Optional[str]
    slide_count: int
    layouts: List[LayoutDescription]


class TemplateExplainResponse(BaseModel):
    presentation_id: str
    title: Optional[str]
    slide_count: int
    layout_explanations: List[str] = Field(
        default_factory=list,
        description="Natural language descriptions per layout, matching request.layouts order",
    )
    notes: Optional[str] = None
