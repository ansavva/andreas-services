"""
Headless-browser renderer Lambda.

Invoked synchronously by the source-run processor (via
``scout_core.adapters.renderer_client.fetch_rendered``) for webpage sources that
need JavaScript to run before their content exists — client-rendered pages and,
notably, sites behind a JS / proof-of-work bot challenge (e.g. SiteGround's
``sgcaptcha``) that serve a challenge stub to plain HTTP clients. A real browser
runs the site's own challenge JS exactly like a visitor, so the page (and its
clearance cookie) becomes available, then we hand back the fully-rendered HTML.

Contract (mirrors ``fetcher.fetch_url`` on the caller side):
- input:  ``{"url": str, "timeout_ms"?: int}``
- output: ``{"status": int, "html": str, "final_url": str}`` on success,
          ``{"status": 0, "error": str}`` on failure.

Chromium is launched once per warm container and the browser context is reused
across invocations, so within a run the clearance cookie obtained on the first
page is reused for the listing/detail fetches that follow (no re-solving) while
the container stays warm.
"""

import logging
import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Lambda only mounts /tmp writable and /dev/shm is tiny, so steer Chromium's
# scratch space there and drop the sandbox (the function is already isolated).
_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-setuid-sandbox",
]

# Substrings / paths that mark a page as still showing an anti-bot challenge
# interstitial rather than the real content.
_CHALLENGE_PATHS = ("/.well-known/sgcaptcha/", "/.well-known/captcha/")
_CHALLENGE_MARKERS = (
    "sgcaptcha", "sg-captcha", "Robot Challenge Screen",
    "Checking the site connection security",
)

# After the page settles, wait this long (at most) for the network to go idle so
# SPAs that fill content via XHR after DOMContentLoaded are captured fully.
# Bounded so a site with long-polling / persistent connections can't burn the
# whole invocation budget waiting for an idle that never comes.
_NETWORK_IDLE_MS = 8000

_pw = None
_browser = None
_context = None


def _ensure_context():
    """Lazily start Playwright + Chromium and a reusable browser context,
    re-launching if a previous one was torn down."""
    global _pw, _browser, _context
    if _pw is None:
        _pw = sync_playwright().start()
    if _browser is None or not _browser.is_connected():
        _browser = _pw.chromium.launch(headless=True, args=_LAUNCH_ARGS)
        _context = None
    if _context is None:
        _context = _browser.new_context(
            user_agent=_UA, viewport={"width": 1280, "height": 1800})
    return _context


def _safe_content(page):
    """page.content() raises while the page is mid-navigation (which is exactly
    what an anti-bot interstitial does when it redirects). Treat that as "not
    ready yet" rather than an error. Returns (html, navigating)."""
    try:
        return page.content(), False
    except PlaywrightError:
        return "", True


def _looks_like_challenge(html, url):
    if any(path in url for path in _CHALLENGE_PATHS):
        return True
    return any(marker in (html or "") for marker in _CHALLENGE_MARKERS)


def _settle_challenge(page, deadline):
    """Give an anti-bot interstitial time to run its JS (e.g. solve the
    proof-of-work) and redirect to the real page. Returns once the page is
    settled on non-challenge content, or the deadline passes."""
    while time.time() < deadline:
        html, navigating = _safe_content(page)
        if not navigating and not _looks_like_challenge(html, page.url):
            return
        try:
            page.wait_for_load_state("networkidle", timeout=2000)
        except PlaywrightError:
            pass
        page.wait_for_timeout(500)


def lambda_handler(event, _context):
    url = (event or {}).get("url")
    if not url:
        return {"status": 0, "error": "url is required"}
    timeout_ms = int((event or {}).get("timeout_ms") or 30000)
    deadline = time.time() + timeout_ms / 1000.0

    try:
        context = _ensure_context()
        page = context.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            _settle_challenge(page, deadline)
            # Let async/lazy-loaded content (XHR after DOMContentLoaded) land
            # before we snapshot. Bounded by both _NETWORK_IDLE_MS and the
            # remaining invocation budget.
            idle_ms = min(_NETWORK_IDLE_MS,
                          max(0, int((deadline - time.time()) * 1000)))
            if idle_ms:
                try:
                    page.wait_for_load_state("networkidle", timeout=idle_ms)
                except PlaywrightError:
                    pass
            status = resp.status if resp is not None else 200
            # The initial response is the challenge stub (HTTP 202) for gated
            # sites; once we've settled onto real content, report success so the
            # pipeline treats the HTML as a normal 2xx page.
            if status < 200 or status >= 300:
                status = 200
            html, navigating = _safe_content(page)
            # If we're still mid-navigation at the deadline, settle once more.
            if navigating:
                page.wait_for_timeout(500)
                html, _ = _safe_content(page)
            return {"status": status, "html": html, "final_url": page.url}
        finally:
            page.close()
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("render failed for %s", url)
        return {"status": 0, "error": str(exc)}
