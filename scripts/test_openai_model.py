#!/usr/bin/env python3
"""Quick CLI to sanity check OpenAI model connectivity."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Tuple

from dotenv import load_dotenv


def _load_pdf_text(pdf_path: str) -> Tuple[str, int]:
    try:
        import fitz  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Reading PDFs requires pymupdf; install it with 'uv add pymupdf' or pip."
        ) from exc

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    combined = "\n\n".join(pages)
    return combined.strip(), doc.page_count

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover - fail fast when dependency missing
    raise SystemExit("Install the 'openai' package to use this script.") from exc


def _configure_client() -> OpenAI:
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key)


def _format_response(resp: Any) -> str:
    try:
        message = resp.choices[0].message
    except (AttributeError, IndexError):
        return repr(resp)
    content = message.content
    if isinstance(content, list):
        return "".join(getattr(part, "text", "") for part in content)
    return content or ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Ping an OpenAI chat model with a simple prompt.")
    parser.add_argument("model", help="OpenAI model name, e.g. gpt-4.1-mini")
    parser.add_argument(
        "--prompt",
        default="Say hello and identify yourself.",
        help="Text prompt to send to the model.",
    )
    parser.add_argument(
        "--pdf",
        help="Optional PDF file whose extracted text will be appended to the prompt.",
    )
    args = parser.parse_args()

    client = _configure_client()

    pdf_text = ""
    pdf_pages = 0
    if args.pdf:
        pdf_text, pdf_pages = _load_pdf_text(args.pdf)
        print(
            f"Loaded PDF '{args.pdf}' ({pdf_pages} pages, {len(pdf_text):,} characters)",
            file=sys.stderr,
        )

    start = time.perf_counter()
    try:
        user_message = args.prompt
        if pdf_text:
            user_message = (
                f"{args.prompt}\n\n"
                "[PDF CONTENT]\n"
                f"{pdf_text}"
            )
        response = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": "You are a quick connectivity smoke test."},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as exc:  # pragma: no cover - network interaction
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - start

    print(f"Model: {args.model}")
    print(f"Elapsed: {elapsed:.2f}s")
    print("Response:\n")
    print(_format_response(response))
    return 0


if __name__ == "__main__":
    sys.exit(main())
