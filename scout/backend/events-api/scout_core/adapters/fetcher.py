"""
Source content fetcher.

Our own code (not the agent) acquires source content. For webpage sources it
fetches the root URL; when a source has follow-links enabled it additionally
pulls same-domain links exactly one level deep, capped at the system-wide
link-follow cap. Per-link failures are recorded as outcomes, never raised, so a
run proceeds with whatever was fetched.

The HTTP call is injectable (fetch_fn) so the pipeline and tests can supply a
stub; the default uses urllib.
"""

import re
import urllib.request
from urllib.parse import urljoin, urlparse

_HREF_RE = re.compile(r'<a\b[^>]*?href=["\']([^"\']+)["\']', re.IGNORECASE)


def host_of(url):
    """Registrable host of a URL or bare domain, lowercased, without a leading
    www. or a port."""
    parsed = urlparse(url if "//" in url else f"//{url}")
    host = (parsed.netloc or parsed.path).lower().split(":")[0].strip("/")
    return host[4:] if host.startswith("www.") else host


def same_domain(url, root_domain):
    """True if url's host equals root_domain or is a subdomain of it."""
    host = host_of(url)
    root = root_domain.lower()
    root = root[4:] if root.startswith("www.") else root
    if not host or not root:
        return False
    return host == root or host.endswith("." + root)


def extract_links(html, base_url=None):
    """Absolute http(s) links from anchor tags, de-duplicated in document order.
    Relative links are resolved against base_url when provided."""
    seen = set()
    out = []
    for href in _HREF_RE.findall(html or ""):
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href) if base_url else href
        if not absolute.startswith(("http://", "https://")):
            continue
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


def fetch_url(url, timeout=10):
    """Default HTTP fetch. Returns (status_code, text)."""
    req = urllib.request.Request(url, headers={"User-Agent": "scout-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.status, resp.read().decode(charset, errors="replace")


def follow_links(html, *, base_url, root_domain, cap, fetch_fn=fetch_url):
    """Fetch eligible same-domain links one level deep, up to cap. Returns a list
    of outcome dicts: {url, ok, http_status|reason, content?}. Failures are
    captured, not raised."""
    eligible = [u for u in extract_links(html, base_url) if same_domain(u, root_domain)]
    outcomes = []
    for url in eligible[: max(0, int(cap))]:
        try:
            status, content = fetch_fn(url)
            if 200 <= int(status) < 300:
                outcomes.append({"url": url, "ok": True, "http_status": int(status),
                                 "content": content})
            else:
                outcomes.append({"url": url, "ok": False,
                                 "reason": f"http {int(status)}"})
        except Exception as exc:  # pylint: disable=broad-except
            outcomes.append({"url": url, "ok": False, "reason": str(exc)})
    return outcomes
