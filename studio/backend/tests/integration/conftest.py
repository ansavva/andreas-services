"""The integration harness: real S3, real DynamoDB, real Cognito (#288).

**Opt-in, and silent otherwise.** Without `STUDIO_INTEGRATION=1` every test in
this tree is skipped at collection. That is not politeness — these tests write to
a real AWS account, and a suite that ran them by accident on a laptop with prod
credentials exported would be a bad afternoon.

**These never run in CI.** `studio-pr.yml` validates only and never writes to
AWS; that is a repo-wide rule and this does not become the exception. The gate is
local, and `dev-aws-setup.sh --check` is what tells a developer their stack is
ready.

**Nothing here is hard-coded.** The stack's identifiers are read out of the
Terraform state object in S3, keyed by the machine id at
`~/.config/andreas-services/studio/machine-id` — the same way
`dev-aws-common.sh` finds them, so a developer's stack and this suite cannot end
up pointing at two different places. Set `STUDIO_DEV_MACHINE_ID` to target a
stack this machine did not create; `dev-aws-setup.sh` prints the id it used.

**The token comes from `dev-token.sh` rather than being minted here.** One
description of how you sign in: the script is what a developer uses and what
these tests exercise, so a break in it is a failure here rather than a surprise
later. It costs a subprocess per session, which is nothing against a suite that
already needs a provisioned AWS stack.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import boto3
import pytest

STATE_BUCKET = "andreas-services-terraform-state"
SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
MACHINE_ID_FILE = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "andreas-services"
    / "studio"
    / "machine-id"
)
UUID_SHAPE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(config, items):
    """Skip this tree unless it was asked for, by name.

    **Filtered to this directory, and that is not cosmetic.** pytest hands this
    hook *every* collected item regardless of which conftest defines it, so the
    unfiltered version skipped the entire backend suite — 373 tests, reported as
    373 skips, exit code 0. A CI run would have been green having executed
    nothing. Caught by reading the count, which is the only thing that
    distinguishes that outcome from a healthy one.
    """
    if os.environ.get("STUDIO_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(
        reason="integration suite: set STUDIO_INTEGRATION=1 and provision a dev stack"
    )
    for item in items:
        if HERE in Path(str(item.fspath)).resolve().parents:
            item.add_marker(skip)


def _machine_id() -> str:
    override = os.environ.get("STUDIO_DEV_MACHINE_ID", "").strip()
    if override:
        value = override
    elif MACHINE_ID_FILE.exists():
        value = MACHINE_ID_FILE.read_text().strip()
    else:
        pytest.fail(
            f"No machine id at {MACHINE_ID_FILE} and STUDIO_DEV_MACHINE_ID is unset. "
            "Run studio/scripts/dev-aws-setup.sh first."
        )
    if not UUID_SHAPE.match(value):
        pytest.fail(f"Machine id in {MACHINE_ID_FILE} is not a lowercase UUID.")
    return value


@pytest.fixture(scope="session")
def dev_stack() -> dict:
    """This machine's dev stack, read straight out of the Terraform state.

    Deliberately not `terraform output`: that needs an init, a backend
    reconfiguration and a provider download to answer a question the state
    object already contains, and it would not work from a cold checkout.
    """
    machine_id = _machine_id()
    account = boto3.client("sts").get_caller_identity()["Account"]
    key = f"studio/dev/{account}/{machine_id}/terraform.tfstate"
    try:
        body = boto3.client("s3").get_object(Bucket=STATE_BUCKET, Key=key)["Body"].read()
    except Exception as error:  # noqa: BLE001 - any failure here means the same thing
        pytest.fail(f"Could not read s3://{STATE_BUCKET}/{key}: {error}")

    outputs = json.loads(body).get("outputs", {})
    stack = {name: outputs.get(name, {}).get("value") for name in (
        "cognito_user_pool_id",
        "cognito_user_pool_client_id",
        "media_bucket_name",
        "catalog_table_name",
        "machine_id",
    )}
    missing = [name for name, value in stack.items() if not value]
    if missing:
        pytest.fail(f"Terraform state is missing outputs: {', '.join(missing)}")
    # The state describes the stack this machine id names, or the run is aimed at
    # something nobody meant to write to.
    assert stack["machine_id"] == machine_id
    return stack


@pytest.fixture(scope="session", autouse=True)
def _point_config_at_the_dev_stack(dev_stack):
    """Redirect `studio_core.config` at the dev stack for the whole session.

    Autouse and session-scoped because every module here imports `studio_core`,
    and a per-test override would leave the first import reading whatever the
    developer's shell happened to hold — which, for anyone who has run
    `dev-setup.sh`, is **prod**. Set once, before anything reads it.
    """
    previous = {}
    for name, value in (
        ("STUDIO_MEDIA_BUCKET", dev_stack["media_bucket_name"]),
        ("STUDIO_CATALOG_TABLE", dev_stack["catalog_table_name"]),
        ("STUDIO_COGNITO_USER_POOL_ID", dev_stack["cognito_user_pool_id"]),
        ("STUDIO_COGNITO_CLIENT_ID", dev_stack["cognito_user_pool_client_id"]),
        # The browsable root is the whole bucket, as in prod. A stale value in a
        # shell would otherwise silently rewrite what these tests assert about.
        ("STUDIO_MEDIA_ROOT_PREFIX", ""),
    ):
        previous[name] = os.environ.get(name)
        os.environ[name] = value

    # The clients cache a boto3 client per process, and any earlier test run in
    # the same interpreter would have built one against a different bucket.
    from studio_core.clients.aws import dynamodb, s3
    from studio_core.services import identity

    s3.reset_client()
    dynamodb.reset_client()
    identity.reset_jwks_client()
    yield
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@pytest.fixture(autouse=True)
def signed_in():
    """Switch off the unit suite's stub caller for this whole tree.

    `tests/conftest.py` autouses a fixture of this name that replaces
    `app_factory`'s references to `identity` and `catalog` with a stand-in
    returning `sub-owner` and `lib-0001`. That is right where it lives —
    thirty-seven route tests that are not about authentication would otherwise
    each need a token — and a conftest applies to every directory beneath it,
    so it reaches here too.

    Here it is silently wrong. A test that builds the app would be signed in as
    a subject the real pool never issued, scoped to a library the real table
    does not hold, and would fail on a 403 that says nothing about what it was
    checking. Overriding the name in *this* conftest rather than in one module
    means a test added later inherits the real `before_request` rather than
    finding out the hard way.

    Nothing to yield: the point is that the parent fixture does not run.
    """
    return None


@pytest.fixture(scope="session")
def id_token() -> str:
    """A real ID token for the dev pool's test account, via `dev-token.sh`.

    Session-scoped: SRP is several round trips and the token is valid for eight
    hours, so minting one per test would add minutes to the suite and prove
    nothing a single mint does not.
    """
    script = SCRIPTS / "dev-token.sh"
    result = subprocess.run(  # noqa: S603 - a path this repo owns, no shell
        [str(script), "--no-prompt"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        # stderr, never stdout: stdout is the token on success, and a failure
        # message that quoted it would put a credential in the pytest report.
        pytest.fail(f"dev-token.sh failed: {result.stderr.strip()}")
    token = result.stdout.strip()
    assert token.count(".") == 2, "dev-token.sh did not return a JWT"
    return token


@pytest.fixture
def bucket(dev_stack):
    """A boto3 S3 client aimed at the dev bucket, and the bucket's name."""
    return boto3.client("s3"), dev_stack["media_bucket_name"]


@pytest.fixture
def library(dev_stack, id_token):
    """A library and its root node in the dev table, removed afterwards.

    Written literally rather than through `services.catalog`, for the reason the
    unit `conftest` gives: `catalog` is the only module allowed to know these
    shapes, so a fixture built from its own helpers would agree with any drift in
    them. Here it matters more, not less — this is the suite that would catch a
    shape DynamoDB accepts and moto does not.

    The membership row is for the **real `sub`** out of the real token, so a
    request authorised through `before_request` reaches these rows rather than a
    stub's.
    """
    import uuid as _uuid

    from studio_core.services import identity

    sub = identity.caller_sub(f"Bearer {id_token}")
    table = dev_stack["catalog_table_name"]
    client = boto3.client("dynamodb")

    lib = f"lib-it-{_uuid.uuid4()}"
    root = f"node-it-{_uuid.uuid4()}"
    now = "2026-08-20T00:00:00.000000+00:00"
    items = [
        {"pk": {"S": f"LIB#{lib}"}, "sk": {"S": "META"}, "name": {"S": "Integration"},
         "root_node": {"S": root}, "created_at": {"S": now}},
        {"pk": {"S": f"USER#{sub}"}, "sk": {"S": f"LIB#{lib}"}, "role": {"S": "owner"},
         "created_at": {"S": now}},
        {"pk": {"S": f"NODE#{root}"}, "sk": {"S": "META"}, "node_id": {"S": root},
         "lib": {"S": lib}, "name": {"S": "Integration"}, "kind": {"S": "folder"},
         "path": {"S": "/"}, "created_at": {"S": now}, "updated_at": {"S": now}},
    ]
    for item in items:
        client.put_item(TableName=table, Item=item)

    created: list[str] = []
    yield {"lib": lib, "root": root, "sub": sub, "created": created}

    # Best effort. A leaked row in a dev table is noise; a failed teardown that
    # masks the real assertion failure is worse, so nothing here raises.
    from studio_core.services import catalog

    for node_id in created:
        try:
            catalog.delete_node(node_id)
        except Exception:  # noqa: BLE001, S110 - teardown must not mask a failure
            pass
    for item in items:
        try:
            client.delete_item(
                TableName=table, Key={"pk": item["pk"], "sk": item["sk"]}
            )
        except Exception:  # noqa: BLE001, S110
            pass
