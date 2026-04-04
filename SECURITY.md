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
- Customer IDs are truncated to 6 digits in logs
- CSV report files are written with `0o600` permissions (owner-only)

**Note:** On Windows, CSV report files in `~/.burnr8/reports/` are created with default permissions (Unix `0o600` file modes are not enforced on Windows). This only affects report data (performance metrics, search terms), not credentials.

## Supply Chain Security

- **Dependency scanning**: `pip-audit` runs on every CI push and weekly via scheduled workflow
- **Dependabot**: Automated PRs for dependency updates (Python + GitHub Actions)
- **Dependency bounds**: All direct deps have upper version bounds to prevent unexpected breaking changes
- **Lock file**: `requirements.lock` pins exact versions for reproducible installs
- **Typosquatting check**: CI verifies direct dependencies are from expected publishers
- **Minimal permissions**: GitHub Actions workflows use `permissions: contents: read`

## Dependency Audit

Run a local security audit:

```bash
pip install pip-audit
pip-audit
```

## Scope

This policy applies to the burnr8 codebase. It does not cover:
- The Google Ads API itself
- Third-party dependencies (report upstream)
- Your Google Cloud Platform account security
