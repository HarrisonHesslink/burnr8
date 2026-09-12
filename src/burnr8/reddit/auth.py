"""Local OAuth setup: burnr8-reddit-setup. Never prints codes or tokens."""

from __future__ import annotations

import argparse
import getpass
import hmac
import os
import secrets
import tempfile
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import requests
from dotenv import dotenv_values, set_key, unset_key

from burnr8.reddit.client import DEFAULT_USER_AGENT, TOKEN_URL, RedditAdsApiError, decode_response

DEFAULT_REDIRECT = "http://localhost:8765/callback"


def authorization_url(client_id: str, redirect_uri: str, state: str) -> str:
    return "https://www.reddit.com/api/v1/authorize?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "duration": "permanent",
            "scope": "adsread,adsedit",
        }
    )


def callback_code(query: str, expected_state: str) -> str:
    values = parse_qs(query, keep_blank_values=True)
    states = values.get("state", [])
    if len(states) != 1 or not hmac.compare_digest(states[0].encode(), expected_state.encode()):
        raise ValueError("OAuth state did not match. Restart Reddit setup.")
    if "error" in values:
        raise ValueError("Reddit authorization was declined. No credentials were saved.")
    codes = values.get("code", [])
    if len(codes) != 1 or not codes[0]:
        raise ValueError("Reddit did not return an authorization code.")
    return codes[0]


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str, user_agent: str) -> str:
    response = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
        headers={"User-Agent": user_agent},
        timeout=30,
        allow_redirects=False,
    )
    payload = decode_response(response, "Reddit OAuth")
    refresh = payload.get("refresh_token")
    scopes = set(str(payload.get("scope", "")).replace(",", " ").split())
    if not isinstance(refresh, str) or not refresh or not {"adsread", "adsedit"}.issubset(scopes):
        raise RedditAdsApiError(
            "Reddit did not return a refresh token with adsread and adsedit. Reauthorize the application."
        )
    return refresh


def save_credentials(path: Path, values: dict[str, str]) -> None:
    """Atomically add Reddit credentials while preserving other providers/settings."""
    if path.is_symlink():
        raise ValueError("Refusing to write credentials through a symlink.")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    content = path.read_text() if path.exists() else ""
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".reddit-env-")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
        for key, value in values.items():
            set_key(temp_name, key, value)
        # A stale manually configured access token must not override the new refresh token.
        if "REDDIT_ACCESS_TOKEN" in dotenv_values(temp_name):
            unset_key(temp_name, "REDDIT_ACCESS_TOKEN")
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def receive_code(redirect_uri: str, client_id: str, state: str) -> str:
    target = urlsplit(redirect_uri)
    if (
        target.scheme != "http"
        or target.hostname not in {"localhost", "127.0.0.1"}
        or not target.port
        or target.query
        or target.fragment
        or target.username
        or target.password
    ):
        raise ValueError("Setup redirect must be an HTTP localhost/127.0.0.1 URL with an explicit port and no query.")
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            received = urlsplit(self.path)
            if received.path != target.path:
                self.send_error(404)
                return
            try:
                result["code"] = callback_code(received.query, state)
                message = "Reddit authorization received. Return to your terminal to finish setup."
                status = 200
            except ValueError as ex:
                result["error"] = str(ex)
                message, status = str(ex), 400
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(message.encode())

        def log_message(self, format: str, *args: object) -> None:
            # BaseHTTPRequestHandler would log the callback URL, including the OAuth code.
            pass

    with HTTPServer(("127.0.0.1", target.port), CallbackHandler) as server:
        server.timeout = 1
        url = authorization_url(client_id, redirect_uri, state)
        print(f"Authorize this application in your browser:\n{url}\n")
        webbrowser.open(url)
        deadline = time.monotonic() + 300
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if "error" in result:
        raise ValueError(result["error"])
    if "code" not in result:
        raise ValueError("Reddit authorization timed out. No credentials were saved.")
    return result["code"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT)
    args = parser.parse_args()
    path = Path.home() / ".burnr8" / ".env"
    existing = dotenv_values(path)
    print(
        f"Register this exact redirect URL in Reddit Ads Manager > Business > Developer Portal:\n{args.redirect_uri}\n"
    )
    try:
        client_id = existing.get("REDDIT_CLIENT_ID") or input("Reddit app ID: ").strip()
        client_secret = existing.get("REDDIT_CLIENT_SECRET") or getpass.getpass("Reddit app secret: ").strip()
        if not client_id or not client_secret:
            raise ValueError("Reddit app ID and secret are required.")
        user_agent = existing.get("REDDIT_USER_AGENT") or DEFAULT_USER_AGENT
        code = receive_code(args.redirect_uri, client_id, secrets.token_hex(24))
        refresh = exchange_code(client_id, client_secret, code, args.redirect_uri, user_agent)
        save_credentials(
            path,
            {
                "REDDIT_CLIENT_ID": client_id,
                "REDDIT_CLIENT_SECRET": client_secret,
                "REDDIT_REFRESH_TOKEN": refresh,
                "REDDIT_USER_AGENT": user_agent,
            },
        )
    except (ValueError, OSError, RedditAdsApiError) as ex:
        # requests failures can embed the request URL; never print those exceptions.
        message = (
            "Could not reach Reddit OAuth. Check your connection."
            if isinstance(ex, requests.RequestException)
            else str(ex)
        )
        parser.exit(1, f"Reddit setup failed: {message}\n")
    except (KeyboardInterrupt, EOFError):
        parser.exit(1, "Reddit setup cancelled. No credentials were saved.\n")
    print(f"Saved Reddit credentials to {path} (permissions 0600). Restart the MCP server.")
    print("Call reddit_list_businesses, then reddit_list_ad_accounts. Set REDDIT_AD_ACCOUNT_ID to the chosen account.")


if __name__ == "__main__":
    main()
