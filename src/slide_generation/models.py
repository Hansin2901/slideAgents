from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, TypedDict


class PlaceholderType(str, Enum):
    TITLE = "TITLE"
    SUBTITLE = "SUBTITLE"
    BODY = "BODY"
    PICTURE = "PICTURE"
    SLIDE_NUMBER = "SLIDE_NUMBER"
    OTHER = "OTHER"


@dataclass(frozen=True)
class Placeholder:
    type: PlaceholderType
    index: Optional[int]
    object_id: str


@dataclass(frozen=True)
class TemplateLayout:
    layout_id: str
    placeholders: List[Placeholder]


class PlanContent(TypedDict, total=False):
    # key: index as string or "null"
    # value: xml/html string
    pass


class PlanSlide(TypedDict):
    objectId: str
    content: Dict[str, PlanContent]
    instructions: Optional[str]


@dataclass
class TextRun:
    start: int
    end: int
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None


@dataclass
class ListMarker:
    start: int
    end: int
    type: str  # "ordered" | "unordered"


@dataclass
class TextModel:
    raw_text: str
    text_runs: List[TextRun] = field(default_factory=list)
    list_markers: List[ListMarker] = field(default_factory=list)


@dataclass
class ResolvedSlide:
    layout_id: str
    mappings: Dict[str, Dict[str, str]]  # TYPE -> { idx-or-null(str) -> pageElementId }
    parsed: Dict[str, Dict[str, TextModel]]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
