"""Bounded, domain-safe static HTML crawler for technical and on-page SEO checks."""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests

from burnr8.seo.transport import PublicAddressAdapter, public_addresses

_USER_AGENT = "burnr8-seo-audit/0.7 (+https://github.com/HarrisonHesslink/burnr8)"
_HTML_TYPES = {"text/html", "application/xhtml+xml"}
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_REDIRECTS = 5
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: str
    redirects: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PageSignals:
    url: str
    final_url: str
    status_code: int
    content_type: str
    title: str | None
    meta_description: str | None
    meta_robots: str | None
    canonical: str | None
    language: str | None
    viewport: str | None
    h1: list[str]
    h2_count: int
    h3_count: int
    word_count: int
    internal_links: list[str]
    external_links_count: int
    images_count: int
    images_missing_alt: int
    static_json_ld_blocks: int
    crawl_depth: int = 0
    blocked_by_robots: bool = False
    findings: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class SafeWebFetcher:
    """Fetch public HTTP(S) pages with bounded redirects and response sizes."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_bytes: int = _MAX_RESPONSE_BYTES,
        max_redirects: int = _MAX_REDIRECTS,
        session: requests.Session | None = None,
    ) -> None:
        if timeout <= 0 or max_bytes <= 0 or max_redirects < 0:
            raise ValueError("Crawler limits must be positive.")
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.session = session or requests.Session()
        self.session.trust_env = False
        if session is None:
            self.session.mount("http://", PublicAddressAdapter())
            self.session.mount("https://", PublicAddressAdapter())

    def fetch(self, url: str, *, allowed_host: str | None = None) -> FetchResult:
        current = normalize_crawl_url(url, keep_query=True)
        redirects: list[str] = []
        for _ in range(self.max_redirects + 1):
            parsed = validate_public_url(current)
            if allowed_host and parsed.hostname != allowed_host:
                raise ValueError(f"Crawler redirect left the allowed host: {parsed.hostname}.")
            response = self.session.request(
                "GET",
                current,
                headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"},
                timeout=self.timeout,
                allow_redirects=False,
                stream=True,
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise ValueError("Redirect response did not include a Location header.")
                if len(redirects) >= self.max_redirects:
                    raise ValueError(f"Crawler exceeded {self.max_redirects} redirects.")
                current = normalize_crawl_url(urljoin(current, location), keep_query=True)
                redirects.append(current)
                continue

            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            body_bytes = bytearray()
            raw_length = response.headers.get("Content-Length")
            try:
                content_length = int(raw_length) if raw_length is not None else None
            except ValueError:
                content_length = None
            if content_length is not None and content_length > self.max_bytes:
                response.close()
                raise ValueError(f"Response exceeded the crawler limit of {self.max_bytes} bytes.")
            try:
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    body_bytes.extend(chunk)
                    if len(body_bytes) > self.max_bytes:
                        raise ValueError(f"Response exceeded the crawler limit of {self.max_bytes} bytes.")
                encoding = response.encoding or "utf-8"
                body = bytes(body_bytes).decode(encoding, errors="replace")
                status_code = response.status_code
            finally:
                response.close()
            return FetchResult(url, current, status_code, content_type, body, redirects)
        raise ValueError(f"Crawler exceeded {self.max_redirects} redirects.")


class _SeoHtmlParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.description: str | None = None
        self.robots: str | None = None
        self.canonical: str | None = None
        self.language: str | None = None
        self.viewport: str | None = None
        self.headings: dict[str, list[str]] = {"h1": [], "h2": [], "h3": []}
        self.links: list[str] = []
        self.images_count = 0
        self.images_missing_alt = 0
        self.static_json_ld_blocks = 0
        self.text_parts: list[str] = []
        self._capture: str | None = None
        self._capture_parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "html":
            self.language = values.get("lang") or None
        elif tag == "meta":
            name = values.get("name", "").lower()
            if name == "description" and self.description is None:
                self.description = _clean_text(values.get("content", "")) or None
            elif name in {"robots", "googlebot"} and self.robots is None:
                self.robots = _clean_text(values.get("content", "")) or None
            elif name == "viewport" and self.viewport is None:
                self.viewport = _clean_text(values.get("content", "")) or None
        elif tag == "link" and "canonical" in values.get("rel", "").lower().split():
            href = values.get("href")
            if href and self.canonical is None:
                self.canonical = urljoin(self.base_url, href)
        elif tag == "a":
            href = values.get("href")
            if href:
                self.links.append(href)
        elif tag == "img":
            self.images_count += 1
            if "alt" not in values or not values["alt"].strip():
                self.images_missing_alt += 1
        elif tag == "script":
            self._ignored_depth += 1
            if values.get("type", "").lower().split(";", 1)[0].strip() == "application/ld+json":
                self.static_json_ld_blocks += 1
        elif tag in {"style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag in {"title", "h1", "h2", "h3"}:
            self._capture = tag
            self._capture_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._capture == tag:
            text = _clean_text(" ".join(self._capture_parts))
            if text:
                if tag == "title":
                    self.title_parts.append(text)
                else:
                    self.headings[tag].append(text)
            self._capture = None
            self._capture_parts = []
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._capture_parts.append(data)
        if self._ignored_depth == 0 and self._capture != "title":
            cleaned = _clean_text(data)
            if cleaned:
                self.text_parts.append(cleaned)


def validate_public_url(url: str) -> SplitResult:
    """Validate URL syntax and reject any hostname resolving to non-public IP space."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Crawler URL must be an absolute HTTP(S) URL.")
    if parsed.username or parsed.password:
        raise ValueError("Crawler URLs cannot contain embedded credentials.")
    if parsed.hostname.lower() == "localhost":
        raise ValueError("Crawler only permits public internet hosts.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        raise ValueError("Crawler URL contains an invalid port.") from None
    public_addresses(parsed.hostname, port)
    return parsed


def normalize_crawl_url(url: str, *, keep_query: bool = False) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Crawler URL must be an absolute HTTP(S) URL.")
    host = parsed.hostname.lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Crawler URL contains an invalid port.") from None
    default_port = 443 if parsed.scheme == "https" else 80
    host_for_url = f"[{host}]" if ":" in host else host
    netloc = host_for_url if port in {None, default_port} else f"{host_for_url}:{port}"
    path = parsed.path or "/"
    query = parsed.query if keep_query else ""
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, ""))


def analyze_html(result: FetchResult, *, crawl_depth: int = 0, root_host: str | None = None) -> PageSignals:
    parser = _SeoHtmlParser(result.final_url)
    if result.content_type in _HTML_TYPES or not result.content_type:
        parser.feed(result.body)
    host = root_host or urlsplit(result.final_url).hostname or ""
    internal: list[str] = []
    external_count = 0
    for raw_link in parser.links:
        candidate = urljoin(result.final_url, raw_link)
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        if parsed.hostname.lower() == host.lower():
            internal.append(normalize_crawl_url(candidate))
        else:
            external_count += 1
    page = PageSignals(
        url=result.requested_url,
        final_url=result.final_url,
        status_code=result.status_code,
        content_type=result.content_type,
        title=_clean_text(" ".join(parser.title_parts)) or None,
        meta_description=parser.description,
        meta_robots=parser.robots,
        canonical=parser.canonical,
        language=parser.language,
        viewport=parser.viewport,
        h1=parser.headings["h1"],
        h2_count=len(parser.headings["h2"]),
        h3_count=len(parser.headings["h3"]),
        word_count=len(" ".join(parser.text_parts).split()),
        internal_links=list(dict.fromkeys(internal)),
        external_links_count=external_count,
        images_count=parser.images_count,
        images_missing_alt=parser.images_missing_alt,
        static_json_ld_blocks=parser.static_json_ld_blocks,
        crawl_depth=crawl_depth,
    )
    page.findings = page_findings(page)
    return page


def page_findings(page: PageSignals) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def add(severity: str, code: str, evidence: str, fix: str) -> None:
        findings.append({"severity": severity, "code": code, "evidence": evidence, "fix": fix})

    if page.status_code >= 400:
        add(
            "high",
            "http_error",
            f"HTTP {page.status_code}",
            "Restore the page or redirect it to the closest relevant live URL.",
        )
    elif page.status_code >= 300:
        add(
            "medium",
            "redirect",
            f"HTTP {page.status_code}",
            "Update internal links to point directly to the final URL.",
        )
    if page.content_type and page.content_type not in _HTML_TYPES:
        add("medium", "non_html", page.content_type, "Audit an HTML document for on-page SEO signals.")
        return findings
    if not page.title:
        add("high", "missing_title", "No static <title> was found.", "Add one descriptive, unique page title.")
    elif len(page.title) < 15 or len(page.title) > 65:
        add(
            "low",
            "title_length",
            f"Title length is {len(page.title)} characters.",
            "Use a concise title that communicates the page topic.",
        )
    if not page.meta_description:
        add(
            "medium",
            "missing_meta_description",
            "No static meta description was found.",
            "Add a unique description aligned with search intent.",
        )
    elif len(page.meta_description) < 50 or len(page.meta_description) > 165:
        add(
            "low",
            "meta_description_length",
            f"Description length is {len(page.meta_description)} characters.",
            "Write a concise, useful search snippet description.",
        )
    if not page.h1:
        add("medium", "missing_h1", "No static H1 was found.", "Add one clear primary heading.")
    elif len(page.h1) > 1:
        add(
            "low",
            "multiple_h1",
            f"Found {len(page.h1)} H1 elements.",
            "Keep heading structure unambiguous and intentional.",
        )
    if not page.canonical:
        add(
            "medium",
            "missing_canonical",
            "No static canonical link was found.",
            "Add a self-referencing canonical to indexable pages.",
        )
    if page.meta_robots and "noindex" in page.meta_robots.lower():
        add(
            "high",
            "noindex",
            page.meta_robots,
            "Confirm this page should be excluded; remove noindex if it should rank.",
        )
    if not page.viewport:
        add("medium", "missing_viewport", "No viewport meta tag was found.", "Add a responsive viewport declaration.")
    if page.images_missing_alt:
        add(
            "low",
            "missing_image_alt",
            f"{page.images_missing_alt} image(s) have missing or empty alt text.",
            "Add meaningful alt text to informative images; leave decorative images empty intentionally.",
        )
    if page.static_json_ld_blocks == 0:
        add(
            "info",
            "no_static_json_ld",
            "No JSON-LD was found in fetched HTML.",
            "Static HTML checks cannot detect client-rendered schema; validate rendered output or Search Console rich results before concluding schema is absent.",
        )
    return findings


def audit_url(url: str, *, fetcher: SafeWebFetcher | None = None) -> PageSignals:
    normalized = normalize_crawl_url(url, keep_query=True)
    root_host = urlsplit(normalized).hostname or ""
    result = (fetcher or SafeWebFetcher()).fetch(normalized, allowed_host=root_host)
    return analyze_html(result, root_host=root_host)


def crawl_site(
    start_url: str,
    *,
    max_pages: int = 25,
    max_depth: int = 3,
    respect_robots: bool = True,
    fetcher: SafeWebFetcher | None = None,
) -> dict[str, object]:
    hard_max = max(1, int(os.environ.get("BURNR8_SEO_MAX_CRAWL_PAGES", "100")))
    if not 1 <= max_pages <= hard_max:
        raise ValueError(f"max_pages must be between 1 and {hard_max}.")
    if not 0 <= max_depth <= 10:
        raise ValueError("max_depth must be between 0 and 10.")
    start = normalize_crawl_url(start_url)
    parsed_start = validate_public_url(start)
    host = parsed_start.hostname or ""
    web = fetcher or SafeWebFetcher()
    robots = _load_robots(web, start, host) if respect_robots else None
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    queued = {start}
    pages: list[PageSignals] = []
    fetch_errors: list[dict[str, object]] = []

    while queue and len(pages) + len(fetch_errors) < max_pages:
        url, depth = queue.popleft()
        if robots and not robots.can_fetch(_USER_AGENT, url):
            pages.append(
                PageSignals(
                    url=url,
                    final_url=url,
                    status_code=0,
                    content_type="",
                    title=None,
                    meta_description=None,
                    meta_robots=None,
                    canonical=None,
                    language=None,
                    viewport=None,
                    h1=[],
                    h2_count=0,
                    h3_count=0,
                    word_count=0,
                    internal_links=[],
                    external_links_count=0,
                    images_count=0,
                    images_missing_alt=0,
                    static_json_ld_blocks=0,
                    crawl_depth=depth,
                    blocked_by_robots=True,
                    findings=[
                        {
                            "severity": "info",
                            "code": "blocked_by_robots",
                            "evidence": "robots.txt disallows this URL for the Burnr8 crawler.",
                            "fix": "No change is needed if the block is intentional.",
                        }
                    ],
                )
            )
            continue
        try:
            result = web.fetch(url, allowed_host=host)
            page = analyze_html(result, crawl_depth=depth, root_host=host)
            pages.append(page)
        except (requests.RequestException, ValueError) as ex:
            fetch_errors.append({"url": url, "depth": depth, "error": str(ex)[:300]})
            continue
        if depth >= max_depth:
            continue
        for link in page.internal_links:
            if link not in queued and urlsplit(link).hostname == host:
                queued.add(link)
                queue.append((link, depth + 1))

    duplicate_titles = _duplicates(pages, "title")
    duplicate_descriptions = _duplicates(pages, "meta_description")
    issue_counts = Counter(finding["code"] for page in pages for finding in page.findings)
    severity_counts = Counter(finding["severity"] for page in pages for finding in page.findings)
    return {
        "start_url": start,
        "scope": {"host": host, "max_pages": max_pages, "max_depth": max_depth, "respect_robots": respect_robots},
        "summary": {
            "pages_processed": len(pages),
            "fetch_errors": len(fetch_errors),
            "queued_but_not_processed": len(queue),
            "issue_counts": dict(issue_counts),
            "severity_counts": dict(severity_counts),
            "duplicate_title_groups": len(duplicate_titles),
            "duplicate_description_groups": len(duplicate_descriptions),
        },
        "duplicates": {"titles": duplicate_titles, "meta_descriptions": duplicate_descriptions},
        "fetch_errors": fetch_errors,
        "pages": [page.as_dict() for page in pages],
        "schema_detection": "static_html_only",
        "schema_note": "Zero JSON-LD blocks does not prove schema is absent because client-rendered markup is not executed.",
    }


def _load_robots(fetcher: SafeWebFetcher, start_url: str, host: str) -> RobotFileParser | None:
    parsed = urlsplit(start_url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    try:
        result = fetcher.fetch(robots_url, allowed_host=host)
    except (requests.RequestException, ValueError):
        return None
    if result.status_code >= 400:
        return None
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(result.body.splitlines())
    return parser


def _duplicates(pages: list[PageSignals], attribute: str) -> list[dict[str, object]]:
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for page in pages:
        value = getattr(page, attribute)
        if isinstance(value, str) and value:
            grouped[value.casefold()].append(page.final_url)
    return [{"value": key, "urls": urls, "count": len(urls)} for key, urls in grouped.items() if len(urls) > 1]


def _clean_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()
