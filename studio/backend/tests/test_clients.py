"""The client cache hook every moto-backed test in this suite leans on.

`conftest.media_bucket` calls `s3.reset_client()` on both sides of the mock,
because a client cached across that boundary is one still bound to a backend that
no longer exists — and the way that fails is a test quietly asserting against
another test's bucket rather than raising. The hook had no test of its own; it
gets one here for each client, so a caching change cannot break every fixture in
the suite silently.
"""

import pytest

from studio_core.clients.aws import dynamodb, s3


@pytest.fixture(autouse=True)
def _drop_cached_clients():
    """Leave both caches empty.

    These are the only tests that build a client outside a moto mock, so the one
    they leave behind would be pointed at real AWS. Empty is the safe state to
    hand to whatever runs next.
    """
    yield
    s3.reset_client()
    dynamodb.reset_client()


def test_s3_client_is_cached():
    assert s3.client() is s3.client()


def test_s3_reset_client_drops_the_cached_client():
    cached = s3.client()
    s3.reset_client()
    assert s3.client() is not cached


def test_dynamodb_client_is_cached():
    assert dynamodb.client() is dynamodb.client()


def test_dynamodb_reset_client_drops_the_cached_client():
    cached = dynamodb.client()
    dynamodb.reset_client()
    assert dynamodb.client() is not cached
