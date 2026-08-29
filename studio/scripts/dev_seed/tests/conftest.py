"""Fixtures for `dev-seed`'s own suite.

**Two guards, both inherited from the pipeline suite this test came out of, and
both load-bearing.** `dev-seed` is the one tool in this repo that opens a
DynamoDB client and an S3 client of its own, which is exactly why it is a
separate project — and exactly why its tests must not be able to reach a real
table. In the pipeline suite these sat in a conftest shared with ninety other
commands; here they guard the only code that could do damage with them.
"""
import os

import pytest

# Credentials and region before boto3/moto import, as `pipeline/tests/conftest.py`
# sets them: a missing region fails as `NoRegionError`, which reads like a code
# bug rather than a configuration one.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

from moto import mock_dynamodb  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_dynamodb():
    """No test may reach a real catalog table, including by accident.

    Autouse rather than opt-in: `publish` asks whether the table exists before
    it reads anything, and without this that question goes to AWS over the
    network with the sentinel credentials above. The table itself is NOT created
    here — a command meeting a table that does not exist is worth exercising,
    and `dev_stack` builds one for the tests that want it.
    """
    with mock_dynamodb():
        yield


@pytest.fixture(autouse=True)
def _no_profile_config(monkeypatch, tmp_path):
    """Never read the developer's real `~/.config/.../studio/config`.

    `aws.value()` falls back to it when the environment does not supply a field,
    so a machine with a `dev` profile configured would silently point a test at
    that stack. Pointed at an empty directory instead: the tests set
    `STUDIO_S3_BUCKET` and `STUDIO_CATALOG_TABLE` explicitly, and anything they
    forget must fail rather than resolve.
    """
    monkeypatch.setattr("dev_seed.aws.CONFIG_FILE", tmp_path / "config")
