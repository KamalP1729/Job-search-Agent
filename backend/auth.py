"""
auth.py — Gmail OAuth helpers for the Job Agent backend.
"""

import os
from google_auth_oauthlib.flow import Flow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
REDIRECT_URI = "http://localhost:8000/api/auth/gmail/callback"


def get_gmail_auth_url(session_id: str) -> str:
    """
    Build the Google OAuth authorization URL.
    Requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET env vars.
    """
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    if not client_id:
        raise ValueError("GOOGLE_CLIENT_ID not set")

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=session_id,
        prompt="consent",
    )

    return auth_url


def exchange_gmail_code(code: str, state: str) -> dict:
    """
    Exchange the OAuth authorization code for credentials.
    Returns a dict with token, refresh_token, etc.
    """
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        state=state,
    )

    flow.fetch_token(code=code)
    creds = flow.credentials

    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }
