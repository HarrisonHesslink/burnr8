#!/usr/bin/env python3
"""One-time OAuth2 refresh token generator for Google Ads API."""

import hashlib
import os
import re
import socket
from urllib.parse import unquote, parse_qs, urlparse

from google_auth_oauthlib.flow import Flow

SCOPE = "https://www.googleapis.com/auth/adwords"
SERVER = "127.0.0.1"
PORT = 8080
REDIRECT_URI = f"http://{SERVER}:{PORT}"


def main():
    client_id = input("Enter your OAuth2 client ID: ").strip()
    client_secret = input("Enter your OAuth2 client secret: ").strip()

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }

    flow = Flow.from_client_config(client_config, scopes=[SCOPE])
    flow.redirect_uri = REDIRECT_URI

    passthrough_val = hashlib.sha256(os.urandom(1024)).hexdigest()
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        state=passthrough_val,
        prompt="consent",
        include_granted_scopes="true",
    )

    print(f"\nOpen this URL in your browser:\n\n{authorization_url}\n")
    print(f"Waiting for callback on {REDIRECT_URI} ...")

    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((SERVER, PORT))
    sock.listen(1)
    connection, _ = sock.accept()
    data = connection.recv(4096).decode("utf-8")

    # Parse the request line to extract the query string
    match = re.search(r"GET\s(/[^\s]*)\s", data)
    if not match:
        print("Error: Could not parse callback request")
        connection.close()
        sock.close()
        return

    request_path = match.group(1)
    parsed = urlparse(request_path)
    params = parse_qs(parsed.query)

    # Verify CSRF state
    returned_state = params.get("state", [None])[0]
    if returned_state != passthrough_val:
        print("Error: State parameter mismatch — possible CSRF attack. Aborting.")
        connection.close()
        sock.close()
        return

    code = params.get("code", [None])[0]
    if not code:
        print("Error: No authorization code in callback")
        connection.close()
        sock.close()
        return

    response = "HTTP/1.1 200 OK\r\n\r\n<b>Authorization successful!</b> You can close this tab."
    connection.sendall(response.encode())
    connection.close()
    sock.close()

    flow.fetch_token(code=code)
    refresh_token = flow.credentials.refresh_token

    print(f"\nYour refresh token:\n\n{refresh_token}\n")
    print("Add this to your .env file as GOOGLE_ADS_REFRESH_TOKEN")


if __name__ == "__main__":
    main()
