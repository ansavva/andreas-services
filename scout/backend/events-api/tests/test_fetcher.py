"""Unit tests for the content fetcher (fetcher.py). No network — fetch is stubbed."""

import unittest

import fetcher


class TestFetcherPure(unittest.TestCase):
    def test_host_of(self):
        self.assertEqual(fetcher.host_of("https://www.Example.com/path"), "example.com")
        self.assertEqual(fetcher.host_of("example.com"), "example.com")
        self.assertEqual(fetcher.host_of("http://sub.example.com:8080/x"),
                         "sub.example.com")

    def test_same_domain(self):
        self.assertTrue(fetcher.same_domain("https://example.com/a", "example.com"))
        self.assertTrue(fetcher.same_domain("https://events.example.com/a", "example.com"))
        self.assertTrue(fetcher.same_domain("https://example.com", "www.example.com"))
        self.assertFalse(fetcher.same_domain("https://evil.com", "example.com"))
        self.assertFalse(fetcher.same_domain("https://notexample.com", "example.com"))

    def test_extract_links_resolves_and_dedupes(self):
        html = """
          <a href="/events">rel</a>
          <a href="https://example.com/abs">abs</a>
          <a href="/events">dup</a>
          <a href="mailto:x@y.com">mail</a>
          <a href="#frag">frag</a>
        """
        links = fetcher.extract_links(html, base_url="https://example.com/home")
        self.assertEqual(links, [
            "https://example.com/events",
            "https://example.com/abs",
        ])

    def test_extract_links_without_base_keeps_only_absolute(self):
        html = '<a href="/rel">r</a><a href="https://x.com/p">a</a>'
        self.assertEqual(fetcher.extract_links(html), ["https://x.com/p"])

    def test_follow_links_filters_caps_and_records_failures(self):
        html = """
          <a href="https://example.com/1">1</a>
          <a href="https://example.com/2">2</a>
          <a href="https://example.com/3">3</a>
          <a href="https://offsite.com/x">off</a>
        """

        def fetch_fn(url):
            if url.endswith("/2"):
                raise TimeoutError("slow")
            if url.endswith("/3"):
                return 404, ""
            return 200, f"<p>{url}</p>"

        outcomes = fetcher.follow_links(
            html, base_url="https://example.com", root_domain="example.com",
            cap=2, fetch_fn=fetch_fn,
        )
        # Offsite excluded; cap=2 keeps only /1 and /2.
        self.assertEqual([o["url"] for o in outcomes],
                         ["https://example.com/1", "https://example.com/2"])
        self.assertTrue(outcomes[0]["ok"])
        self.assertEqual(outcomes[0]["content"], "<p>https://example.com/1</p>")
        self.assertFalse(outcomes[1]["ok"])
        self.assertIn("slow", outcomes[1]["reason"])

    def test_follow_links_non_2xx_is_failure(self):
        html = '<a href="https://example.com/x">x</a>'
        outcomes = fetcher.follow_links(
            html, base_url="https://example.com", root_domain="example.com",
            cap=5, fetch_fn=lambda u: (500, ""),
        )
        self.assertFalse(outcomes[0]["ok"])
        self.assertEqual(outcomes[0]["reason"], "http 500")


if __name__ == "__main__":
    unittest.main()
