"""Scout/enricher: paste a URL, get company/role/JD extracted automatically.

Deterministic and polite: one fetch of a public page the owner pasted (the
queue stays curated — this never discovers or crawls). Extraction order:
1. schema.org JobPosting JSON-LD (most ATS pages embed it — highest quality)
2. OpenGraph/title heuristics + visible body text
If a site blocks the fetch (auth walls, bot checks), we report why and the
owner pastes the JD manually. No CAPTCHA circumvention, ever.
"""
import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
MAX_BYTES = 2_000_000
MAX_JD_CHARS = 20_000

ATS_HOSTS = {
    "greenhouse.io": "greenhouse", "boards.greenhouse.io": "greenhouse",
    "lever.co": "lever", "jobs.lever.co": "lever",
    "myworkdayjobs.com": "workday", "workday.com": "workday",
    "ashbyhq.com": "ashby", "jobs.ashbyhq.com": "ashby",
    "smartrecruiters.com": "smartrecruiters", "icims.com": "icims",
    "bamboohr.com": "bamboohr", "workable.com": "workable",
    "linkedin.com": "linkedin", "indeed.com": "indeed",
}


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(html)
    except Exception:
        pass
    return re.sub(r"\n{3,}", "\n\n", "\n".join(p.parts))[:MAX_JD_CHARS]


def _meta(html: str, prop: str) -> str:
    m = re.search(
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]*'
        rf'content=["\']([^"\']*)["\']', html, re.I)
    if not m:  # content= can come before property=
        m = re.search(
            rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]*'
            rf'(?:property|name)=["\']{re.escape(prop)}["\']', html, re.I)
    return unescape(m.group(1)).strip() if m else ""


def _title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""


def _jobposting_ld(html: str) -> dict | None:
    for m in re.finditer(
            r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
            html, re.I | re.S):
        try:
            data = json.loads(m.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            continue
        candidates = data if isinstance(data, list) else \
            data.get("@graph", [data]) if isinstance(data, dict) else []
        for c in candidates:
            if isinstance(c, dict) and str(c.get("@type", "")).lower() == "jobposting":
                return c
    return None


def detect_ats(url: str) -> tuple[str, str]:
    """(ats, channel) from the host."""
    host = (urlparse(url).hostname or "").lower()
    for suffix, ats in ATS_HOSTS.items():
        if host == suffix or host.endswith("." + suffix):
            channel = "linkedin" if ats == "linkedin" else "external"
            return ats, channel
    return "", "external"


def split_title(title: str) -> tuple[str, str]:
    """'Role - Company | Site' style heuristics -> (role, company)."""
    for sep in (" - ", " – ", " | ", " at ", " @ "):
        if sep in title:
            left, right = title.split(sep, 1)
            return left.strip(), right.split("|")[0].split(" - ")[0].strip()
    return title.strip(), ""


def parse_job_page(html: str, url: str) -> dict:
    """Pure extraction (unit-testable, no network)."""
    ats, channel = detect_ats(url)
    ld = _jobposting_ld(html)
    if ld:
        org = ld.get("hiringOrganization") or {}
        company = (org.get("name", "") if isinstance(org, dict) else str(org)).strip()
        role = str(ld.get("title", "")).strip()
        jd = html_to_text(str(ld.get("description", "")))
        if role or jd:
            return {"company": company, "role": role, "jd_text": jd,
                    "ats": ats, "channel": channel, "source": "json-ld"}
    title = _meta(html, "og:title") or _title(html)
    role, company = split_title(title)
    company = company or _meta(html, "og:site_name")
    return {"company": company, "role": role, "jd_text": html_to_text(html),
            "ats": ats, "channel": channel, "source": "heuristic"}


def fetch_html(url: str) -> str:
    """One polite GET. Raises EnrichError with a plain-English reason."""
    try:
        with httpx.Client(timeout=15, follow_redirects=True,
                          headers={"User-Agent": UA}) as client:
            r = client.get(url)
    except httpx.HTTPError as e:
        raise EnrichError(f"could not fetch the page: {e}")
    if r.status_code in (401, 403, 999):
        raise EnrichError(f"the site blocked the fetch (HTTP {r.status_code}) "
                          "— paste the JD manually")
    if r.status_code >= 400:
        raise EnrichError(f"page returned HTTP {r.status_code}")
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        raise EnrichError(f"not an HTML page ({ctype or 'unknown type'})")
    return r.text[:MAX_BYTES]


class EnrichError(Exception):
    pass


def enrich_from_url(url: str) -> dict:
    return parse_job_page(fetch_html(url), url)
