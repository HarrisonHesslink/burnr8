"""Behavior and security tests for the bounded SEO crawler."""

from unittest.mock import patch

import pytest

from burnr8.seo.crawler import FetchResult, SafeWebFetcher, analyze_html, crawl_site, validate_public_url


class _FixtureFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch(self, url, *, allowed_host=None):
        self.calls.append((url, allowed_host))
        if url.endswith("/robots.txt"):
            return FetchResult(url, url, 200, "text/plain", "User-agent: *\nDisallow: /private\n")
        if url not in self.pages:
            raise ValueError("fixture missing")
        return FetchResult(url, url, 200, "text/html", self.pages[url])


def _html(
    title, links="", *, description="A useful description for a study page that provides enough context for searchers."
):
    return f"""<!doctype html><html lang="en"><head><title>{title}</title>
    <meta name="description" content="{description}"><meta name="viewport" content="width=device-width">
    <link rel="canonical" href="https://studywithlily.com/"></head>
    <body><h1>{title}</h1><p>{"study revision learning " * 25}</p>{links}<img src="hero.png" alt=""></body></html>"""


def test_private_and_mixed_dns_addresses_are_rejected():
    private = [(2, 1, 6, "", ("127.0.0.1", 80))]
    with (
        patch("burnr8.seo.transport.socket.getaddrinfo", return_value=private),
        pytest.raises(ValueError, match="non-public"),
    ):
        validate_public_url("http://example.test/")

    mixed = [
        (2, 1, 6, "", ("93.184.216.34", 443)),
        (2, 1, 6, "", ("10.0.0.1", 443)),
    ]
    with (
        patch("burnr8.seo.transport.socket.getaddrinfo", return_value=mixed),
        pytest.raises(ValueError, match="non-public"),
    ):
        validate_public_url("https://example.test/")


def test_html_analysis_returns_evidence_and_static_schema_caveat():
    html = """<html><head><title>Short</title><meta name="robots" content="noindex"></head>
    <body><h1>One</h1><h1>Two</h1><img src="x.png"><a href="/next?tracking=1#x">Next</a></body></html>"""
    page = analyze_html(FetchResult("https://studywithlily.com/", "https://studywithlily.com/", 200, "text/html", html))

    codes = {finding["code"] for finding in page.findings}
    assert {"noindex", "missing_meta_description", "multiple_h1", "no_static_json_ld"} <= codes
    assert page.internal_links == ["https://studywithlily.com/next"]
    assert page.images_missing_alt == 1


def test_bounded_crawl_respects_robots_depth_and_duplicate_titles():
    pages = {
        "https://studywithlily.com/": _html(
            "Study With Lily",
            '<a href="/lesson">Lesson</a><a href="/private">Private</a><a href="https://outside.test/">Outside</a>',
        ),
        "https://studywithlily.com/lesson": _html("Study With Lily", '<a href="/deep">Deep</a>'),
        "https://studywithlily.com/deep": _html("Deep Page"),
    }
    fetcher = _FixtureFetcher(pages)
    public_dns = [(2, 1, 6, "", ("93.184.216.34", 443))]
    with patch("burnr8.seo.transport.socket.getaddrinfo", return_value=public_dns):
        result = crawl_site(
            "https://studywithlily.com/",
            max_pages=10,
            max_depth=1,
            respect_robots=True,
            fetcher=fetcher,
        )

    assert result["summary"]["pages_processed"] == 3
    assert result["summary"]["duplicate_title_groups"] == 1
    private = next(page for page in result["pages"] if page["url"].endswith("/private"))
    assert private["blocked_by_robots"] is True
    assert not any(call[0].endswith("/deep") for call in fetcher.calls)
    assert result["schema_detection"] == "static_html_only"


def test_redirect_to_different_host_is_rejected_before_second_request():
    response = type("Response", (), {})()
    response.status_code = 302
    response.headers = {"Location": "http://127.0.0.1/admin"}
    response.close = lambda: None
    session = type("Session", (), {"trust_env": True})()
    calls = []

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    session.request = request
    fetcher = SafeWebFetcher(session=session)
    public_dns = [(2, 1, 6, "", ("93.184.216.34", 443))]
    with (
        patch("burnr8.seo.transport.socket.getaddrinfo", return_value=public_dns),
        pytest.raises(ValueError, match="allowed host"),
    ):
        fetcher.fetch("https://studywithlily.com/", allowed_host="studywithlily.com")
    assert len(calls) == 1
