# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in burnr8, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, email the maintainer directly (see GitHub profile for contact info).

## Credential Safety

burnr8 is designed to keep your Google Ads credentials safe:

- Credentials are loaded from environment variables (`.env` file)
- `.env` is in `.gitignore` — never committed to the repo
- No credentials are logged or included in error responses
- The OAuth setup script only prints the refresh token to stdout

## Scope

This policy applies to the burnr8 codebase. It does not cover:
- The Google Ads API itself
- Third-party dependencies
- Your Google Cloud Platform account security
