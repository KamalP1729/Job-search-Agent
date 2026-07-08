"""
gmail_oauth.py — Send email via Gmail OAuth2 token.
"""

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
import os
from email.mime.text import MIMEText


def send_via_oauth(token_info: dict, draft: dict) -> None:
    """
    Send an email draft using a Gmail OAuth2 token.

    Args:
        token_info: dict with token, refresh_token, etc.
        draft: dict with to_email, subject, body fields.
    """
    creds = Credentials(
        token=token_info["token"],
        refresh_token=token_info.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
    )

    service = build("gmail", "v1", credentials=creds)

    msg = MIMEText(draft["body"])
    msg["To"] = draft["to_email"]
    msg["From"] = "me"
    msg["Subject"] = draft["subject"]

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
