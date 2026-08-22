"""The post-deploy smoke harness: the deployed prod API, over HTTPS, signed in.

**Opt-in, and silent otherwise.** Without `STUDIO_SMOKE=1` every test in this
tree is skipped at collection, like `tests/integration/`. Unlike that tree, this
one runs **in CI** — `studio-prod.yaml` runs it after `update-lambda`, against
`studio-api.andreas.services`.

## The one library, and why that is the whole design

The account this signs in as is a member of **exactly one library**, seeded by
`scripts/prod-seed-smoke.py` from `seeds/smoke.json`. That is not a convention:
`app_factory`'s `before_request` resolves the library a request is about from
the caller's own membership rows, and a caller with one membership can only ever
address that one. Every route then checks the node's own `lib` against the same
rows. So the blast radius of everything below is one library that holds nothing
but what a smoke run put there.

Two things follow, and both are deliberate:

* **No request here sends `X-Studio-Library`.** The header is how a caller in
  several libraries names one; sending it is the only way this suite could ask
  for a different library, so it never does. The API resolves the sole
  membership instead.
* **`only_library` asserts it before anything else runs.** Every fixture that
  writes depends on it, so a token that reaches more than one library never
  reaches a `POST`.

## Credentials

`SMOKE_TEST_USER_PASSWORD` has **no default** and never will — a default would
be a credential in the repository. Nothing here interpolates it into a test
name, an assertion message, a log line or a URL: every error names the
*variable*, never what it held.

The pool id, the client id and the base URL have no defaults either, for a
different reason: this suite writes to production, and a value it guessed would
be a run nobody chose. `studio-prod.yaml` passes all three.

**No AWS credentials are needed or used.** The suite holds a pool id, a client
id, an address and a password, and reaches everything else over HTTPS — which is
also what makes it exercise the Lambda's own execution role rather than a
developer's.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
FIXTURE_FILE = HERE.parents[2] / "seeds" / "smoke.json"
SIGN_IN = HERE / "sign_in.py"

# Every scratch folder this suite makes starts with it, so a run can recognise
# what an earlier run left behind and remove it. Nothing else in a library is
# named this way.
SCRATCH_PREFIX = "smoke-"


def pytest_collection_modifyitems(config, items):
    """Skip this tree unless it was asked for, by name.

    **Filtered to this directory**, because pytest hands this hook *every*
    collected item regardless of which conftest defines it — an unfiltered
    version skips the entire backend suite and reports a green run that executed
    nothing. `tests/integration/conftest.py` learned that the hard way.
    """
    if os.environ.get("STUDIO_SMOKE") == "1":
        return
    skip = pytest.mark.skip(reason="smoke suite: set STUDIO_SMOKE=1 (it writes to prod)")
    for item in items:
        if HERE in Path(str(item.fspath)).resolve().parents:
            item.add_marker(skip)


def _required(name: str) -> str:
    """A variable this suite cannot invent, or a failure naming only the variable."""
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(
            f"{name} is not set. The smoke suite takes its target and its credentials "
            "from the environment only — see studio/docs/PROD_SMOKE.md. An environment "
            "secret resolves to an empty string in silence when a job is missing its "
            "`environment:` key, so check that first."
        )
    return value


@pytest.fixture(scope="session")
def fixture() -> dict:
    """`seeds/smoke.json` — the one file that says who exists and what they own.

    The same file the seeder loads, so the identity that is provisioned and the
    identity this signs in as cannot drift apart.
    """
    return json.loads(FIXTURE_FILE.read_text())


@pytest.fixture(scope="session")
def base_url() -> str:
    """The deployed origin under test, with no trailing slash."""
    return _required("STUDIO_SMOKE_BASE_URL").rstrip("/")


@pytest.fixture(scope="session")
def id_token() -> str:
    """A real ID token for the smoke account, by SRP against the real pool.

    Session-scoped: SRP is several round trips and the token is valid for eight
    hours, so minting one per test would add minutes and prove nothing a single
    mint does not.

    Run through `uv` on a PEP 723 script rather than imported, because SRP needs
    a client the backend does not otherwise depend on — and a test-only Cognito
    client does not belong in the Lambda image's lockfile.
    """
    result = subprocess.run(
        ["uv", "run", "--quiet", str(SIGN_IN)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env={
            **os.environ,
            "STUDIO_SMOKE_POOL_ID": _required("STUDIO_SMOKE_POOL_ID"),
            "STUDIO_SMOKE_CLIENT_ID": _required("STUDIO_SMOKE_CLIENT_ID"),
            "SMOKE_TEST_USER_PASSWORD": _required("SMOKE_TEST_USER_PASSWORD"),
        },
    )
    if result.returncode != 0:
        # stderr, never stdout: stdout is the token on success, and a failure
        # message quoting it would put a credential in the pytest report.
        pytest.fail(f"sign_in.py failed: {result.stderr.strip()}")
    token = result.stdout.strip()
    assert token.count(".") == 2, "sign_in.py did not return a JWT"
    return token


class Api:
    """The deployed API, as a signed-in caller sees it.

    `urllib` rather than a client library: this suite's dependency surface is
    the thing it is trying not to have, and the API is six verbs over JSON.

    **`X-Studio-Library` is never sent.** See this module's docstring — with one
    membership the API resolves the library itself, and the header is the only
    way a request here could ask for another one.
    """

    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url
        self._token = token

    def request(self, method: str, path: str, *, params: dict | None = None,
                body: dict | None = None, expect: int = 200):
        url = f"{self._base}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self._token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                status, payload = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, payload = error.code, error.read()

        # A body that is not JSON is a body the application did not write —
        # API Gateway's own `Unauthorized`, or a CloudFront error page. Decoding
        # it defensively keeps the *status* readable instead of replacing a
        # useful 403 with a JSONDecodeError three frames down.
        try:
            parsed = json.loads(payload) if payload else None
        except ValueError:
            parsed = payload.decode(errors="replace")[:500]

        if status != expect:
            # The body carries the API's own message, which is the whole reason
            # this is worth reading — "Could not read the catalog" is what a
            # missing IAM grant looks like from out here.
            pytest.fail(f"{method} {path} returned {status}, expected {expect}: {parsed}")
        return parsed

    def get(self, path: str, **params):
        return self.request("GET", path, params=params or None)

    def post(self, path: str, body: dict | None = None, expect: int = 200):
        return self.request("POST", path, body=body if body is not None else {}, expect=expect)

    def delete(self, path: str):
        return self.request("DELETE", path)


@pytest.fixture(scope="session")
def api(base_url, id_token) -> Api:
    return Api(base_url, id_token)


@pytest.fixture(scope="session")
def only_library(api, fixture) -> str:
    """The smoke library's id, having proved it is the *only* one reachable.

    **Everything that writes depends on this fixture**, directly or through
    `scratch`, so a token that reaches a second library fails here and never
    reaches a `POST`. The test of the same name asserts it again as the suite's
    first and most important claim; this is the structural half.
    """
    expected = fixture["library"]["id"]
    reachable = [entry["id"] for entry in api.get("/api/libraries")]
    if reachable != [expected]:
        pytest.fail(
            "ISOLATION VIOLATED — refusing to touch anything.\n"
            f"GET /api/libraries returned {len(reachable)} librar"
            f"{'y' if len(reachable) == 1 else 'ies'}; the smoke account must be a "
            f"member of exactly one, {expected}, and of nothing else. Membership is "
            "the whole of authorisation in this service, so an extra one is an extra "
            "library this suite can create in, upload to and DELETE from. Remove it "
            "before running again."
        )
    return expected


@pytest.fixture(scope="session")
def root_node(api, only_library, fixture) -> str:
    """The library's root node id, via the route a client would use.

    `/api/resolve` with no path is how anything finds where to start —
    `/api/libraries` deliberately reports id, name and role and not the root.
    """
    resolved = api.get("/api/resolve")["id"]
    assert resolved == fixture["library"]["root_node"], (
        "The library's root is not the node the fixture seeded; the seeder and the "
        "table disagree about what this library opens on."
    )
    return resolved


@pytest.fixture(scope="session")
def scratch(api, root_node):
    """A folder of this run's own, removed afterwards **however the run ends**.

    Session-scoped so one teardown covers every test: a `DELETE` of this folder
    removes the whole subtree, rows first and then blobs, so nothing a test
    created below it can outlive the run — including when the test that created
    it failed halfway through.

    Stale siblings are swept at setup rather than left to accumulate. A job
    killed between the `yield` and the teardown — a cancelled workflow, a runner
    that vanished — leaves its folder behind, and nothing else would ever remove
    it. The sweep is one listing of one folder inside this library and touches
    nothing that is not named `smoke-…`.
    """
    for entry in api.get("/api/tree", node=root_node)["folders"]:
        if entry["name"].startswith(SCRATCH_PREFIX):
            api.delete(f"/api/nodes/{entry['id']}")

    folder = api.post(
        "/api/nodes",
        {"parent": root_node, "name": f"{SCRATCH_PREFIX}{uuid.uuid4()}", "kind": "folder"},
        expect=201,
    )
    yield folder["id"]

    # Best effort, and loud. A teardown that raised would replace whatever
    # assertion actually failed with a cleanup error, which is the one way to
    # make a red run harder to read than no run at all. What it leaves behind is
    # swept by the next run's setup.
    try:
        api.delete(f"/api/nodes/{folder['id']}")
    except (Exception, pytest.fail.Exception) as error:  # noqa: BLE001
        print(f"[smoke] could not remove {folder['name']}: {error}")
