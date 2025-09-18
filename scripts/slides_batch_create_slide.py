"""Run a Google Slides batchUpdate to create a slide and insert text.

Usage (Windows cmd):
  uv run python scripts\slides_batch_create_slide.py
  # or override presentationId and layoutId
  uv run python scripts\slides_batch_create_slide.py --presentation 1PAGmCAxZtO9gWk0eYAUpTICubU0EoCyOfGJuc1yi7FY --layout p28

Auth:
- Requires a Google OAuth client secret JSON in the repo root (client_secret_*.json).
- Tokens will be saved to token.json next to this script after first run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request


SCOPES = ["https://www.googleapis.com/auth/presentations"]
DEFAULT_PRESENTATION_ID = "1PAGmCAxZtO9gWk0eYAUpTICubU0EoCyOfGJuc1yi7FY"
DEFAULT_LAYOUT_ID = "p28"


def _find_client_secret(repo_root: Path) -> Optional[Path]:
    # Try explicit env var first
    env_path = os.environ.get("GOOGLE_CLIENT_SECRET_FILE")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    # Fallback: pick the first client_secret_*.json at repo root
    for p in repo_root.glob("client_secret_*.json"):
        return p
    # Some users may export from gcloud; also try credentials.json
    p = repo_root / "credentials.json"
    return p if p.exists() else None


def _get_credentials(token_path: Path, client_secret_path: Path) -> Credentials:
    creds: Optional[Credentials] = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        return creds
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    return creds


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run Slides batchUpdate to create a slide and insert text.")
    parser.add_argument("--presentation", default=DEFAULT_PRESENTATION_ID, help="Presentation ID")
    parser.add_argument("--layout", default=DEFAULT_LAYOUT_ID, help="Layout ID to use for the new slide")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    token_path = Path(__file__).resolve().with_name("token.json")
    client_secret_path = _find_client_secret(repo_root)
    if not client_secret_path or not client_secret_path.exists():
        print("Client secret JSON not found. Set GOOGLE_CLIENT_SECRET_FILE or place client_secret_*.json at repo root.")
        return 2

    creds = _get_credentials(token_path, client_secret_path)
    service = build("slides", "v1", credentials=creds)

    # Exact requests provided by the user
    requests = [
        {
            "createSlide": {
                "objectId": "slide_1",
                "slideLayoutReference": {"layoutId": args.layout},
                "placeholderIdMappings": [
                    {"layoutPlaceholder": {"type": "PICTURE"}, "objectId": "s1_picture_0"},
                    {"layoutPlaceholder": {"type": "TITLE"}, "objectId": "s1_title_0"},
                    {"layoutPlaceholder": {"type": "SUBTITLE"}, "objectId": "s1_subtitle_0"},
                    {"layoutPlaceholder": {"type": "SUBTITLE", "index": 1}, "objectId": "s1_subtitle_1"},
                ],
            }
        },
        {
            "insertText": {
                "objectId": "s1_title_0",
                "insertionIndex": 0,
                "text": "How to Build a Knowledge Graph",
            }
        },
        {
            "insertText": {
                "objectId": "s1_subtitle_0",
                "insertionIndex": 0,
                "text": "The Developer's Guide",
            }
        },
    ]

    print("Sending batchUpdate to presentation:", args.presentation)
    try:
        resp = service.presentations().batchUpdate(
            presentationId=args.presentation,
            body={"requests": requests},
        ).execute()
    except Exception as e:
        print("batchUpdate failed:", e)
        return 3

    print("batchUpdate response (truncated):")
    try:
        print(json.dumps(resp, ensure_ascii=False)[:2000])
    except Exception:
        print(str(resp)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
