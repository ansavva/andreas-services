#!/usr/bin/env python3
"""
One-time script to obtain a Gmail OAuth refresh token.

Usage:
  1. Download OAuth credentials from Google Cloud Console:
       APIs & Services → Credentials → [your Desktop app client] → download JSON
       Save as credentials.json in this directory (it is gitignored).

  2. Install dependency:
       pip install google-auth-oauthlib

  3. Run:
       python3 get_gmail_tokens.py

     A browser window will open for Google sign-in.
     After authorizing, the refresh token is printed to stdout.

  4. Copy GMAIL_REFRESH_TOKEN into GitHub secrets (and your local .env if used).
     The Lambda mints fresh access tokens from this on each cold start —
     no GMAIL_ACCESS_TOKEN secret is needed.

Note: The refresh token is long-lived. Re-run only if it is revoked
(e.g. you removed app access in Google Account settings, the OAuth
client was reset, or the OAuth consent screen was set back to Testing
— Testing-mode refresh tokens expire after 7 days).
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
creds = flow.run_local_server(port=0)

print()
print("GMAIL_REFRESH_TOKEN=", creds.refresh_token)
