"""
Source content fetcher.

Our own code (not the agent) acquires source content. For webpage sources it
fetches the root URL; when a source has follow-links enabled it additionally
pulls links one level deep, capped at the system-wide link-follow cap. Webpage
sources stay same-domain; email sources follow the (cross-domain) organizer /
ticketing links found in the mail. Junk links (unsubscribe, tracking,
social, file downloads) are filtered out and per-link failures are recorded as
outcomes, never raised, so a run proceeds with whatever was fetched.

Fetched HTML is stripped of boilerplate chrome (scripts, nav, footer, cookie
banners, …) and converted to clean text before it reaches the model — this is
both higher-signal and far cheaper against the prompt's content cap. The HTTP
call is injectable (fetch_fn) so the pipeline and tests can supply a stub; the
default uses urllib.
"""

import re
import urllib.request
from urllib.parse import urljoin, urlparse

_HREF_RE = re.compile(r'<a\b[^>]*?href=["\']([^"\']+)["\']', re.IGNORECASE)

# Substrings that mark a link as not-an-event: list management, click trackers,
# social, and direct file downloads. Matched case-insensitively against the URL.
_JUNK_LINK_SIGNALS = (
    "unsubscribe", "optout", "opt-out", "/preferences", "list-manage",
    "mailchi.mp", "/click", "/track", "utm_unsubscribe", "email-settings",
    "manage-subscription", "/wf/open", "/o/", "sendgrid.net", "/c/",
    "facebook.com", "instagram.com", "twitter.com", "x.com", "youtube.com",
    "linkedin.com", "tiktok.com", "t.me", "whatsapp.com",
)
_JUNK_LINK_SUFFIXES = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".zip", ".ics",
    ".doc", ".docx", ".xls", ".xlsx", ".mp3", ".mp4", ".dmg", ".exe",
)

# Tags whose content is never useful to an event extractor.
_DROP_TAGS = ("script", "style", "noscript", "svg", "head", "iframe",
              "template", "form", "nav", "header", "footer", "aside")

# Boilerplate signals matched (case-insensitive substring) against an element's
# id / class / role. Conservative: we drop definite chrome but keep the main
# content and sidebars (event pages often put date/venue/price in a sidebar).
_BOILERPLATE_SIGNALS = (
    "cookie", "consent", "gdpr", "banner", "subscribe", "newsletter",
    "signup", "sign-up", "social", "share", "breadcrumb", "skip-link",
    "advert", "ad-", "-ad", "popup", "modal", "menu", "navbar", "navigation",
)


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


def is_junk_link(url):
    """True for links that are never an event detail page: unsubscribe/list
    management, click/open trackers, social profiles, and file downloads."""
    low = (url or "").lower()
    if any(signal in low for signal in _JUNK_LINK_SIGNALS):
        return True
    path = urlparse(low).path
    return path.endswith(_JUNK_LINK_SUFFIXES)


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


def clean_html(html):
    """Strip boilerplate chrome from HTML and return clean text (markdown).

    Removes scripts/styles, structural chrome (nav/header/footer/aside/form),
    and elements whose id/class/role match common boilerplate signals, then
    converts what's left to text. Conservative on purpose: main content and
    sidebars are preserved. Falls back to a plain text conversion if parsing
    fails for any reason."""
    html = html or ""
    try:
        from bs4 import BeautifulSoup, Comment  # noqa: PLC0415
    except Exception:  # pragma: no cover - bs4 always present in the image
        return html_to_text(html)

    try:
        soup = BeautifulSoup(html, "html.parser")
        for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
            comment.extract()
        for tag in soup.find_all(_DROP_TAGS):
            tag.decompose()
        for tag in soup.find_all(True):
            tokens = " ".join([
                tag.get("id", "") or "",
                " ".join(tag.get("class", []) or []),
                tag.get("role", "") or "",
            ]).lower()
            if tokens and any(sig in tokens for sig in _BOILERPLATE_SIGNALS):
                tag.decompose()
        return html_to_text(str(soup))
    except Exception:  # pragma: no cover - defensive
        return html_to_text(html)


def html_to_text(html):
    """Convert HTML to markdown-ish text, keeping links and images (they carry
    event detail URLs and posters). Lazily imports html2text."""
    import html2text  # noqa: PLC0415
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = False
    converter.body_width = 0
    return converter.handle(html or "").strip()


def fetch_url(url, timeout=10):
    """Default HTTP fetch. Returns (status_code, text)."""
    req = urllib.request.Request(url, headers={"User-Agent": "scout-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.status, resp.read().decode(charset, errors="replace")


def fetch_text(url, *, fetch_fn=fetch_url):
    """Fetch a URL and return cleaned text. Returns (status_code, text); the
    text is empty for non-2xx responses."""
    status, html = fetch_fn(url)
    text = clean_html(html) if 200 <= int(status) < 300 else ""
    return int(status), text


def follow_links(html, *, base_url, root_domain, cap, fetch_fn=fetch_url,
                 same_domain_only=True, candidate_urls=None):
    """Fetch eligible links one level deep, up to cap, returning their cleaned
    text. Returns a list of outcome dicts: {url, ok, http_status|reason,
    content?}. Failures are captured, not raised.

    Links come from `candidate_urls` when provided (e.g. links lifted from an
    email body) otherwise from anchors in `html`. Junk links are always
    dropped; when `same_domain_only` is set, off-domain links are dropped too
    (the webpage-source default)."""
    found = candidate_urls if candidate_urls is not None else extract_links(html, base_url)
    eligible = []
    for url in found:
        if is_junk_link(url):
            continue
        if same_domain_only and not same_domain(url, root_domain):
            continue
        if url not in eligible:
            eligible.append(url)

    outcomes = []
    for url in eligible[: max(0, int(cap))]:
        try:
            status, text = fetch_text(url, fetch_fn=fetch_fn)
            if 200 <= status < 300:
                outcomes.append({"url": url, "ok": True, "http_status": status,
                                 "content": text})
            else:
                outcomes.append({"url": url, "ok": False,
                                 "reason": f"http {status}"})
        except Exception as exc:  # pylint: disable=broad-except
            outcomes.append({"url": url, "ok": False, "reason": str(exc)})
    return outcomes
