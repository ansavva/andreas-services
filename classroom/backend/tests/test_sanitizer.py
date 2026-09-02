"""The sanitizer is the XSS boundary — these assert what it must never pass."""

from classroom_core.utils import html


def test_strips_script_tags_and_their_contents():
    cleaned = html.sanitize("<p>Warm up</p><script>steal(document.cookie)</script>")
    assert "<p>Warm up</p>" in cleaned
    assert "script" not in cleaned.lower()
    assert "steal" not in cleaned


def test_strips_inline_event_handlers():
    cleaned = html.sanitize('<img src="https://x.test/a.png" onerror="alert(1)">')
    assert "onerror" not in cleaned.lower()
    assert "alert" not in cleaned


def test_strips_javascript_urls():
    cleaned = html.sanitize('<a href="javascript:alert(1)">click</a>')
    assert "javascript:" not in cleaned.lower()


def test_strips_data_urls_which_can_smuggle_executable_svg():
    cleaned = html.sanitize('<a href="data:text/html;base64,PHNjcmlwdD4=">x</a>')
    assert "data:" not in cleaned.lower()


def test_strips_iframes_and_forms():
    cleaned = html.sanitize(
        '<iframe src="https://evil.test"></iframe>'
        '<form action="https://evil.test"><input name="p"></form>'
    )
    assert "iframe" not in cleaned.lower()
    assert "<form" not in cleaned.lower()


def test_keeps_the_markup_a_worksheet_actually_needs():
    source = (
        "<h2>Solving for x</h2>"
        "<p>Try these <strong>three</strong> problems:</p>"
        "<ol><li>2x + 3 = 11</li><li>5x = 40</li></ol>"
        '<table><tr><th scope="col">x</th><td>4</td></tr></table>'
        '<img src="https://example.test/graph.png" alt="A line graph">'
        '<a href="https://example.test/notes">Notes</a>'
    )
    cleaned = html.sanitize(source)
    for fragment in ["<h2>", "<strong>", "<ol>", "<li>", "<table>", "<img", "<a"]:
        assert fragment in cleaned
    assert 'alt="A line graph"' in cleaned


def test_adds_noopener_to_links():
    cleaned = html.sanitize('<a href="https://example.test">Notes</a>')
    assert "noopener" in cleaned


def test_empty_input_is_empty_output():
    assert html.sanitize("") == ""
    assert html.sanitize(None) == ""
