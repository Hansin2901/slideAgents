from __future__ import annotations

from html.parser import HTMLParser
from typing import List

from .models import ListMarker, TextModel, TextRun


class _MiniHTMLToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.buf: List[str] = []
        self.stack: List[str] = []
        self.runs: List[TextRun] = []
        self.lists: List[ListMarker] = []

    def handle_starttag(self, tag: str, attrs):
        self.stack.append(tag)
        if tag in ("p", "br") and self.buf:
            self.buf.append("\n")

    def handle_endtag(self, tag: str):
        if tag in ("p", "li"):
            self.buf.append("\n")
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i] == tag:
                del self.stack[i]
                break

    def handle_data(self, data: str):
        if not data:
            return
        start = len("".join(self.buf))
        self.buf.append(data)
        end = len("".join(self.buf))
        bold = "b" in self.stack or "strong" in self.stack
        italic = "i" in self.stack or "em" in self.stack
        underline = "u" in self.stack
        if bold or italic or underline:
            self.runs.append(
                TextRun(
                    start=start,
                    end=end,
                    bold=bold or None,
                    italic=italic or None,
                    underline=underline or None,
                )
            )
        if "li" in self.stack:
            self.lists.append(ListMarker(start=start, end=end, type="unordered"))


def parse_inline_xml_to_textmodel(source: str) -> TextModel:
    parser = _MiniHTMLToText()
    try:
        parser.feed(source)
        raw_text = "".join(parser.buf).strip()
    except Exception:
        raw_text = source
    return TextModel(raw_text=raw_text, text_runs=parser.runs, list_markers=parser.lists)
