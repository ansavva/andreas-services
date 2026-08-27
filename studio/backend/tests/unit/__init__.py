"""Unit tests: moto plus the Flask test client. No AWS, no network, no money.

**These used to sit loose at `tests/` and be "unit" only by implication** — they
were whatever was not in `integration/` or `smoke/`. That ambiguity is not
cosmetic: `conftest.py` one level up autouses a socket guard and a stubbed
caller, and a conftest applies to every directory beneath it, so "which tier am
I in" and "which guards apply to me" are the same question. Naming the tier
makes the answer readable instead of inferred.

    unit/          moto + test client        no gate
    integration/   real S3, DynamoDB, Cognito  STUDIO_INTEGRATION=1
    smoke/         the live prod API over HTTPS  STUDIO_SMOKE=1

`integration/` overrides `signed_in` and `_no_outbound_sockets` by name for
exactly this reason.
"""
