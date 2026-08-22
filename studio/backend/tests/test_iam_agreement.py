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

**What this cannot catch.** That the deployed role is serving what the Terraform
says — an apply has to have run. Nor a permission needed at a *resource* this
policy does not list, since it checks actions and not ARNs. And it only sees
calls written as `client().<operation>(`; one reached through a variable or
`getattr` is invisible. Those are the cases a real call still owns.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "studio_core"
COMPUTE = (
    Path(__file__).resolve().parents[2] / "infra" / "modules" / "compute" / "main.tf"
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

# S3 is granted by a separate statement and addressed by prefix; this file is
# about the catalog, which is the seam that actually broke.
_CALL = re.compile(r"client\(\)\.([a-z_]+)\(")


def _operations_called() -> set[str]:
    """DynamoDB operations the service invokes, by boto3 name."""
    found: set[str] = set()
    for path in BACKEND.rglob("*.py"):
        # `clients/aws/s3.py` calls `client().get_object` and friends on an S3
        # client. Only the DynamoDB module's calls are in scope here.
        if path.name == "s3.py":
            continue
        found |= set(_CALL.findall(path.read_text()))
    return {name for name in found if name in IAM_ACTION}


def _actions_granted() -> set[str]:
    """`dynamodb:*` actions the API role's policy allows."""
    return set(re.findall(r'"(dynamodb:[A-Za-z]+)"', COMPUTE.read_text()))


def test_the_terraform_and_the_test_are_both_actually_being_read():
    """A guard on the guard.

    Both halves are regexes over files. A path that stopped resolving, or a
    pattern that stopped matching, would make the assertion below vacuous — and
    a vacuous IAM check is worse than none, because it reads like coverage.
    """
    assert COMPUTE.is_file(), f"{COMPUTE} is not where this test expects it"
    granted = _actions_granted()
    assert "dynamodb:Query" in granted, f"parsed no recognisable actions: {granted}"
    assert _operations_called(), "parsed no DynamoDB calls out of the service"


def test_every_dynamodb_operation_the_service_calls_is_granted():
    """The check that would have caught #438.

    `BatchGetItem` is not covered by `GetItem`, and the failure it produced was
    indistinguishable from any other read error — the service collapses every
    `ClientError` into "Could not read the catalog".
    """
    granted = _actions_granted()
    missing = {
        IAM_ACTION[name]
        for name in _operations_called()
        if IAM_ACTION[name] not in granted
    }

    assert not missing, (
        f"the service calls {sorted(missing)} and the API role is not granted "
        f"{'it' if len(missing) == 1 else 'them'}.\n"
        f"Add to `actions` in studio/infra/modules/compute/main.tf.\n"
        f"moto does not enforce IAM, so nothing else in this suite will fail."
    )
