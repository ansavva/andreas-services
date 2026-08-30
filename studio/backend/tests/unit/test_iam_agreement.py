"""Every AWS call this service makes must be granted, as a check rather than a hope.

**Why this file exists.** The deployed app returned "Could not read the catalog"
on every folder because `dynamodb:BatchGetItem` was not in the API role's policy.
`GetItem` and `Query` were, so sign-in — which resolves membership with a Query —
kept working while every listing failed. It shipped in #424 and was found by a
person opening the site.

**Nothing in the suite could have caught it.** moto does not enforce IAM: the
whole backend suite passes against a policy that grants nothing at all. A grant
is only ever proved by a real call, and CI makes none. So thirteen green PRs went
out and the one thing none of them could check was the one that broke.

This closes it the same way `test_cors_agreement.py` closes the CORS seam — by
reading the Terraform rather than trusting a comment. The source names the
operations; `modules/compute` names the permissions; the two are asserted to
agree.

**Two halves, and S3 is here because it is the same seam untested.** DynamoDB is
the one that broke. S3 is the one that has not yet: `clients/aws/s3.py` reaches
`get_object`, `put_object`, `copy_object`, `delete_objects`, `head_object` and
`generate_presigned_url`, and until now nothing asserted a single one of them was
granted. One file rather than two because the claim is about AWS calls and not
about a service, and because the guard below is one guard — a second copy of it
beside a second copy of the Terraform path is the drift this check exists to stop.

**The two halves are not the same shape, and that is the whole S3 difficulty.** A
boto3 DynamoDB operation maps to exactly one IAM action of the same name. An S3
one does not, and the names do not survive the crossing:

* there is **no `s3:HeadObject`** — `head_object` is authorized as `s3:GetObject`
* there is **no `s3:DeleteObjects`** — the batch delete is authorized per object
  as `s3:DeleteObject`
* there is **no `s3:CopyObject`** — a copy needs `s3:GetObject` on the source
  *and* `s3:PutObject` on the destination, which is what
  `modules/compute/main.tf` already says in prose and nothing checked

So the S3 map is one-to-many and reads nothing like the call it covers. A grant
missing there produces an `AccessDenied` naming an action that appears nowhere in
the source, which is the kind of failure that gets diagnosed as the wrong bug.

**What this cannot catch.** That the deployed role is serving what the Terraform
says — an apply has to have run. Nor a permission needed at a *resource* this
policy does not list, since it checks actions and not ARNs. It only sees calls
written as `client().<operation>(`, plus the two boto3 methods below that name
their operation in a string argument; one reached through a variable or `getattr`
is invisible. And it does not police *where* a call is written — an S3 call added
outside `clients/aws/s3.py` would be read as a DynamoDB one and dropped. Those
are the cases a real call still owns.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.paths import INFRA_MODULES, STUDIO_DIR

BACKEND = STUDIO_DIR / "backend" / "studio_core"
S3_CLIENT = BACKEND / "clients" / "aws" / "s3.py"
COMPUTE = (
    INFRA_MODULES / "compute" / "main.tf"
)

# `boto3` names an operation in snake_case and IAM names it in PascalCase.
# Spelled out rather than derived, because the mapping is not always mechanical
# — `BatchGetItem` is one word DynamoDB splits differently from how a naive
# title-case would.
IAM_ACTION = {
    "batch_get_item": "dynamodb:BatchGetItem",
    "get_item": "dynamodb:GetItem",
    "put_item": "dynamodb:PutItem",
    "update_item": "dynamodb:UpdateItem",
    "delete_item": "dynamodb:DeleteItem",
    "query": "dynamodb:Query",
    "scan": "dynamodb:Scan",
    "transact_write_items": "dynamodb:TransactWriteItems",
    "transact_get_items": "dynamodb:TransactGetItems",
    "batch_write_item": "dynamodb:BatchWriteItem",
}

# What each S3 operation is actually authorized as. One-to-many, and none of the
# three interesting rows is the name of the call — see the module docstring.
S3_ACTIONS = {
    "get_object": {"s3:GetObject"},
    # A managed transfer, and still one action. `download_fileobj` issues ranged
    # GETs under the covers — which is why it needs no multipart grant on the way
    # *in*, unlike `upload_file` on the way out, which this service deliberately
    # never uses.
    "download_fileobj": {"s3:GetObject"},
    "head_object": {"s3:GetObject"},
    "put_object": {"s3:PutObject"},
    "copy_object": {"s3:GetObject", "s3:PutObject"},
    "delete_object": {"s3:DeleteObject"},
    "delete_objects": {"s3:DeleteObject"},
    "list_objects_v2": {"s3:ListBucket"},
}

# Methods on a boto3 client that are not themselves API calls. Both of them name
# the real operation in a string argument, which `_signed_operations` and
# `_paginated_operations` read back out — so being on this list means "expanded
# elsewhere", never "needs nothing".
INDIRECT = {"generate_presigned_url", "get_paginator"}

_CALL = re.compile(r"client\(\)\.([a-z_]+)\(")

# THE PRESIGN TRAP, AND IT IS THE REASON THE S3 HALF IS NOT JUST A SECOND DICT.
#
# `generate_presigned_url` makes **no API call**. The signature is local
# arithmetic over the credentials in hand, so it returns a perfectly well-formed
# URL against a role that has been granted nothing at all — no exception, no log
# line, no failed request. The URL is only valid if the ROLE holds the action the
# signature names, and S3 decides that when somebody follows it.
#
# So the failure lands as far from the cause as this service can put it: a 403 in
# a browser's network tab, on a URL this API handed out, with nothing in
# CloudWatch — because the request that failed never reached the Lambda. Neither
# the unit suite nor a real invocation of this service would show it.
#
# The operation is therefore read out of the first argument and counted as a
# call, which is what makes `presign` depend on `s3:GetObject` and `presign_put`
# on `s3:PutObject` here rather than in a comment.
_SIGNED = re.compile(r'generate_presigned_url\(\s*"([a-z_]+)"')

# The same shape on the DynamoDB side: `client().get_paginator("query")` is the
# only way this service issues a Query, and the bare `_CALL` regex above sees
# `get_paginator` and stops. Until this line, `dynamodb:Query` — the grant that
# every sign-in depends on — was not covered by the assertion below at all.
_PAGINATED = re.compile(r'get_paginator\(\s*"([a-z_]+)"')


def _sources(*, s3: bool) -> list[Path]:
    """Backend modules, split by which client's calls they hold.

    `clients/aws/s3.py` is the only module that touches an S3 client, and every
    other module's `client()` is DynamoDB's. Splitting on the filename is what
    lets one regex serve both halves — and it is also the assumption named in
    the docstring's "cannot catch", because an S3 call written anywhere else
    would be counted as a DynamoDB one and then dropped as unrecognised.
    """
    if s3:
        return [S3_CLIENT]
    return [path for path in BACKEND.rglob("*.py") if path != S3_CLIENT]


def _called(paths: list[Path]) -> set[str]:
    found: set[str] = set()
    for path in paths:
        source = path.read_text()
        found |= set(_CALL.findall(source))
        found |= set(_SIGNED.findall(source))
        found |= set(_PAGINATED.findall(source))
    return found - INDIRECT


def _dynamodb_operations_called() -> set[str]:
    """DynamoDB operations the service invokes, by boto3 name."""
    return {name for name in _called(_sources(s3=False)) if name in IAM_ACTION}


def _s3_operations_called() -> set[str]:
    """S3 operations the service invokes, by boto3 name.

    Unfiltered, unlike the DynamoDB half above. That half scans the whole backend
    and has to ignore what is not a table call; this one reads exactly one module
    whose every `client()` is an S3 client, so an operation missing from
    `S3_ACTIONS` is a call nobody has checked rather than noise — and it fails
    below rather than being quietly dropped.
    """
    return _called(_sources(s3=True))


def _actions_granted(service: str) -> set[str]:
    """Actions for one service the API role's policy allows."""
    return set(re.findall(rf'"({service}:[A-Za-z]+)"', COMPUTE.read_text()))


def test_the_terraform_and_the_test_are_both_actually_being_read():
    """A guard on the guard.

    Both halves are regexes over files. A path that stopped resolving, or a
    pattern that stopped matching, would make the assertions below vacuous — and
    a vacuous IAM check is worse than none, because it reads like coverage.

    The two indirect patterns get their own line each. They are the ones that can
    silently stop matching without anything else changing: moving an operation
    name into a variable keeps the code working, keeps every other test green,
    and removes the only reason `s3:GetObject` and `dynamodb:Query` appear here
    at all.
    """
    assert COMPUTE.is_file(), f"{COMPUTE} is not where this test expects it"
    assert S3_CLIENT.is_file(), f"{S3_CLIENT} is not where this test expects it"

    granted = _actions_granted("dynamodb") | _actions_granted("s3")
    assert "dynamodb:Query" in granted, f"parsed no recognisable actions: {granted}"
    assert "s3:GetObject" in granted, f"parsed no recognisable actions: {granted}"

    assert _dynamodb_operations_called(), "parsed no DynamoDB calls out of the service"
    assert _s3_operations_called(), "parsed no S3 calls out of the service"

    source = S3_CLIENT.read_text()
    assert _SIGNED.findall(source), (
        "parsed no presigned operations out of clients/aws/s3.py — the trap the "
        "S3 half exists for is now unchecked"
    )
    assert _PAGINATED.findall("".join(path.read_text() for path in _sources(s3=False))), (
        "parsed no paginated operations out of the service — dynamodb:Query is "
        "now unchecked"
    )


def test_every_dynamodb_operation_the_service_calls_is_granted():
    """The check that would have caught #438.

    `BatchGetItem` is not covered by `GetItem`, and the failure it produced was
    indistinguishable from any other read error — the service collapses every
    `ClientError` into "Could not read the catalog".
    """
    granted = _actions_granted("dynamodb")
    missing = {
        IAM_ACTION[name]
        for name in _dynamodb_operations_called()
        if IAM_ACTION[name] not in granted
    }

    assert not missing, (
        f"the service calls {sorted(missing)} and the API role is not granted "
        f"{'it' if len(missing) == 1 else 'them'}.\n"
        f"Add to `actions` in studio/infra/modules/compute/main.tf.\n"
        f"moto does not enforce IAM, so nothing else in this suite will fail."
    )


def test_every_s3_action_the_service_needs_is_granted():
    """The same check on the seam that has not broken yet.

    A missing grant here fails in two different places depending on the call. A
    direct one — `get_object`, `copy_object`, `delete_objects` — raises inside
    the Lambda and surfaces as `services.manage`'s generic upstream error. A
    presigned one fails in the browser, hours later, on a URL this service
    already returned 200 with.
    """
    unmapped = sorted(_s3_operations_called() - set(S3_ACTIONS))
    assert not unmapped, (
        f"clients/aws/s3.py calls {unmapped}, which this test cannot map to an "
        f"IAM action.\nAdd to `S3_ACTIONS` — an S3 operation is rarely authorized "
        f"under its own name."
    )

    needed: set[str] = set()
    for name in _s3_operations_called():
        needed |= S3_ACTIONS[name]

    missing = needed - _actions_granted("s3")

    assert not missing, (
        f"the service needs {sorted(missing)} and the API role is not granted "
        f"{'it' if len(missing) == 1 else 'them'}.\n"
        f"Add to a statement in studio/infra/modules/compute/main.tf.\n"
        f"Note the action rarely matches the call: head_object needs "
        f"s3:GetObject, delete_objects needs s3:DeleteObject, and copy_object "
        f"needs both s3:GetObject and s3:PutObject."
    )
