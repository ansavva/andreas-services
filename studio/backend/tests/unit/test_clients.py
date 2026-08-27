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


def test_collecting_the_integration_tree_leaves_the_unit_credentials_alone():
    """**The one that only failed on CI, and only after both guards existed.**

    pytest imports every conftest during COLLECTION, so
    `tests/integration/conftest.py` runs on an ordinary `pytest -q` where every
    test in that tree is skipped. It strips the sentinel AWS credentials — right,
    when it is about to talk to real AWS, because an environment variable beats
    `~/.aws/credentials` and would shadow the real key.

    Doing it unconditionally left the unit suite with no credentials at all.
    botocore then walks its provider chain to the EC2 metadata service, and the
    socket guard next door refuses the connection: four failures here, invisible
    on any machine with a credentials file for boto3 to fall back to.

    This asserts the state the unit suite needs AFTER every conftest has been
    imported, which is the only place the interaction is visible.
    """
    import os

    assert os.environ.get("AWS_ACCESS_KEY_ID") == "testing"
    assert os.environ.get("AWS_SECRET_ACCESS_KEY") == "testing"
