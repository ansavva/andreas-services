#!/usr/bin/env python3
"""
One-time script to obtain Gmail OAuth access + refresh tokens.

Usage:
  1. Download OAuth credentials from Google Cloud Console:
       APIs & Services → Credentials → [your Desktop app client] → download JSON
       Save as credentials.json in this directory (it is gitignored).

  2. Install dependency:
       pip install google-auth-oauthlib

  3. Run:
       python3 get_gmail_tokens.py

     A browser window will open for Google sign-in.
     After authorizing, tokens are printed to stdout.

  4. Copy the tokens into your .env (local) or GitHub secrets (production):
       GMAIL_ACCESS_TOKEN=...
       GMAIL_REFRESH_TOKEN=...

Note: The refresh token is long-lived. The Lambda auto-refreshes the access
token using it, so you normally only need to run this once. Re-run if the
refresh token is ever revoked (e.g. after removing app access in Google
Account settings).
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
creds = flow.run_local_server(port=0)

print()
print("GMAIL_ACCESS_TOKEN =", creds.token)
print("GMAIL_REFRESH_TOKEN=", creds.refresh_token)
