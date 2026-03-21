#!/usr/bin/env python3
"""
Run ONCE to authorize Gmail access. Opens your browser for Google consent.

Usage:
    python setup_oauth.py

Prerequisites:
    1. Go to https://console.cloud.google.com
    2. Create a new project (e.g. "Flowmingo Gmail Assistant")
    3. APIs & Services → Library → search "Gmail API" → Enable
    4. APIs & Services → OAuth consent screen → External
       - App name: Flowmingo Assistant
       - Support email: your email
       - Add your Gmail address as a Test user
    5. APIs & Services → Credentials → Create Credentials → OAuth client ID
       - Application type: Desktop app
       - Download JSON → rename to credentials.json
       - Place at: credentials/credentials.json
    6. Run this script
"""

import json
import sys
import webbrowser
from pathlib import Path

CREDENTIALS_PATH = Path(__file__).parent.parent.parent / "credentials" / "credentials.json"
TOKEN_PATH = Path(__file__).parent.parent.parent / "credentials" / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/spreadsheets",
]


def main():
    # Check credentials.json exists
    if not CREDENTIALS_PATH.exists():
        print("ERROR: credentials.json not found.")
        print(f"Expected location: {CREDENTIALS_PATH}")
        print()
        print("Steps to get it:")
        print("  1. Go to https://console.cloud.google.com")
        print("  2. Create a project, enable Gmail API")
        print("  3. APIs & Services → Credentials → Create OAuth client ID (Desktop app)")
        print("  4. Download JSON, rename to credentials.json")
        print(f"  5. Place it at: {CREDENTIALS_PATH}")
        sys.exit(1)

    # Check if already authorized
    if TOKEN_PATH.exists():
        answer = input("token.json already exists. Re-authorize? [y/N]: ").strip().lower()
        if answer != "y":
            print("Keeping existing token. Setup complete.")
            sys.exit(0)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: google-auth-oauthlib not installed.")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)

    print()
    print("Opening browser for Google authorization...")
    print("If the browser doesn't open, check your default browser settings.")
    print()
    print("NOTE: You may see 'Google hasn't verified this app'.")
    print("      Click 'Advanced' → 'Go to Flowmingo Assistant (unsafe)' to continue.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(
        port=8080,
        access_type="offline",
        prompt="consent",
    )

    # Save token
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    print()
    print(f"OAuth complete. Token saved to: {TOKEN_PATH}")
    print()
    print("You can now open Claude Code in this directory and use the Gmail tools.")
    print("Try asking: 'List my unread emails'")


if __name__ == "__main__":
    main()
