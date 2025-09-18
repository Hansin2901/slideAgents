from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Sequence

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/presentations"]
_DEFAULT_CLIENT_SECRET_NAME = "client_secret.json"
_DEFAULT_TOKEN_NAME = "token.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_token_path() -> Path:
    env_path = os.environ.get("GOOGLE_SLIDES_TOKEN_FILE")
    if env_path:
        return Path(env_path)
    return _repo_root() / _DEFAULT_TOKEN_NAME


def _find_client_secret() -> Optional[Path]:
    env_path = os.environ.get("GOOGLE_CLIENT_SECRET_FILE")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    for pattern in ("client_secret_*.json", _DEFAULT_CLIENT_SECRET_NAME, "credentials.json"):
        for candidate in _repo_root().glob(pattern):
            if candidate.exists():
                return candidate
    return None


def _refresh_if_needed(creds: Credentials, token_path: Path | None = None) -> Credentials:
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        if token_path:
            token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _load_credentials(token_path: Path, client_secret_path: Path) -> Credentials:
    creds: Optional[Credentials] = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        return _refresh_if_needed(creds, token_path)
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    refreshed = flow.run_local_server(port=0)
    token_path.write_text(refreshed.to_json(), encoding="utf-8")
    return refreshed


def build_slides_service(
    *,
    token_path: Path | None = None,
    client_secret_path: Path | None = None,
    credentials_dict: Optional[dict] = None,
    credentials_obj: Optional[Credentials] = None,
) -> object:
    load_dotenv()
    creds: Optional[Credentials] = None
    if credentials_obj:
        creds = credentials_obj
    elif credentials_dict:
        creds = Credentials(**credentials_dict)
    else:
        token = token_path or _default_token_path()
        client_secret = client_secret_path or _find_client_secret()
        if not client_secret or not client_secret.exists():
            raise FileNotFoundError(
                "Google OAuth client secret not found. Set GOOGLE_CLIENT_SECRET_FILE or place client_secret_*.json at repo root."
            )
        creds = _load_credentials(token, client_secret)
        token_path = token
        creds = _refresh_if_needed(creds, token_path)
    if not creds:
        raise RuntimeError("Unable to obtain Google Slides credentials")
    creds = _refresh_if_needed(creds, token_path)
    return build("slides", "v1", credentials=creds)


def send_batch_requests(
    presentation_id: str,
    requests: Sequence[dict],
    *,
    token_path: Path | None = None,
    client_secret_path: Path | None = None,
    credentials_dict: Optional[dict] = None,
    credentials_obj: Optional[Credentials] = None,
) -> dict:
    if not presentation_id:
        raise ValueError("presentation_id is required")
    if not requests:
        raise ValueError("requests must be a non-empty sequence")
    service = build_slides_service(
        token_path=token_path,
        client_secret_path=client_secret_path,
        credentials_dict=credentials_dict,
        credentials_obj=credentials_obj,
    )
    body = {"requests": list(requests)}
    response = service.presentations().batchUpdate(presentationId=presentation_id, body=body).execute()
    return json.loads(json.dumps(response))
