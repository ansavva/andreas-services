"""Sanitization for teacher-authored page HTML.

A teacher pastes HTML and students load it from a URL on our own domain. That
makes anything stored here a stored-XSS sink: a script that survives the write
runs in every student's browser, on our origin, for as long as the page is up.
So the HTML is sanitized on the way IN (here) and served under a restrictive
Content-Security-Policy on the way OUT (see ``routes.public``). Two independent
layers, because either one alone is a single point of failure.

The allowlist is shaped for teaching material — headings, lists, tables,
images, code, emphasis — and deliberately excludes anything that executes or
loads active content: no <script>, <style>, <iframe>, <object>, <embed>,
<form>, and no event-handler attributes.
"""

import nh3

# Tags a worksheet, warm-up or study guide legitimately needs.
ALLOWED_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr", "div", "span",
    "strong", "b", "em", "i", "u", "s", "sub", "sup", "mark", "small",
    "ul", "ol", "li", "dl", "dt", "dd",
    "blockquote", "pre", "code", "kbd", "samp", "var",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
    "a", "img", "figure", "figcaption",
    "abbr", "cite", "q", "time",
}

ALLOWED_ATTRIBUTES = {
    "*": {"class", "id", "title", "dir", "lang"},
    # "rel" is deliberately absent: nh3 sets it itself via link_rel below, and
    # allowlisting it here makes ammonia panic on a conflicting definition.
    "a": {"href", "target"},
    "img": {"src", "alt", "width", "height", "loading"},
    "td": {"colspan", "rowspan", "headers"},
    "th": {"colspan", "rowspan", "scope", "headers"},
    "col": {"span"},
    "colgroup": {"span"},
    "time": {"datetime"},
    "abbr": {"title"},
    "q": {"cite"},
    "blockquote": {"cite"},
}

# http/https only. Notably absent: javascript: and data: — the first executes,
# and the second can smuggle an SVG document that executes.
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def sanitize(raw_html: str) -> str:
    """Return ``raw_html`` reduced to the allowlist above.

    Disallowed tags are removed along with their content where that content is
    itself unsafe to show (script/style bodies), and unwrapped otherwise, so a
    teacher who pastes from a word processor keeps their text and loses only
    the machinery around it.
    """
    if not raw_html:
        return ""
    return nh3.clean(
        raw_html,
        tags=ALLOWED_TAGS,
        attributes={tag: set(attrs) for tag, attrs in ALLOWED_ATTRIBUTES.items()},
        url_schemes=ALLOWED_URL_SCHEMES,
        strip_comments=True,
        link_rel="noopener noreferrer",
    )
