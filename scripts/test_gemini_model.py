#!/usr/bin/env python3
"""Quick CLI to sanity check Gemini model connectivity."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv


def _configure_client() -> None:
    load_dotenv()
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY environment variable is not set")
    genai.configure(api_key=api_key)


def _format_response(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return text
    if hasattr(response, "to_dict"):
        return json.dumps(response.to_dict(), indent=2)
    return repr(response)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ping a Gemini model with a simple prompt.")
    parser.add_argument("model", help="Gemini model name, e.g. gemini-2.0-flash")
    parser.add_argument(
        "--prompt",
        default="Say hello and identify yourself.",
        help="Text prompt to send to the model.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Request timeout in seconds (default: 120).",
    )
    args = parser.parse_args()

    _configure_client()

    model = genai.GenerativeModel(args.model)
    start = time.perf_counter()
    try:
        response = model.generate_content(
            args.prompt,
            request_options={"timeout": args.timeout},
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
