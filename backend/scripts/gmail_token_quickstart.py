"""Utility to replicate the Gmail API Python quickstart OAuth flow.

This script mirrors the flow from
https://developers.google.com/workspace/gmail/api/quickstart/python but
accepts the OAuth client credentials as command-line arguments so the
resulting token payload can be merged directly into the AWS Secrets Manager
entry consumed by the ingestion container.

Example:
    python3 backend/scripts/gmail_token_quickstart.py \
        --client-id YOUR_CLIENT_ID \
        --client-secret YOUR_CLIENT_SECRET \
        --scopes https://www.googleapis.com/auth/gmail.readonly \
        --output gmail-credentials.json

The script opens a browser window, asks you to authorize the Gmail account,
and saves the resulting refresh/access tokens in JSON format.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

from google_auth_oauthlib.flow import InstalledAppFlow


DEFAULT_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/gmail.readonly",
)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Gmail OAuth quickstart flow and emit token JSON.")
    parser.add_argument("--client-id", required=True, help="OAuth client_id from Google Cloud Console")
    parser.add_argument("--client-secret", required=True, help="OAuth client_secret from Google Cloud Console")
    parser.add_argument(
        "--scopes",
        nargs="*",
        default=list(DEFAULT_SCOPES),
        help="OAuth scopes to request (defaults to gmail.readonly)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("gmail-credentials.json"),
        help="Path to write the merged credential JSON",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Use the console-based authorization flow instead of launching a local server",
    )
    return parser.parse_args(argv)


def ensure_scopes(scopes: Iterable[str]) -> list[str]:
    normalized = []
    for scope in scopes:
        scope = scope.strip()
        if not scope:
            continue
        normalized.append(scope)
    if not normalized:
        raise SystemExit("At least one OAuth scope must be provided.")
    return normalized


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    scopes = ensure_scopes(args.scopes)

    client_config = {
        "installed": {
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)

    if args.no_browser:
        credentials = flow.run_console()
    else:
        credentials = flow.run_local_server(port=0, prompt="consent", authorization_prompt_message="")

    output_payload = {
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "refresh_token": credentials.refresh_token,
        "token": credentials.token,
        "token_uri": credentials.token_uri,
        "scopes": list(credentials.scopes or scopes),
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        "id_token": credentials.id_token,
        "type": "authorized_user",
    }

    args.output.write_text(json.dumps(output_payload, indent=2))

    print(f"Saved Gmail credentials to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
