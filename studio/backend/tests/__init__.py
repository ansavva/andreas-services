"""The app's test suite. START HERE.

    tests/
      conftest.py    moto, the stub caller, the socket guard
      paths.py       where studio/ is, counted ONCE
      unit/          moto + the Flask test client        no gate
      integration/   real S3, DynamoDB, Cognito          STUDIO_INTEGRATION=1
      smoke/         the live prod API over HTTPS        STUDIO_SMOKE=1

Route modules are exercised through the `api` / `empty_api` HTTP fixture rather
than imported directly, and that is the intended seam: a unit layer under a
Flask route mostly re-tests Flask.

**Each tier is a directory because conftest inheritance is scoped by directory**
— so "which tier am I in" and "which guards apply to me" are one question.
`integration/` overrides `signed_in` and `_no_outbound_sockets` by name, because
the stub caller and the loopback allowlist are both exactly wrong for a tree
whose purpose is to reach real AWS. Those overrides are the mechanism; put a new
tier-wide exemption in that conftest rather than in a module.

The unit tests used to sit loose at `tests/` and be "unit" only by implication.

`smoke/` is a DETECTOR, not a gate: studio has no staging, so `studio-prod.yaml`
runs it after the new image is already serving. It is the only thing that
exercises the Lambda's own execution role — moto enforces no IAM — which is how
a missing `dynamodb:BatchGetItem` grant reached production.
"""
